import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.dependencies import get_db_session as get_db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])

@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        logger.info("Database connection: OK")
        return {"status": "ok", "message": "success"}
    except Exception as e:
        logger.error("Database connection FAILED: %s", e)
        raise HTTPException(status_code=503, detail="Database unavailable")

@router.get("/ready")
def ready_check(db: Session = Depends(get_db)):
    # Check Database
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        logger.error("Readiness check - Database FAILED: %s", e)
        raise HTTPException(status_code=503, detail="Database unavailable")
        
    # Check ChromaDB
    try:
        from app.vectordb.vector_store import get_collection
        get_collection()
    except Exception as e:
        logger.error("Readiness check - Vector store FAILED: %s", e)
        raise HTTPException(status_code=503, detail="Vector store unavailable")
        
    return {"status": "ready"}

@router.get("/metrics")
def metrics():
    return {
        "status": "healthy",
        "metrics": {
            "uptime": "active"
        }
    }
