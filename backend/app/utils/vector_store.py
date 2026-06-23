import logging
import os
from dotenv import load_dotenv
import chromadb
from chromadb.utils import embedding_functions
from langchain_community.vectorstores import Chroma
from langchain_core.embeddings import Embeddings

# Resolve absolute path to ensure database is created and dotenv is loaded in the correct backend workspace directory
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
dotenv_path = os.path.join(backend_dir, ".env")
load_dotenv(dotenv_path=dotenv_path)

logger = logging.getLogger(__name__)

# Configure ChromaDB Settings
CHROMA_PATH = os.getenv("CHROMA_PATH", "chroma_db")
CHROMA_COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME", "documents")
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")

# Resolve absolute path to ensure database is created in the correct backend workspace directory
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
chroma_dir = os.path.join(backend_dir, CHROMA_PATH)

logger.info("Initializing ChromaDB PersistentClient at path: %s", chroma_dir)

try:
    chroma_client = chromadb.PersistentClient(path=chroma_dir)
except Exception as e:
    logger.error("Failed to initialize ChromaDB PersistentClient: %s", e)
    raise

_embedding_function = None


def get_collection():
    """Retrieves or creates the ChromaDB collection using the defined embedding function."""
    global _embedding_function
    if _embedding_function is None:
        try:
            logger.info("Initializing SentenceTransformerEmbeddingFunction with model: %s", EMBEDDING_MODEL_NAME)
            _embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=EMBEDDING_MODEL_NAME
            )
        except Exception as e:
            logger.error("Failed to initialize SentenceTransformerEmbeddingFunction with model %s: %s", EMBEDDING_MODEL_NAME, e)
            raise

    try:
        collection = chroma_client.get_or_create_collection(
            name=CHROMA_COLLECTION_NAME,
            embedding_function=_embedding_function
        )
        return collection
    except Exception as e:
        logger.error("Failed to get or create ChromaDB collection '%s': %s", CHROMA_COLLECTION_NAME, e)
        raise


def add_document_chunks(document_id: int, chunks: list[str], filename: str) -> None:
    """Indexes document text chunks in ChromaDB.

    Args:
        document_id: The ID of the document in the primary database.
        chunks: List of text strings to index.
        filename: Name of the original document.
    """
    if not chunks:
        logger.warning("No chunks provided to index for document_id: %d", document_id)
        return

    collection = get_collection()

    ids = [f"{document_id}_chunk_{i}" for i in range(len(chunks))]
    metadatas = [
        {"document_id": document_id, "filename": filename, "chunk_index": i}
        for i in range(len(chunks))
    ]

    try:
        collection.add(
            documents=chunks,
            metadatas=metadatas,
            ids=ids
        )
        logger.info("Indexed %d chunks for document_id=%d in ChromaDB.", len(chunks), document_id)
    except Exception as e:
        logger.error("Failed to index chunks for document_id=%d in ChromaDB: %s", document_id, e)
        raise


def delete_document_chunks(document_id: int) -> None:
    """Deletes all chunks belonging to a document from ChromaDB.

    Args:
        document_id: The ID of the document to delete chunks for.
    """
    collection = get_collection()
    try:
        collection.delete(where={"document_id": document_id})
        logger.info("Deleted chunks for document_id=%d from ChromaDB.", document_id)
    except Exception as e:
        logger.error("Failed to delete chunks for document_id=%d from ChromaDB: %s", document_id, e)
        raise


class ChromaEmbeddingWrapper(Embeddings):
    """Wraps Chroma's custom SentenceTransformerEmbeddingFunction into a LangChain Embeddings-compatible interface."""
    def __init__(self, chroma_embedding_fn):
        self.fn = chroma_embedding_fn

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.fn(texts)

    def embed_query(self, text: str) -> list[float]:
        return self.fn([text])[0]


_vector_store = None


def get_vector_store() -> Chroma:
    """Returns a cached LangChain Chroma vector store instance, reusing the persistent client."""
    global _vector_store
    if _vector_store is None:
        # get_collection() ensures both collection and _embedding_function are initialized
        get_collection()
        embeddings = ChromaEmbeddingWrapper(_embedding_function)
        _vector_store = Chroma(
            client=chroma_client,
            collection_name=CHROMA_COLLECTION_NAME,
            embedding_function=embeddings
        )
    return _vector_store

