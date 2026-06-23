import logging
import os
from dotenv import load_dotenv

# Load environment variables from .env file using absolute path before any other app modules are imported
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
dotenv_path = os.path.join(backend_dir, ".env")
load_dotenv(dotenv_path=dotenv_path)

from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import engine, get_db
import app.models as models  # noqa: F401 — registers all ORM classes with Base
from app.routers import documents
from app.utils import get_collection

app = FastAPI(title="DocuMind API")
main = app
logger = logging.getLogger(__name__)

# ── Routers ──────────────────────────────────────────────────────────────────
app.include_router(documents.router)


# ── Startup ───────────────────────────────────────────────────────────────────
@app.on_event("startup")
def startup_event() -> None:
    """Run startup checks and initialization tasks:
    1. Create all relational database tables.
    2. Initialize ChromaDB persistent client and collection.
    """
    models.Base.metadata.create_all(bind=engine)
    logger.info("Database tables created / verified.")
    
    try:
        get_collection()
        logger.info("ChromaDB connection and collection initialized / verified.")
    except Exception as e:
        logger.error("Failed to initialize ChromaDB collection: %s", e)
        raise e


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        logger.info("Database connection: OK")
        return {"status": "ok", "message": "success"}
    except Exception as e:
        logger.error("Database connection FAILED: %s", e)
        return {"status": "error", "message": "error"}
