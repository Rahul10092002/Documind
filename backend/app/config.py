import logging
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import find_dotenv

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=find_dotenv(),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    groq_api_key: str | None = None
    google_api_key: str | None = None
    gemini_api_key: str | None = None
    llm_provider: str = "groq"
    llm_model: str = "llama-3.3-70b-versatile"
    gemini_model: str = "gemini-2.5-flash"
    temperature: float = 0.0
    chroma_distance_threshold: float = 1.2
    max_context_chars: int = 12000
    enable_gemini_fallback: bool = True
    database_url: str | None = None
    chroma_path: str = "chroma_db"
    chroma_collection_name: str = "documents"
    embedding_model_name: str = "all-MiniLM-L6-v2"
    # Explicit CORS origin allowlist. Override via CORS_ORIGINS env var
    # (comma-separated for multiple origins, e.g.
    # "http://localhost:3000,https://app.yourdomain.com").
    # Never use ["*"] with allow_credentials=True — it is both invalid per the
    # CORS spec and a security vulnerability.
    cors_origins: list[str] = ["http://localhost:3000"]

    @property
    def effective_google_api_key(self) -> str | None:
        return self.google_api_key or self.gemini_api_key

# Global settings instance
settings = Settings()
