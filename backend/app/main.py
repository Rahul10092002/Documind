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

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import engine, get_db
import app.models as models  # noqa: F401 — registers all ORM classes with Base
from app.routers import documents
from app.utils import get_collection

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

    yield
    # Shutdown — nothing to clean up yet


app = FastAPI(title="DocuMind API", lifespan=lifespan)
main = app

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

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(documents.router)


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        logger.info("Database connection: OK")
        return {"status": "ok", "message": "success"}
    except Exception as e:
        logger.error("Database connection FAILED: %s", e)
        raise HTTPException(status_code=503, detail="Database unavailable")
