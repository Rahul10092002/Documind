import asyncio
import json
import logging
from typing import List, Any, Sequence
from pydantic import BaseModel, Field
from langchain_core.output_parsers import JsonOutputParser
from langchain_classic.output_parsers import OutputFixingParser
from langchain_core.runnables import RunnableParallel, RunnableLambda
from langchain_core.output_parsers import StrOutputParser
from operator import itemgetter
from sqlalchemy.orm import Session
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document as LCDocument
from app.config import settings
from app.database import engine, SessionLocal
from app.models import Document as DbDocument, ChatMessage, MessageRole
from app.utils.llm_client import LLMClientInterface, default_llm_client
from app.utils.vector_retriever import VectorStoreInterface, default_vector_retriever
from app.utils.prompt_templates import get_qa_prompt, get_risk_analysis_prompt, get_rephrase_prompt, get_followup_questions_prompt
from app.utils.vector_store import get_vector_store
from app.utils.entity_extraction import clean_boilerplate

logger = logging.getLogger(__name__)


class RiskFlag(BaseModel):
    clause: str = Field(description="Text of the risky clause or summary from the document")
    reason: str = Field(description="Detailed explanation of the risk, in Devanagari/Hindi script if response language is Hindi, else in English")
    level: str = Field(description="Risk level: high, medium, or low")


class RiskAnalysisAndDraft(BaseModel):
    risk_flags: List[RiskFlag] = Field(default=[], description="List of identified potential legal/financial risk flags")
    risk_obligation_summary: str = Field(default="", description="A combined summary detailing risks, faults, liabilities, and key obligation terms identified in the document, in Devanagari/Hindi script if response language is Hindi, else in English")


def format_docs(docs: list[LCDocument]) -> str:
    """Helper to format list of LangChain Document objects into a single context string."""
    if not docs:
        return ""
    return "\n\n".join(doc.page_content for doc in docs)


format_docs_runnable = RunnableLambda(format_docs)


def build_context(retrieved_chunks: list[dict], max_chars: int | None = None) -> str:
    """Concatenates the chunk contents until the max character limit is reached."""
    limit = max_chars if max_chars is not None else settings.max_context_chars
    context = ""
    for chunk in retrieved_chunks:
        content = chunk["page_content"]
        if len(context) + len(content) > limit:
            logger.warning("Context truncated to stay under MAX_CONTEXT_CHARS (%d)", limit)
            break
          
        context += content + "\n\n"
    return context.strip()


def generate_answer(
    context: str, 
    question: str, 
    llm_client: LLMClientInterface = default_llm_client
) -> str:
    """Constructs prompt using ChatPromptTemplate and generates answer using prompt | llm composition."""
    prompt = get_qa_prompt()
    messages = prompt.invoke({
        "context": context,
        "input": question,
        "chat_history": []
    })

    try:
        return llm_client.ask(messages)
    except Exception as e:
        logger.error("Failed to generate answer from LLM: %s", e)
        raise RuntimeError(f"Error generating answer from LLM: {e}") from e


async def agenerate_answer(
    context: str, 
    question: str, 
    llm_client: LLMClientInterface = default_llm_client
) -> str:
    """Constructs prompt using ChatPromptTemplate and generates answer using prompt | llm composition asynchronously."""
    prompt = get_qa_prompt()
    messages = prompt.invoke({
        "context": context,
        "input": question,
        "chat_history": []
    })

    try:
        return await llm_client.aask(messages)
    except Exception as e:
        logger.error("Failed to generate answer from LLM asynchronously: %s", e)
        raise RuntimeError(f"Error generating answer from LLM: {e}") from e


class ScoredChromaRetriever(BaseRetriever):
    vector_store: Any
    k: int
    document_id: str
    distance_threshold: float
    on_step: Any = None

    def _get_relevant_documents(self, query: str) -> List[LCDocument]:
        results = self.vector_store.similarity_search_with_score(
            query=query,
            k=self.k,
            filter={"document_id": self.document_id}
        )
        docs = []
        for doc, score in results:
            if score < self.distance_threshold:
                doc.metadata["score"] = score
                docs.append(doc)
        return docs

    async def _aget_relevant_documents(self, query: str) -> List[LCDocument]:
        on_step = getattr(self, "on_step", None)
        if on_step:
            await on_step("Searching document sections...")
        results = await self.vector_store.asimilarity_search_with_score(
            query=query,
            k=self.k,
            filter={"document_id": self.document_id}
        )
        docs = []
        for doc, score in results:
            if score < self.distance_threshold:
                doc.metadata["score"] = score
                docs.append(doc)
        return docs


