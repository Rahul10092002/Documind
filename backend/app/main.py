import logging
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

# ── Logging setup ─────────────────────────────────────────────────────────────
# Configure the root logger so that all app.* module loggers emit INFO and
# above.  Uvicorn's own access logger (uvicorn.access) is unaffected — it has
# its own handler configured by uvicorn at startup.
# httpx / httpcore are pinned to WARNING to suppress connection-level chatter.
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s: %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("groq").setLevel(logging.WARNING)
logging.getLogger("google").setLevel(logging.WARNING)
logging.getLogger("google_genai").setLevel(logging.WARNING)
# ─────────────────────────────────────────────────────────────────────────────

from contextlib import asynccontextmanager

from app.config import settings

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import engine, get_db
from app.exceptions import DocuMindBaseError
import app.models as models  # noqa: F401 — registers all ORM classes with Base
from app.routers import documents, extraction, reports, health
from app.vectordb import get_collection

logger = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle handler.

    Startup:
      1. Create all relational database tables (idempotent).
      2. Initialize the ChromaDB persistent client and collection.
    Shutdown:
      Add any cleanup logic (connection pool teardown, etc.) below the yield.
    """
    # Startup
    models.Base.metadata.create_all(bind=engine)
    logger.info("Database tables created / verified.")

    # Run self-healing migration to add new columns if not present
    try:
        from sqlalchemy import inspect, text
        inspector = inspect(engine)
        columns = [col["name"] for col in inspector.get_columns("analysis_results")]
        if "risk_obligation_summary" not in columns:
            logger.info("Migrating database: adding risk_obligation_summary column to analysis_results")
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE analysis_results ADD COLUMN risk_obligation_summary TEXT"))
        
        doc_columns = [col["name"] for col in inspector.get_columns("documents")]
        if "detailed_status" not in doc_columns:
            logger.info("Migrating database: adding detailed_status column to documents")
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE documents ADD COLUMN detailed_status VARCHAR(255)"))
    except Exception as exc:
        logger.error("Failed to run database migrations: %s", exc)

    try:
        get_collection()
        logger.info("ChromaDB connection and collection initialized / verified.")
    except Exception as e:
        logger.error("Failed to initialize ChromaDB collection: %s", e)
        raise e

    # Pre-load spaCy models at server startup to prevent per-request cold start (2-3s delay)
    try:
        logger.info("Pre-loading spaCy models (xx_ent_wiki_sm & en_core_web_lg) on server startup...")
        from app.agents.extraction_agent import get_spacy_model
        get_spacy_model("hindi")
        get_spacy_model("english")
        logger.info("spaCy models pre-loaded and cached successfully.")
    except Exception as e:
        logger.warning("Failed to pre-load spaCy models at server startup: %s", e)

    yield
    # Shutdown — nothing to clean up yet


app = FastAPI(title="DocuMind API", lifespan=lifespan)
main = app

@app.exception_handler(DocuMindBaseError)
async def documind_exception_handler(request: Request, exc: DocuMindBaseError):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "error_type": type(exc).__name__,
        },
    )

# ── CORS ──────────────────────────────────────────────────────────────────────
# WARNING: allow_origins=["*"] combined with allow_credentials=True is invalid
# per the CORS spec and is a security vulnerability. Always use an explicit
# origin allowlist when credentials (cookies / Authorization headers) are sent.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.middleware.logging import logging_middleware
app.middleware("http")(logging_middleware)

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(documents.router)
app.include_router(extraction.router)
app.include_router(reports.router)
app.include_router(health.router)
