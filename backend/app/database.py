import logging
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text 
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import declarative_base, sessionmaker

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
dotenv_path = os.path.join(backend_dir, ".env")
load_dotenv(dotenv_path=dotenv_path)

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)

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