class ChatMessageHistoryAdapter(BaseChatMessageHistory):
    """Adapter that reads chat history from the relational database's chat_messages table."""

    def __init__(self, document_id: str, db: Session = None):
        self.document_id = str(document_id)
        self._db = db

    @property
    def messages(self) -> List[BaseMessage]:
        if self._db is not None:
            return self._load_messages(self._db)
        
        with SessionLocal() as db:
            return self._load_messages(db)

    def _load_messages(self, db: Session) -> List[BaseMessage]:
        try:
            db_msgs = (
                db.query(ChatMessage)
                .filter(ChatMessage.document_id == self.document_id)
                .order_by(ChatMessage.created_at.asc())
                .all()
            )
            langchain_msgs = []
            for msg in db_msgs:
                if msg.role == MessageRole.user:
                    langchain_msgs.append(HumanMessage(content=msg.content))
                elif msg.role == MessageRole.assistant:
                    langchain_msgs.append(AIMessage(content=msg.content))
            return langchain_msgs
        except Exception as e:
            logger.error("Failed to load chat history for document_id=%s: %s", self.document_id, e)
            return []

    def add_messages(self, messages: Sequence[BaseMessage]) -> None:
        pass

    def clear(self) -> None:
        pass

    async def aget_messages(self) -> List[BaseMessage]:
        return self.messages

    async def aadd_messages(self, messages: Sequence[BaseMessage]) -> None:
        pass

    async def aclear(self) -> None:
        pass


def get_document_language(document_id: str) -> str:
    """Retrieves document's language from relational DB and maps it to a readable name."""
    try:
        with SessionLocal() as db:
            db_doc = db.query(DbDocument).filter(DbDocument.id == document_id).first()
            if db_doc and db_doc.language:
                if db_doc.language in ("hi", "hi-Latn", "hindi", "hinglish"):
                    return "Hindi"
    except Exception as e:
        logger.error("Failed to query document language from database: %s", e)
    return "English"


