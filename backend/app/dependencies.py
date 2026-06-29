from typing import Generator
from app.database import SessionLocal
from sqlalchemy.orm import Session
from app.llm import default_llm_client
from app.llm.llm_client import ConfiguredLLMClient

def get_db_session() -> Generator[Session, None, None]:
    """Dependency injection provider for SQLAlchemy database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

from app.config import settings
from app.vectordb import VectorStoreClient, ChromaVectorClient

def get_llm_client() -> ConfiguredLLMClient:
    """Singleton LLM client injected into routes."""
    return default_llm_client

def get_vector_client() -> VectorStoreClient:
    """Singleton Vector Store client injected into routes/agents."""
    return ChromaVectorClient(persist_dir=settings.chroma_path)
