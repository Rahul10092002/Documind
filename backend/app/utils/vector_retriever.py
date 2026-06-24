import logging
from abc import ABC, abstractmethod
from app.config import settings
from app.utils.vector_store import get_vector_store

logger = logging.getLogger(__name__)

class VectorStoreInterface(ABC):
    @abstractmethod
    def retrieve_chunks(self, document_id: str, question: str, k: int = 4) -> list[dict]:
        pass

    @abstractmethod
    async def aretrieve_chunks(self, document_id: str, question: str, k: int = 4) -> list[dict]:
        pass


class ChromaVectorRetriever(VectorStoreInterface):
    def retrieve_chunks(self, document_id: str, question: str, k: int = 4) -> list[dict]:
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
            logger.error("Failed to query ChromaDB for document_id=%s: %s", document_id, e)
            raise RuntimeError(f"Error querying vector database: {e}") from e

        distances = [score for _, score in results]
        logger.info("Retrieved %d chunks raw. Distances=%s", len(results), distances)

        # Filter low-similarity results
        filtered_chunks = []
        for doc, score in results:
            if score < settings.chroma_distance_threshold:
                filtered_chunks.append({
                    "page_content": doc.page_content,
                    "metadata": doc.metadata,
                    "score": score
                })

        logger.info(
            "Retrieved %d chunks after distance filter (<%s). Distances=%s",
            len(filtered_chunks),
            settings.chroma_distance_threshold,
            [c["score"] for c in filtered_chunks]
        )
        return filtered_chunks

    async def aretrieve_chunks(self, document_id: str, question: str, k: int = 4) -> list[dict]:
        """Queries the LangChain Chroma vector store asynchronously, logging distance statistics and filtering outliers."""
        vector_store = get_vector_store()
        try:
            # asimilarity_search_with_score returns list[tuple[Document, float]]
            results = await vector_store.asimilarity_search_with_score(
                query=question,
                k=k,
                filter={"document_id": document_id}
            )
        except Exception as e:
            logger.error("Failed to query ChromaDB for document_id=%s: %s", document_id, e)
            raise RuntimeError(f"Error querying vector database: {e}") from e

        distances = [score for _, score in results]
        logger.info("Retrieved %d chunks raw. Distances=%s", len(results), distances)

        # Filter low-similarity results
        filtered_chunks = []
        for doc, score in results:
            if score < settings.chroma_distance_threshold:
                filtered_chunks.append({
                    "page_content": doc.page_content,
                    "metadata": doc.metadata,
                    "score": score
                })

        logger.info(
            "Retrieved %d chunks after distance filter (<%s). Distances=%s",
            len(filtered_chunks),
            settings.chroma_distance_threshold,
            [c["score"] for c in filtered_chunks]
        )
        return filtered_chunks

# Default retriever instance
default_vector_retriever = ChromaVectorRetriever()