def answer_question(
    document_id: str,
    question: str,
    k: int = 4,
    vector_retriever: VectorStoreInterface = default_vector_retriever,
    llm_client: LLMClientInterface = default_llm_client,
    db: Session = None
) -> dict:
    """Answers a question about a specific document by retrieving relevant chunks
    from ChromaDB and generating an answer via Groq/Gemini LLM.

    Args:
        document_id: The ID of the document in the relational database.
        question: The user's query/question.
        k: The number of top chunks to retrieve as context (default 4).
        vector_retriever: VectorStoreInterface implementation for retrieval.
        llm_client: LLMClientInterface implementation for LLM invocation.

    Returns:
        Structured response dictionary.
    """
    # Validate Input
    if not question or not question.strip():
        raise ValueError("Question cannot be empty.")
    if not document_id:
        raise ValueError("Invalid document_id")
    document_id = str(document_id)

    logger.info("Answering question for document_id=%s: '%s'", document_id, question)

    try:
        vector_store = get_vector_store()
        retriever = ScoredChromaRetriever(
            vector_store=vector_store,
            k=k,
            document_id=str(document_id),
            distance_threshold=settings.chroma_distance_threshold
        )

        llm = llm_client.get_resilient_llm()
        response_lang = get_document_language(document_id)
        qa_prompt = get_qa_prompt(response_lang)
        rephrase_prompt = get_rephrase_prompt()

        rephrase_chain = rephrase_prompt | llm | StrOutputParser()

        def get_search_query(x):
            if not x.get("chat_history"):
                return x["input"]
            return rephrase_chain.invoke(x)

        search_query_runnable = RunnableLambda(get_search_query)

        retrieve = RunnableParallel(
            context=RunnableParallel(
                input=itemgetter("input"),
                chat_history=itemgetter("chat_history"),
            )
            | search_query_runnable
            | retriever,
            input=itemgetter("input"),
            chat_history=itemgetter("chat_history"),
        )

        generate = (
            {
                "context": itemgetter("context") | format_docs_runnable,
                "input": itemgetter("input"),
                "chat_history": itemgetter("chat_history"),
            }
            | qa_prompt
            | llm
            | StrOutputParser()
        )

        rag_chain = (
            retrieve
            | RunnableParallel(
                answer=generate,
                context=itemgetter("context"),
            )
        )

        def get_session_history(session_id: str) -> BaseChatMessageHistory:
            return ChatMessageHistoryAdapter(document_id=document_id, db=db)

        chain_with_history = RunnableWithMessageHistory(
            rag_chain,
            get_session_history,
            input_messages_key="input",
            history_messages_key="chat_history",
            output_messages_key="answer",
        )

        config = {"configurable": {"session_id": f"doc_{document_id}"}}
        response = chain_with_history.invoke(
            {"input": question},
            config=config
        )

        retrieved_docs = response.get("context", [])
        answer = response.get("answer", "")

        if not retrieved_docs or "I cannot find the answer" in answer:
            confidence = "low"
        else:
            scores = [doc.metadata.get("score") for doc in retrieved_docs if doc.metadata.get("score") is not None]
            if scores:
                avg_distance = sum(scores) / len(scores)
                if avg_distance < 0.6:
                    confidence = "high"
                elif avg_distance < 1.0:
                    confidence = "medium"
                else:
                    confidence = "low"
            else:
                confidence = "medium"

        sources = []
        for doc in retrieved_docs:
            sources.append({
                "filename": doc.metadata.get("filename", ""),
                "chunk_index": doc.metadata.get("chunk_index", 0),
                "document_id": doc.metadata.get("document_id", document_id),
                "page_content": doc.page_content,
                "score": doc.metadata.get("score", 0.0),
                "page": doc.metadata.get("page", None)
            })

        return {
            "answer": answer,
            "document_id": document_id,
            "chunks_used": len(retrieved_docs),
            "confidence": confidence,
            "sources": sources
        }
    except Exception as e:
        logger.error("Failed to answer question via RAG chain: %s", e, exc_info=True)
        raise RuntimeError(f"Error answering question: {e}") from e


