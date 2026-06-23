import logging
from pathlib import Path
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Document, DocumentStatus, ChatMessage, MessageRole, AnalysisResult
from app.schemas import DocumentOut, ChatRequest, ChatResponse, AnalysisResultOut
from app.utils import (
    split_text,
    add_document_chunks,
    extract_text_from_pdf,
    detect_language,
    answer_question,
    extract_entities_via_regex,
    run_full_entity_extraction,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

# Directory where uploaded PDFs are persisted
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)



@router.post(
    "/upload",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a PDF document",
    description=(
        "Accepts a PDF file, saves it to disk, extracts raw text via PyMuPDF, "
        "detects the language, and inserts a row into the documents table."
    ),
)
async def upload_document(
    file: UploadFile = File(..., description="PDF file to upload"),
    db: Session = Depends(get_db),
) -> DocumentOut:
    # ── 1. Validate MIME type ────────────────────────────────────────────────
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF files are accepted.",
        )

    # ── 2. Save to disk ──────────────────────────────────────────────────────
    # Use a timestamp prefix to avoid filename collisions
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    safe_filename = Path(file.filename).name  # strip any path traversal
    dest_path = UPLOAD_DIR / f"{timestamp}_{safe_filename}"

    try:
        contents = await file.read()
        dest_path.write_bytes(contents)
        logger.info("Saved uploaded file to %s", dest_path)
    except OSError as exc:
        logger.error("Failed to save file: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save the uploaded file.",
        ) from exc

    # ── 3. Extract raw text via PyMuPDF ──────────────────────────────────────
    try:
        raw_text = extract_text_from_pdf(dest_path)
        logger.info("Extracted %d chars from %s", len(raw_text), dest_path.name)
    except Exception as exc:
        logger.error("Text extraction failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not extract text from the PDF. Ensure it is not corrupted.",
        ) from exc

    # ── 4. Detect language ───────────────────────────────────────────────────
    language = detect_language(raw_text)
    logger.info("Detected language: %s", language)

    # ── 5. Persist to DB and Index ───────────────────────────────────────────
    doc = Document(
        filename=safe_filename,
        upload_date=datetime.now(timezone.utc),
        language=language,
        raw_text=raw_text,
        status=DocumentStatus.processing,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    logger.info("Inserted document id=%d (%s), status set to processing", doc.id, doc.filename)

    try:
        chunks = split_text(raw_text)
        logger.info("Generated %d text chunks for document id=%d", len(chunks), doc.id)
        
        # Index chunks in ChromaDB
        add_document_chunks(document_id=doc.id, chunks=chunks, filename=doc.filename)
        
        # Run full analysis and create AnalysisResult
        logger.info("Running full entity extraction for document id=%d", doc.id)
        entities = run_full_entity_extraction(raw_text, language=language)
        analysis = AnalysisResult(
            document_id=doc.id,
            extracted_entities=entities,
            risk_flags=[],
            draft_text=""
        )
        db.add(analysis)
        
        # Update status to completed
        doc.status = DocumentStatus.completed
        db.commit()
        db.refresh(doc)
        logger.info("Successfully indexed and analyzed document id=%d and set status to completed", doc.id)
    except Exception as exc:
        logger.error("Failed to process/index document id=%d: %s", doc.id, exc)
        doc.status = DocumentStatus.failed
        db.commit()
        db.refresh(doc)
        # Raise HTTP exception to notify client of the processing failure
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Document uploaded but indexing failed: {exc}",
        ) from exc

    # The endpoint's response_model is `DocumentOut` — return the persisted
    # `Document` instance so FastAPI can serialize the expected fields.
    return doc


@router.post(
    "/{document_id}/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Ask a question about a document",
    description=(
        "Takes a document ID and a question, retrieves context chunks from ChromaDB, "
        "generates an answer using Groq (llama-3.3-70b-versatile), "
        "persists the user query and assistant response in the database, "
        "and returns the generated answer."
    ),
)
def chat_with_document(
    document_id: int,
    payload: ChatRequest,
    db: Session = Depends(get_db),
) -> ChatResponse:
    # 1. Check if the document exists
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} was not found."
        )

    # 2. Get answer from RAG pipeline
    try:
        rag_response = answer_question(document_id=document_id, question=payload.question)
    except Exception as exc:
        logger.error("RAG pipeline failed for document_id=%d: %s", document_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"RAG query generation failed: {exc}"
        )

    # 3. Store conversation in database
    try:
        user_msg = ChatMessage(
            document_id=document_id,
            role=MessageRole.user,
            content=payload.question
        )
        assistant_msg = ChatMessage(
            document_id=document_id,
            role=MessageRole.assistant,
            content=rag_response["answer"]
        )
        db.add(user_msg)
        db.add(assistant_msg)
        db.commit()
        logger.info("Saved user query and assistant response for document_id=%d in chat_messages", document_id)
    except Exception as exc:
        logger.error("Failed to save chat exchange to database: %s", exc)

    return ChatResponse(
        answer=rag_response["answer"],
        document_id=rag_response["document_id"],
        chunks_used=rag_response["chunks_used"],
        confidence=rag_response["confidence"],
        sources=rag_response["sources"]
    )


@router.post(
    "/{document_id}/analyze",
    response_model=AnalysisResultOut,
    status_code=status.HTTP_200_OK,
    summary="Run full analysis on a document",
    description="Runs/reruns the full (regex + LLM) pass on the document's raw text and returns/updates the extraction results.",
)
def analyze_document(
    document_id: int,
    db: Session = Depends(get_db),
) -> AnalysisResultOut:
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} was not found."
        )

    logger.info("Running manual analyze request for document id=%d", document_id)
    
    # Normalizing existing raw text if it contains visual-order Devanagari characters or double spaces
    from app.utils.pdf_extraction import normalize_devanagari_text
    raw_text = doc.raw_text or ""
    normalized_text = normalize_devanagari_text(raw_text)
    if normalized_text != raw_text:
        logger.info("Normalizing and re-indexing raw text for document id=%d", document_id)
        doc.raw_text = normalized_text
        db.commit()
        db.refresh(doc)
        
        # Re-index chunks in ChromaDB
        from app.utils import delete_document_chunks, split_text, add_document_chunks
        try:
            delete_document_chunks(doc.id)
            chunks = split_text(normalized_text)
            add_document_chunks(document_id=doc.id, chunks=chunks, filename=doc.filename)
        except Exception as exc:
            logger.error("Failed to re-index normalized chunks for document id=%d: %s", document_id, exc)

    # pyrefly: ignore [bad-argument-type]
    entities = run_full_entity_extraction(doc.raw_text or "", language=doc.language)

    analysis = db.query(AnalysisResult).filter(AnalysisResult.document_id == document_id).first()
    if not analysis:
        analysis = AnalysisResult(
            document_id=document_id,
            extracted_entities=entities,
            risk_flags=[],
            draft_text=""
        )
        db.add(analysis)
    else:
        analysis.extracted_entities = entities

    db.commit()
    db.refresh(analysis)
    return analysis



@router.get(
    "/{document_id}/analysis",
    response_model=AnalysisResultOut,
    status_code=status.HTTP_200_OK,
    summary="Get existing analysis results",
    description="Retrieves the saved analysis result (extracted entities, risk flags, draft reply) for a document.",
)
def get_document_analysis(
    document_id: int,
    db: Session = Depends(get_db),
) -> AnalysisResultOut:
    analysis = db.query(AnalysisResult).filter(AnalysisResult.document_id == document_id).first()
    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No analysis found for document with ID {document_id}. Run analyze first."
        )
    return analysis

