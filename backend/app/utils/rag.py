import logging
import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from tenacity import retry, stop_after_attempt, wait_exponential
from app.utils.vector_store import get_vector_store

# Load environment variables using absolute path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
dotenv_path = os.path.join(backend_dir, ".env")
load_dotenv(dotenv_path=dotenv_path)

logger = logging.getLogger(__name__)

# Global cache for ChatGroq LLM
_llm = None


def get_llm() -> ChatGroq:
    """Returns a cached ChatGroq instance, configured via environment variables."""
    global _llm
    if _llm is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            logger.error("GROQ_API_KEY environment variable is not set.")
            raise ValueError("GROQ_API_KEY is not configured in the environment.")

        model_name = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
        logger.info("Initializing ChatGroq client with model: %s", model_name)
        _llm = ChatGroq(
            model=model_name,
            temperature=0.0
        )
    return _llm


def retrieve_chunks(document_id: int, question: str, k: int = 4) -> list[dict]:
    """Queries the LangChain Chroma vector store, logging distance statistics and filtering outliers."""
    vector_store = get_vector_store()
    try:
        # similarity_search_with_score returns list[tuple[Document, float]]
        results = vector_store.similarity_search_with_score(
            query=question,
            k=k,
            filter={"document_id": document_id}
        )
    except Exception as e:
        logger.error("Failed to query ChromaDB for document_id=%d: %s", document_id, e)
        raise RuntimeError(f"Error querying vector database: {e}") from e

    distances = [score for _, score in results]
    logger.info("Retrieved %d chunks raw. Distances=%s", len(results), distances)

    # Filter low-similarity results (threshold < 1.2)
    filtered_chunks = []
    for doc, score in results:
        if score < 1.2:
            filtered_chunks.append({
                "page_content": doc.page_content,
                "metadata": doc.metadata,
                "score": score
            })

    logger.info(
        "Retrieved %d chunks after distance filter (<1.2). Distances=%s",
        len(filtered_chunks),
        [c["score"] for c in filtered_chunks]
    )
    return filtered_chunks


def build_context(retrieved_chunks: list[dict], max_chars: int = 12000) -> str:
    """Concatenates the chunk contents until the max character limit is reached."""
    context = ""
    for chunk in retrieved_chunks:
        content = chunk["page_content"]
        if len(context) + len(content) > max_chars:
            logger.warning("Context truncated to stay under MAX_CONTEXT_CHARS (%d)", max_chars)
            break
          
        context += content + "\n\n"
    return context.strip()


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True
)
def ask_llm(messages) -> str:
    """Invokes LLM with automatic retry logic for network or server errors."""
    llm = get_llm()
    response = llm.invoke(messages)
    return str(response.content).strip()


def generate_answer(context: str, question: str) -> str:
    """Constructs prompt using ChatPromptTemplate and generates answer using prompt | llm composition."""
    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            """You are a document question answering assistant.

Rules:
1. Use ONLY the provided context.
2. Never use outside knowledge.
3. If the answer is not present in the provided context, reply exactly: "I cannot find the answer in the provided document context."
4. If multiple sections mention the answer, combine them.
5. If unsure, say you don't know.
6. Quote important values exactly.
7. Keep answers concise.

Context:
{context}"""
        ),
        ("human", "{question}")
    ])

    messages = prompt.invoke({
        "context": context,
        "question": question
    })

    try:
        return ask_llm(messages)
    except Exception as e:
        logger.error("Failed to generate answer from Groq LLM: %s", e)
        raise RuntimeError(f"Error generating answer from LLM: {e}") from e


def answer_question(document_id: int, question: str, k: int = 4) -> dict:
    """Answers a question about a specific document by retrieving relevant chunks
    from ChromaDB and generating an answer via Groq LLM.

    Args:
        document_id: The ID of the document in the relational database.
        question: The user's query/question.
        k: The number of top chunks to retrieve as context (default 4).

    Returns:
        Structured response dictionary.
    """
    # Validate Input
    if not question or not question.strip():
        raise ValueError("Question cannot be empty.")
    if document_id <= 0:
        raise ValueError("Invalid document_id")

    logger.info("Answering question for document_id=%d: '%s'", document_id, question)

    # 1. Retrieve chunks
    retrieved_chunks = retrieve_chunks(document_id, question, k)

    if not retrieved_chunks:
        logger.warning("No context chunks retrieved for document_id=%d and query: '%s'", document_id, question)
        return {
            "answer": "I cannot find the answer in the provided document context.",
            "document_id": document_id,
            "chunks_used": 0,
            "confidence": "low",
            "sources": []
        }

    # 2. Compile context
    context = build_context(retrieved_chunks)

    # 3. Generate answer
    answer = generate_answer(context, question)

    # Calculate average distance for confidence estimation
    if "I cannot find the answer in the provided document context." in answer:
        confidence = "low"
    else:
        avg_distance = sum(c["score"] for c in retrieved_chunks) / len(retrieved_chunks)
        if avg_distance < 0.6:
            confidence = "high"
        elif avg_distance < 1.0:
            confidence = "medium"
        else:
            confidence = "low"

    return {
        "answer": answer,
        "document_id": document_id,
        "chunks_used": len(retrieved_chunks),
        "confidence": confidence,
        "sources": [c["metadata"] for c in retrieved_chunks]
    }