async def aanswer_question(
    document_id: str,
    question: str,
    k: int = 4,
    vector_retriever: VectorStoreInterface = default_vector_retriever,
    llm_client: LLMClientInterface = default_llm_client,
    db: Session = None,
    on_step = None
) -> dict:
    """Answers a question about a specific document asynchronously by retrieving relevant chunks
    from ChromaDB and generating an answer via Groq/Gemini LLM.
    """
    # Validate Input
    if not question or not question.strip():
        raise ValueError("Question cannot be empty.")
    if not document_id:
        raise ValueError("Invalid document_id")
    document_id = str(document_id)

    logger.info("Answering question asynchronously for document_id=%s: '%s'", document_id, question)

    try:
        vector_store = get_vector_store()
        retriever = ScoredChromaRetriever(
            vector_store=vector_store,
            k=k,
            document_id=str(document_id),
            distance_threshold=settings.chroma_distance_threshold
        )
        retriever.on_step = on_step

        llm = llm_client.get_resilient_llm()
        response_lang = get_document_language(document_id)
        qa_prompt = get_qa_prompt(response_lang)
        rephrase_prompt = get_rephrase_prompt()

        rephrase_chain = rephrase_prompt | llm | StrOutputParser()

        async def aget_search_query(x):
            if on_step:
                await on_step("Refining search query...")
            if not x.get("chat_history"):
                return x["input"]
            return await rephrase_chain.ainvoke(x)

        search_query_runnable = RunnableLambda(aget_search_query)

        retrieve = RunnableParallel(
            context=RunnableParallel(
                input=itemgetter("input"),
                chat_history=itemgetter("chat_history"),
            )
            | search_query_runnable
            | retriever,
            input=itemgetter("input"),
            chat_history=itemgetter("chat_history"),
        )

        async def aformat_docs_with_step(docs):
            if on_step:
                await on_step("Reading referenced sections...")
            return format_docs(docs)

        async def agenerate_response_with_step(prompt_val):
            if on_step:
                await on_step("Generating final response...")
            return await llm.ainvoke(prompt_val)

        generate = (
            {
                "context": itemgetter("context") | RunnableLambda(aformat_docs_with_step),
                "input": itemgetter("input"),
                "chat_history": itemgetter("chat_history"),
            }
            | qa_prompt
            | RunnableLambda(agenerate_response_with_step)
            | StrOutputParser()
        )

        rag_chain = (
            retrieve
            | RunnableParallel(
                answer=generate,
                context=itemgetter("context"),
            )
        )

        def get_session_history(session_id: str) -> BaseChatMessageHistory:
            return ChatMessageHistoryAdapter(document_id=document_id, db=db)

        chain_with_history = RunnableWithMessageHistory(
            rag_chain,
            get_session_history,
            input_messages_key="input",
            history_messages_key="chat_history",
            output_messages_key="answer",
        )

        config = {"configurable": {"session_id": f"doc_{document_id}"}}
        response = await chain_with_history.ainvoke(
            {"input": question},
            config=config
        )

        retrieved_docs = response.get("context", [])
        answer = response.get("answer", "")

        if not retrieved_docs or "I cannot find the answer" in answer:
            confidence = "low"
        else:
            scores = [doc.metadata.get("score") for doc in retrieved_docs if doc.metadata.get("score") is not None]
            if scores:
                avg_distance = sum(scores) / len(scores)
                if avg_distance < 0.6:
                    confidence = "high"
                elif avg_distance < 1.0:
                    confidence = "medium"
                else:
                    confidence = "low"
            else:
                confidence = "medium"

        sources = []
        for doc in retrieved_docs:
            sources.append({
                "filename": doc.metadata.get("filename", ""),
                "chunk_index": doc.metadata.get("chunk_index", 0),
                "document_id": doc.metadata.get("document_id", document_id),
                "page_content": doc.page_content,
                "score": doc.metadata.get("score", 0.0),
                "page": doc.metadata.get("page", None)
            })

        # Generate dynamic follow-up questions based on the answer and retrieved context
        suggested_questions = []
        try:
            context_text = "\n".join([doc.page_content for doc in retrieved_docs])
            followup_prompt = get_followup_questions_prompt(response_lang)
            followup_chain = followup_prompt | llm | StrOutputParser()
            
            followup_res = await followup_chain.ainvoke({
                "context": context_text[:10000],  # Keep context size reasonable
                "user_question": question,
                "assistant_answer": answer
            })
            
            import json
            import re
            cleaned_res = followup_res.strip()
            match = re.search(r"\[\s*.*?\s*\]", cleaned_res, re.DOTALL)
            if match:
                cleaned_res = match.group(0)
            
            try:
                parsed_questions = json.loads(cleaned_res)
                if isinstance(parsed_questions, list):
                    suggested_questions = [
                        q.strip("? .,:-\"'\n\r\t").strip() + "?" 
                        for q in parsed_questions 
                        if isinstance(q, str) and len(q.strip()) > 5
                    ]
            except Exception as pe:
                logger.warning("Failed to parse follow-up questions JSON: %s. Raw: %s", pe, followup_res)
                # Fallback: split by lines/bullets if JSON parsing failed
                lines = [line.strip() for line in followup_res.split("\n") if line.strip()]
                for line in lines:
                    cleaned_line = re.sub(r"^(\d+\.|\*|-)\s*", "", line).strip("? .,:-\"'\t").strip()
                    if len(cleaned_line) > 5 and len(cleaned_line) < 150:
                        suggested_questions.append(cleaned_line + "?")
        except Exception as e:
            logger.error("Failed to generate dynamic follow-up questions: %s", e)

        return {
            "answer": answer,
            "document_id": document_id,
            "chunks_used": len(retrieved_docs),
            "confidence": confidence,
            "sources": sources,
            "suggested_questions": suggested_questions[:4]
        }
    except Exception as e:
        logger.error("Failed to answer question asynchronously via RAG chain: %s", e, exc_info=True)
        raise RuntimeError(f"Error answering question: {e}") from e


