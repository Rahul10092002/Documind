import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)

from sqlalchemy.orm import relationship

from app.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class DocumentStatus(str, enum.Enum):
    """Lifecycle states for an uploaded document.

    States:
        pending: Reserved for future asynchronous task queue architectures (e.g. background
                 processing workers) when a document is uploaded but processing has not yet begun.
        processing: The document text is currently being extracted, chunked, and analyzed.
        completed: The document has been successfully indexed and analyzed.
        failed: The document processing or indexing failed.
    """
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class MessageRole(str, enum.Enum):
    """Who sent a chat message."""
    user = "user"
    assistant = "assistant"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class Document(Base):
    """Represents an uploaded document and its raw extracted text."""

    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    filename = Column(String(255), nullable=False)
    # Exact path to the uploaded PDF on disk. Stored at upload time so file
    # lookup is O(1) and never ambiguous (no fuzzy mtime matching required).
    # Nullable for backwards compatibility with rows created before this column existed.
    file_path = Column(String(512), nullable=True)
    upload_date = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    language = Column(String(10), nullable=True)          # e.g. "en", "fr"
    raw_text = Column(Text, nullable=True)
    status = Column(
        Enum(DocumentStatus, name="documentstatus"),
        nullable=False,
        default=DocumentStatus.pending,
    )
    detailed_status = Column(String(255), nullable=True)

    # Relationships
    analysis_result = relationship(
        "AnalysisResult",
        back_populates="document",
        uselist=False,          # one-to-one
        cascade="all, delete-orphan",
    )
    chat_messages = relationship(
        "ChatMessage",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )

    def __repr__(self) -> str:
        return f"<Document id={self.id} filename={self.filename!r} status={self.status}>"


class AnalysisResult(Base):
    """Stores AI-generated analysis for a document (one-to-one with Document)."""

    __tablename__ = "analysis_results"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(
        String(36),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,            # enforces one-to-one at the DB level
        index=True,
    )
    extracted_entities = Column(JSON, nullable=True)    # e.g. [{"type": "ORG", "text": "Acme"}]
    risk_flags = Column(JSON, nullable=True)            # e.g. [{"level": "high", "reason": "..."}]
    risk_obligation_summary = Column(Text, nullable=True)

    # Relationship
    document = relationship("Document", back_populates="analysis_result")

    def __repr__(self) -> str:
        return f"<AnalysisResult id={self.id} document_id={self.document_id}>"


class ChatMessage(Base):
    """Individual message in the per-document chat history."""

    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(
        String(36),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(
        Enum(MessageRole, name="messagerole"),
        nullable=False,
    )
    content = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationship
    document = relationship("Document", back_populates="chat_messages")

    def __repr__(self) -> str:
        return f"<ChatMessage id={self.id} role={self.role} document_id={self.document_id}>"
