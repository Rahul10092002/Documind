from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models import DocumentStatus, MessageRole


class DocumentOut(BaseModel):
    """Response schema returned after a successful document upload."""

    id: str
    filename: str
    file_path: Optional[str] = None
    upload_date: datetime
    language: Optional[str]
    status: DocumentStatus
    detailed_status: Optional[str] = None
    raw_text: Optional[str] = None

    model_config = {"from_attributes": True}


class DocumentSummaryOut(BaseModel):
    """Response schema returned for listing documents (excludes raw_text)."""

    id: str
    filename: str
    upload_date: datetime
    language: Optional[str]
    status: DocumentStatus
    detailed_status: Optional[str] = None

    model_config = {"from_attributes": True}


class ChatRequest(BaseModel):
    """Input request schema for document Q&A chat endpoint."""
    question: str = Field(
        min_length=1,
        max_length=2000,
        description="The question to ask about the document (1–2000 characters)."
    )


class ChatResponse(BaseModel):
    """Response schema returned from document Q&A chat endpoint."""
    answer: str
    document_id: str
    chunks_used: int
    confidence: str
    sources: list[dict]
    suggested_questions: list[str] = []


class ChatMessageOut(BaseModel):
    """Response schema representing a single message in a document's chat history."""

    id: int
    document_id: str
    role: MessageRole
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AnalysisResultOut(BaseModel):
    """Response schema returned after document analysis."""
    document_id: str
    extracted_entities: dict
    risk_flags: Optional[list[dict]] = None
    risk_obligation_summary: Optional[str] = None

    model_config = {"from_attributes": True}