def merge_risk_flags(risk_flags_list: List[List[Any]]) -> List[dict]:
    """Merges and deduplicates risk flags from different chunks, keeping the highest risk level.
    
    Level priority: 'high' > 'medium' > 'low'.
    """
    level_priority = {"high": 3, "medium": 2, "low": 1}
    merged_flags = {}
    
    for flags in risk_flags_list:
        for flag in flags:
            if hasattr(flag, "dict"):
                flag_dict = flag.dict()
            elif isinstance(flag, dict):
                flag_dict = flag
            else:
                continue
                
            clause = flag_dict.get("clause", "").strip()
            reason = flag_dict.get("reason", "").strip()
            level = str(flag_dict.get("level", "low")).strip().lower()
            
            if not clause:
                continue
                
            clause_lower = clause.lower()
            if clause_lower not in merged_flags:
                merged_flags[clause_lower] = {
                    "clause": clause,
                    "reason": reason,
                    "level": level if level in level_priority else "low"
                }
            else:
                existing_level = merged_flags[clause_lower]["level"]
                new_priority = level_priority.get(level, 1)
                existing_priority = level_priority.get(existing_level, 1)
                if new_priority > existing_priority:
                    merged_flags[clause_lower]["level"] = level
                    merged_flags[clause_lower]["reason"] = reason
                    
    return list(merged_flags.values())


def get_consolidated_summary(
    summaries: List[str], 
    response_lang: str, 
    llm_client: LLMClientInterface
) -> str:
    """Invokes the LLM to consolidate multiple chunk summaries into a single cohesive summary."""
    if not summaries:
        return ""
    if len(summaries) == 1:
        return summaries[0]
        
    combined_summaries_text = "\n\n".join(
        f"--- Section {i+1} ---\n{summary}" 
        for i, summary in enumerate(summaries) if summary.strip()
    )
    
    if not combined_summaries_text.strip():
        return ""
        
    consolidated_summary_prompt = (
        "You are an expert legal advisor and document intelligence assistant.\n"
        "Your task is to merge the following section-by-section summaries of a document into a single, cohesive, formal summary.\n"
        "The summary must detail the risks, faults, liabilities, and key obligation terms of the entire document.\n"
        "Avoid repeating identical points. Organize the final summary into logical paragraphs.\n"
        f"You MUST write the final summary in {response_lang}.\n\n"
        "Section Summaries:\n"
        f"{combined_summaries_text}\n\n"
        "Generate the consolidated summary text. Do NOT add any preamble or conversational explanation."
    )
    
    try:
        messages = [
            {"role": "system", "content": "You are a document analysis assistant."},
            {"role": "user", "content": consolidated_summary_prompt}
        ]
        return llm_client.ask(messages)
    except Exception as e:
        logger.error("Failed to consolidate summaries via LLM: %s", e)
        return "\n\n".join(summaries)


async def aget_consolidated_summary(
    summaries: List[str], 
    response_lang: str, 
    llm_client: LLMClientInterface
) -> str:
    """Invokes the LLM asynchronously to consolidate multiple chunk summaries into a single cohesive summary."""
    if not summaries:
        return ""
    if len(summaries) == 1:
        return summaries[0]
        
    combined_summaries_text = "\n\n".join(
        f"--- Section {i+1} ---\n{summary}" 
        for i, summary in enumerate(summaries) if summary.strip()
    )
    
    if not combined_summaries_text.strip():
        return ""
        
    consolidated_summary_prompt = (
        "You are an expert legal advisor and document intelligence assistant.\n"
        "Your task is to merge the following section-by-section summaries of a document into a single, cohesive, formal summary.\n"
        "The summary must detail the risks, faults, liabilities, and key obligation terms of the entire document.\n"
        "Avoid repeating identical points. Organize the final summary into logical paragraphs.\n"
        f"You MUST write the final summary in {response_lang}.\n\n"
        "Section Summaries:\n"
        f"{combined_summaries_text}\n\n"
        "Generate the consolidated summary text. Do NOT add any preamble or conversational explanation."
    )
    
    try:
        messages = [
            {"role": "system", "content": "You are a document analysis assistant."},
            {"role": "user", "content": consolidated_summary_prompt}
        ]
        return await llm_client.aask(messages)
    except Exception as e:
        logger.error("Failed to consolidate summaries asynchronously via LLM: %s", e)
        return "\n\n".join(summaries)


