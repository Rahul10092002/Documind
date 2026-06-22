import logging
import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from app.utils.vector_store import get_collection

# Load environment variables using absolute path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
dotenv_path = os.path.join(backend_dir, ".env")
load_dotenv(dotenv_path=dotenv_path)

logger = logging.getLogger(__name__)


def answer_question(document_id: int, question: str, k: int = 4) -> str:
    """Answers a question about a specific document by retrieving relevant chunks
    from ChromaDB and generating an answer via Groq's Llama-3.3-70b model.

    Args:
        document_id: The ID of the document in the relational database.
        question: The user's query/question.
        k: The number of top chunks to retrieve as context (default 4).

    Returns:
        The generated answer string.
    """
    logger.info("Answering question for document_id=%d: '%s'", document_id, question)

    # 1. Retrieve collection
    collection = get_collection()

    # 2. Query collection filtered by document_id
    try:
        # ChromaDB queries using the configured embedding function automatically
        results = collection.query(
            query_texts=[question],
            where={"document_id": document_id},
            n_results=k
        )
    except Exception as e:
        logger.error("Failed to query ChromaDB for document_id=%d: %s", document_id, e)
        raise RuntimeError(f"Error querying vector database: {e}") from e

    # 3. Compile context from retrieved chunks
    documents = results.get("documents", [])
    retrieved_chunks = documents[0] if documents else []

    if not retrieved_chunks:
        logger.warning("No context chunks retrieved for document_id=%d and query: '%s'", document_id, question)
        return "I cannot find the answer in the provided document context (no relevant sections were found)."

    context = "\n\n".join(retrieved_chunks)
    logger.info("Retrieved %d context chunks for document_id=%d", len(retrieved_chunks), document_id)

    # 4. Initialize Groq model via langchain-groq
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        logger.error("GROQ_API_KEY environment variable is not set.")
        raise ValueError("GROQ_API_KEY is not configured in the environment.")

    try:
        # langchain-groq client uses GROQ_API_KEY automatically from environment
        llm = ChatGroq(
            model="llama-3.3-70b-versatile",
            temperature=0.0
        )
    except Exception as e:
        logger.error("Failed to initialize ChatGroq client: %s", e)
        raise RuntimeError(f"Error initializing LLM client: {e}") from e

    # 5. Build prompt with context
    system_prompt = (
        "You are a helpful AI assistant. Answer the user's question based strictly on the provided context. "
        "If the context does not contain the answer, say 'I cannot find the answer in the provided document context.' "
        "Do not make up or extrapolate facts.\n\n"
        f"Context:\n{context}"
    )

    messages = [
        ("system", system_prompt),
        ("human", f"Question: {question}")
    ]

    # 6. Call Groq API
    try:
        response = llm.invoke(messages)
        return str(response.content).strip()
    except Exception as e:
        logger.error("Failed to get answer from Groq LLM: %s", e)
        raise RuntimeError(f"Error generating answer from LLM: {e}") from e
