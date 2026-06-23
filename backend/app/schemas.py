from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models import DocumentStatus


class DocumentOut(BaseModel):
    """Response schema returned after a successful document upload."""

    id: int
    filename: str
    upload_date: datetime
    language: Optional[str]
    status: DocumentStatus

    model_config = {"from_attributes": True}


class ChatRequest(BaseModel):
    """Input request schema for document Q&A chat endpoint."""
    question: str


class ChatResponse(BaseModel):
    """Response schema returned from document Q&A chat endpoint."""
    answer: str
    document_id: int
    chunks_used: int
    confidence: str
    sources: list[dict]


class AnalysisResultOut(BaseModel):
    """Response schema returned after document analysis."""
    document_id: int
    extracted_entities: dict
    risk_flags: Optional[list[dict]] = None
    draft_text: Optional[str] = None

    model_config = {"from_attributes": True}

