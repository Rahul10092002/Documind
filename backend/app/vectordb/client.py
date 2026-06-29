from abc import ABC, abstractmethod
from typing import List


class VectorStoreClient(ABC):
    """Abstract interface — swap ChromaDB for Qdrant without changing agents."""

    @abstractmethod
    async def add_documents(
        self,
        texts: List[str],
        embeddings: List[List[float]],
        metadata: List[dict],
        collection_id: str,
    ) -> None: ...

    @abstractmethod
    async def similarity_search(
        self,
        query_embedding: List[float],
        collection_id: str,
        k: int = 5,
    ) -> List[dict]: ...

    @abstractmethod
    async def delete_collection(self, collection_id: str) -> None: ...


class ChromaVectorClient(VectorStoreClient):
    """Phase 1 — local dev and capstone demo."""

    def __init__(self, persist_dir: str = "./chroma_db"):
        import chromadb
        self.client = chromadb.PersistentClient(path=persist_dir)

    async def add_documents(self, texts, embeddings, metadata, collection_id):
        col = self.client.get_or_create_collection(collection_id)
        col.add(
            documents=texts,
            embeddings=embeddings,
            metadatas=metadata,
            ids=[str(m.get("chunk_id", i)) for i, m in enumerate(metadata)],
        )

    async def similarity_search(self, query_embedding, collection_id, k=5):
        col = self.client.get_or_create_collection(collection_id)
        results = col.query(query_embeddings=[query_embedding], n_results=k)
        return results["documents"][0] if results["documents"] else []

    async def delete_collection(self, collection_id: str):
        self.client.delete_collection(collection_id)
