import logging
import os

from sqlalchemy import create_engine, text 
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)

DATABASE_URL = settings.database_url
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

try:
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL is not set.")
    engine = create_engine(DATABASE_URL)
    # Trigger a connection attempt immediately to verify availability
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    logger.info("Connected to primary database successfully.")
except (OperationalError, Exception) as e:
    logger.warning(
        "Could not connect to database at '%s'. Falling back to local SQLite database 'documind.db'. Error: %s",
        DATABASE_URL,
        e
    )
    sqlite_path = os.path.join(backend_dir, "documind.db")
    sqlite_url = f"sqlite:///{sqlite_path}"
    engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a database session and ensures it is closed.
    Logs whether the connection to the database was successful on each call.
    """
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        logger.info("Database connection: OK")
        yield db
    except OperationalError as e:
        logger.error("Database connection FAILED: %s", e.orig)
        db.close()
        raise
    finally:
        db.close()