def generate_risk_and_draft(
    text: str, 
    language: str, 
    llm_client: LLMClientInterface = default_llm_client
) -> dict:
    """Generates risk flags and a combined summary using a hybrid chunking strategy.
    
    It cleans boilerplate, chunks the text, analyzes chunks in parallel using ThreadPoolExecutor,
    and merges the risk flags and summaries.
    """
    if not text or not text.strip():
        return {"risk_flags": [], "risk_obligation_summary": ""}

    cleaned_text = clean_boilerplate(text)
    if not cleaned_text.strip():
        cleaned_text = text

    from app.utils.text_chunking import split_text
    chunks = split_text(
        cleaned_text,
        chunk_size=12000,
        chunk_overlap=2400,
        separators=["\n\n", "\n", ". ", " ", ""]
    )
    
    if not chunks:
        return {"risk_flags": [], "risk_obligation_summary": ""}

    is_hindi = language in ("hi", "hi-Latn", "hindi", "hinglish")
    response_lang = "Hindi (in Devanagari script)" if is_hindi else "English"

    # Set up parser and chain
    parser = JsonOutputParser(pydantic_object=RiskAnalysisAndDraft)
    fixing_parser = OutputFixingParser.from_llm(
        parser=parser,
        llm=llm_client.get_primary_llm()
    )
    prompt = get_risk_analysis_prompt(response_lang, is_truncated=False).partial(
        format_instructions=parser.get_format_instructions()
    )
    llm = llm_client.get_resilient_llm()
    chain = prompt | llm | fixing_parser

    # Process only up to 15 chunks
    max_chunks = 15
    chunks_to_process = chunks[:max_chunks]
    
    logger.info(f"Generating risk analysis for {len(chunks_to_process)} chunks in parallel...")

    def analyze_chunk(chunk_text: str, chunk_index: int) -> dict:
        chunk_snippet = chunk_text[:100].replace('\n', ' ')
        try:
            logger.info(f"Analyzing risks for chunk {chunk_index + 1}/{len(chunks_to_process)} (len={len(chunk_text)}, snippet='{chunk_snippet}')...")
            result = chain.invoke({"context": chunk_text})
            
            if hasattr(result, "dict"):
                result_dict = result.dict()
            elif isinstance(result, dict):
                result_dict = result
            else:
                result_dict = dict(result)
                
            if "risk_flags" not in result_dict:
                result_dict["risk_flags"] = []
            if "risk_obligation_summary" not in result_dict:
                result_dict["risk_obligation_summary"] = ""
                
            logger.info(f"Successfully analyzed risks for chunk {chunk_index + 1}/{len(chunks_to_process)}.")
            return result_dict
        except Exception as e:
            logger.error(
                f"Failed risk analysis on chunk {chunk_index + 1}/{len(chunks_to_process)} "
                f"(len={len(chunk_text)}, snippet='{chunk_snippet}'): {e}", 
                exc_info=True
            )
            return {"risk_flags": [], "risk_obligation_summary": ""}

    all_chunk_results = []
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(analyze_chunk, chunk, idx): idx for idx, chunk in enumerate(chunks_to_process)}
        for future in as_completed(futures):
            chunk_idx = futures[future]
            try:
                res = future.result()
                all_chunk_results.append(res)
            except Exception as e:
                logger.error(f"Thread for risk analysis chunk {chunk_idx + 1} raised an exception: {e}")

    if not all_chunk_results:
        return {"risk_flags": [], "risk_obligation_summary": "Failed to analyze document risks."}

    # Merge risk flags
    all_risk_flags = [res.get("risk_flags", []) for res in all_chunk_results]
    merged_risk_flags = merge_risk_flags(all_risk_flags)

    # Merge and consolidate summaries
    all_summaries = [res.get("risk_obligation_summary", "") for res in all_chunk_results if res.get("risk_obligation_summary", "")]
    consolidated_summary = get_consolidated_summary(all_summaries, response_lang, llm_client)

    return {
        "risk_flags": merged_risk_flags,
        "risk_obligation_summary": consolidated_summary
    }


async def agenerate_risk_and_draft(
    text: str, 
    language: str, 
    llm_client: LLMClientInterface = default_llm_client
) -> dict:
    """Generates risk flags and a combined summary asynchronously using a hybrid chunking strategy.
    
    It cleans boilerplate, chunks the text, analyzes chunks concurrently,
    and merges the risk flags and summaries.
    """
    if not text or not text.strip():
        return {"risk_flags": [], "risk_obligation_summary": ""}

    cleaned_text = clean_boilerplate(text)
    if not cleaned_text.strip():
        cleaned_text = text

    from app.utils.text_chunking import split_text
    chunks = split_text(
        cleaned_text,
        chunk_size=12000,
        chunk_overlap=2400,
        separators=["\n\n", "\n", ". ", " ", ""]
    )
    
    if not chunks:
        return {"risk_flags": [], "risk_obligation_summary": ""}

    is_hindi = language in ("hi", "hi-Latn", "hindi", "hinglish")
    response_lang = "Hindi (in Devanagari script)" if is_hindi else "English"

    # Set up parser and chain
    parser = JsonOutputParser(pydantic_object=RiskAnalysisAndDraft)
    fixing_parser = OutputFixingParser.from_llm(
        parser=parser,
        llm=llm_client.get_primary_llm()
    )
    prompt = get_risk_analysis_prompt(response_lang, is_truncated=False).partial(
        format_instructions=parser.get_format_instructions()
    )
    llm = llm_client.get_resilient_llm()
    chain = prompt | llm | fixing_parser

    # Process only up to 15 chunks
    max_chunks = 15
    chunks_to_process = chunks[:max_chunks]
    
    logger.info(f"Generating risk analysis asynchronously for {len(chunks_to_process)} chunks in parallel...")

    async def analyze_chunk(chunk_text: str, chunk_index: int) -> dict:
        chunk_snippet = chunk_text[:100].replace('\n', ' ')
        try:
            logger.info(f"Analyzing risks for chunk {chunk_index + 1}/{len(chunks_to_process)} (len={len(chunk_text)}, snippet='{chunk_snippet}')...")
            result = await chain.ainvoke({"context": chunk_text})
            
            if hasattr(result, "dict"):
                result_dict = result.dict()
            elif isinstance(result, dict):
                result_dict = result
            else:
                result_dict = dict(result)
                
            if "risk_flags" not in result_dict:
                result_dict["risk_flags"] = []
            if "risk_obligation_summary" not in result_dict:
                result_dict["risk_obligation_summary"] = ""
                
            logger.info(f"Successfully analyzed risks for chunk {chunk_index + 1}/{len(chunks_to_process)}.")
            return result_dict
        except Exception as e:
            logger.error(
                f"Failed risk analysis on chunk {chunk_index + 1}/{len(chunks_to_process)} "
                f"(len={len(chunk_text)}, snippet='{chunk_snippet}'): {e}", 
                exc_info=True
            )
            return {"risk_flags": [], "risk_obligation_summary": ""}

    tasks = [analyze_chunk(chunk, idx) for idx, chunk in enumerate(chunks_to_process)]
    all_chunk_results = await asyncio.gather(*tasks)

    if not all_chunk_results:
        return {"risk_flags": [], "risk_obligation_summary": "Failed to analyze document risks."}

    # Merge risk flags
    all_risk_flags = [res.get("risk_flags", []) for res in all_chunk_results]
    merged_risk_flags = merge_risk_flags(all_risk_flags)

    # Merge and consolidate summaries
    all_summaries = [res.get("risk_obligation_summary", "") for res in all_chunk_results if res.get("risk_obligation_summary", "")]
    consolidated_summary = await aget_consolidated_summary(all_summaries, response_lang, llm_client)

    return {
        "risk_flags": merged_risk_flags,
        "risk_obligation_summary": consolidated_summary
    }
