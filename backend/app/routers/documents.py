import asyncio
import logging
from pathlib import Path
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Document, DocumentStatus, ChatMessage, MessageRole, AnalysisResult
from app.schemas import DocumentOut, DocumentSummaryOut, ChatRequest, ChatResponse, ChatMessageOut, AnalysisResultOut
from app.utils import (
    split_text,
    split_documents,
    add_document_chunks,
    extract_text_from_pdf,
    detect_language,
    answer_question,
    extract_entities_via_regex,
    run_full_entity_extraction,
)
from app.utils.answer_service import aanswer_question, agenerate_risk_and_draft

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

# Directory where uploaded PDFs are persisted
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


def find_physical_file(doc: Document) -> Path | None:
    """Locate the physical PDF file in the uploads directory for a given Document.
    Attempts to match the formatted upload_date prefix first, then falls back to modification time check.
    """
    if not doc.upload_date or not doc.filename:
        return None

    # Try matching the exact timestamp prefix up to the second (e.g. YYYYMMDD_HHMMSS)
    prefix_sec = doc.upload_date.strftime("%Y%m%d_%H%M%S")
    for file_path in UPLOAD_DIR.glob(f"*_{doc.filename}"):
        if file_path.name.startswith(prefix_sec):
            return file_path

    # Fallback: Find the file ending with _{filename} that has the closest mtime (within 1 minute)
    best_file = None
    min_diff = float("inf")
    for file_path in UPLOAD_DIR.glob(f"*_{doc.filename}"):
        try:
            mtime = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)
            diff = abs((mtime - doc.upload_date).total_seconds())
            if diff < min_diff:
                min_diff = diff
                best_file = file_path
        except Exception:
            continue

    if best_file and min_diff < 60:
        return best_file

    return None



@router.post(
    "/upload",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a PDF document",
    description=(
        "Accepts a PDF file, saves it to disk, extracts raw text via PyMuPDF, "
        "detects the language, and inserts a row into the documents table. "
        "LIMITATION: If the extracted text exceeds 30,000 characters, it will be "
        "truncated to the first 30,000 characters during subsequent risk analysis "
        "and draft reply generation passes."
    ),
)
async def upload_document(
    file: UploadFile = File(..., description="PDF file to upload"),
    db: Session = Depends(get_db),
) -> DocumentOut:
    # ── 1. Read bytes and validate magic header BEFORE writing to disk ───────
    # This prevents malicious files (e.g. .exe or .zip renamed to .pdf) from
    # ever landing in the uploads directory. All real PDFs begin with b"%PDF".
    contents = await file.read()
    if not contents.startswith(b"%PDF"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="File is not a valid PDF (invalid magic bytes). Only PDF files are accepted.",
        )

    # ── 2. Save to disk ──────────────────────────────────────────────────────
    # Use a timestamp prefix to avoid filename collisions
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%d_%H%M%S_%f")
    safe_filename = Path(file.filename).name  # strip any path traversal
    dest_path = UPLOAD_DIR / f"{timestamp}_{safe_filename}"

    try:
        dest_path.write_bytes(contents)
        logger.info("Saved uploaded file to %s", dest_path)
    except OSError as exc:
        logger.error("Failed to save file: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save the uploaded file.",
        ) from exc

    # Clean up the file on disk if any failure occurs before the document row is successfully committed
    try:
        # ── 3. Extract raw text via PyMuPDFLoader ─────────────────────────────────
        try:
            from langchain_community.document_loaders import PyMuPDFLoader
            from app.utils.pdf_extraction import normalize_devanagari

            loader = PyMuPDFLoader(str(dest_path))
            docs = loader.load()

            for d in docs:
                d.page_content = normalize_devanagari(d.page_content)

            raw_text = "\n".join([d.page_content for d in docs])
            logger.info("Extracted %d chars from %s using PyMuPDFLoader", len(raw_text), dest_path.name)
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
            file_path=str(dest_path),
            upload_date=now,
            language=language,
            raw_text=raw_text,
            status=DocumentStatus.processing,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        logger.info("Inserted document id=%s (%s), status set to processing", doc.id, doc.filename)
    except Exception as exc:
        db.rollback()
        try:
            dest_path.unlink(missing_ok=True)
            logger.info("Cleaned up orphaned file from disk: %s", dest_path)
        except Exception as unlink_exc:
            logger.error("Failed to unlink orphaned file %s: %s", dest_path, unlink_exc)

        if isinstance(exc, HTTPException):
            raise exc
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process and save document: {exc}",
        ) from exc

    try:
        chunks = split_documents(docs)
        logger.info("Generated %d text chunks for document id=%s", len(chunks), doc.id)
        
        # Index chunks in ChromaDB
        add_document_chunks(document_id=doc.id, chunks=chunks, filename=doc.filename)
        
        # Run full analysis and create AnalysisResult
        logger.info("Running full entity extraction for document id=%s", doc.id)
        # run_full_entity_extraction is synchronous (makes blocking LLM calls).
        # Offload to a thread pool to avoid stalling the async event loop.
        entities = await asyncio.to_thread(run_full_entity_extraction, raw_text, language=language)
        
        logger.info("Running risk and combined summary generation for document id=%s", doc.id)
        try:
            risk_draft = await agenerate_risk_and_draft(raw_text, language=language)
            risk_flags = risk_draft.get("risk_flags", [])
            risk_obligation_summary = risk_draft.get("risk_obligation_summary", "")
        except Exception as exc:
            logger.error("Failed to generate risk/draft for document id=%s: %s", doc.id, exc)
            risk_flags = []
            risk_obligation_summary = ""

        analysis = AnalysisResult(
            document_id=doc.id,
            extracted_entities=entities,
            risk_flags=risk_flags,
            risk_obligation_summary=risk_obligation_summary
        )
        db.add(analysis)
        
        # Update status to completed
        doc.status = DocumentStatus.completed
        db.commit()
        db.refresh(doc)
        logger.info("Successfully indexed and analyzed document id=%s and set status to completed", doc.id)
    except Exception as exc:
        logger.error("Failed to process/index document id=%s: %s", doc.id, exc)
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
async def chat_with_document(
    document_id: str,
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
        rag_response = await aanswer_question(document_id=document_id, question=payload.question, db=db)
    except Exception as exc:
        logger.error("RAG pipeline failed for document_id=%s: %s", document_id, exc)
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
        logger.info("Saved user query and assistant response for document_id=%s in chat_messages", document_id)
    except Exception as exc:
        logger.error("Failed to save chat exchange to database: %s", exc)

    return ChatResponse(
        answer=rag_response["answer"],
        document_id=rag_response["document_id"],
        chunks_used=rag_response["chunks_used"],
        confidence=rag_response["confidence"],
        sources=rag_response["sources"],
        suggested_questions=rag_response.get("suggested_questions", [])
    )


@router.get(
    "/{document_id}/chat",
    response_model=list[ChatMessageOut],
    status_code=status.HTTP_200_OK,
    summary="Get chat history for a document",
    description="Retrieves the sorted chat messages exchange history (user queries and assistant answers) for a given document.",
)
def get_chat_history(
    document_id: str,
    db: Session = Depends(get_db),
) -> list[ChatMessageOut]:
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} was not found."
        )
    return db.query(ChatMessage).filter(ChatMessage.document_id == document_id).order_by(ChatMessage.created_at.asc()).all()


async def _run_document_analysis(document_id: str, db: Session) -> AnalysisResult:
    """Internal helper to execute or re-run the full analysis and update/create the AnalysisResult."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} was not found."
        )

    logger.info("Running manual analyze request for document id=%s", document_id)
    
    # Normalizing existing raw text if it contains visual-order Devanagari characters or double spaces
    from app.utils.pdf_extraction import normalize_devanagari_text
    raw_text = doc.raw_text or ""
    normalized_text = normalize_devanagari_text(raw_text)
    if normalized_text != raw_text:
        logger.info("Normalizing and re-indexing raw text for document id=%s", document_id)
        doc.raw_text = normalized_text
        db.commit()
        db.refresh(doc)
        
        # Re-index chunks in ChromaDB
        from app.utils import delete_document_chunks, split_text, split_documents, add_document_chunks
        try:
            delete_document_chunks(doc.id)
            
            # Try to load the original PDF to preserve page numbers
            physical_file = find_physical_file(doc)
            if physical_file and physical_file.exists():
                from langchain_community.document_loaders import PyMuPDFLoader
                from app.utils.pdf_extraction import normalize_devanagari
                
                loader = PyMuPDFLoader(str(physical_file))
                pdf_docs = loader.load()
                for d in pdf_docs:
                    d.page_content = normalize_devanagari(d.page_content)
                chunks = split_documents(pdf_docs)
            else:
                chunks = split_text(normalized_text)
                
            add_document_chunks(document_id=doc.id, chunks=chunks, filename=doc.filename)
        except Exception as exc:
            logger.error("Failed to re-index normalized chunks for document id=%s: %s", document_id, exc)

    # pyrefly: ignore [bad-argument-type]
    # run_full_entity_extraction is synchronous (makes blocking LLM calls).
    # Offload to a thread pool to avoid stalling the async event loop.
    entities = await asyncio.to_thread(run_full_entity_extraction, doc.raw_text or "", language=doc.language)

    logger.info("Running manual risk and combined summary generation for document id=%s", document_id)
    try:
        risk_draft = await agenerate_risk_and_draft(doc.raw_text or "", language=doc.language)
        risk_flags = risk_draft.get("risk_flags", [])
        risk_obligation_summary = risk_draft.get("risk_obligation_summary", "")
    except Exception as exc:
        logger.error("Failed to generate risk/draft for document id=%s: %s", document_id, exc)
        risk_flags = []
        risk_obligation_summary = ""

    analysis = db.query(AnalysisResult).filter(AnalysisResult.document_id == document_id).first()
    if not analysis:
        analysis = AnalysisResult(
            document_id=document_id,
            extracted_entities=entities,
            risk_flags=risk_flags,
            risk_obligation_summary=risk_obligation_summary
        )
        db.add(analysis)
    else:
        analysis.extracted_entities = entities
        analysis.risk_flags = risk_flags
        analysis.risk_obligation_summary = risk_obligation_summary

    db.commit()
    db.refresh(analysis)
    return analysis


@router.put(
    "/{document_id}/analysis",
    response_model=AnalysisResultOut,
    status_code=status.HTTP_200_OK,
    summary="Run or update document analysis results",
    description=(
        "Performs an idempotent upsert of the AnalysisResult for the given document. "
        "Runs/reruns the full (regex + LLM) pass on the document's raw text and returns/updates the extraction results. "
        "LIMITATION: For documents exceeding 30,000 characters, the text is truncated "
        "to the first 30,000 characters before sending to the LLM for risk and draft reply generation."
    ),
)
async def analyze_document_put(
    document_id: str,
    db: Session = Depends(get_db),
) -> AnalysisResultOut:
    return await _run_document_analysis(document_id, db)


@router.post(
    "/{document_id}/analyze",
    response_model=AnalysisResultOut,
    status_code=status.HTTP_200_OK,
    summary="Run full analysis on a document (deprecated)",
    description=(
        "Runs/reruns the full (regex + LLM) pass on the document's raw text and returns/updates the extraction results. "
        "POST conventionally implies creation of a resource, whereas this operation is idempotent and performs an upsert. "
        "Hence, PUT /documents/{document_id}/analysis is preferred. This endpoint is deprecated and will be removed in a future version. "
        "LIMITATION: For documents exceeding 30,000 characters, the text is truncated "
        "to the first 30,000 characters before sending to the LLM for risk and draft reply generation."
    ),
    deprecated=True,
)
async def analyze_document_post(
    document_id: str,
    db: Session = Depends(get_db),
) -> AnalysisResultOut:
    return await _run_document_analysis(document_id, db)



@router.get(
    "/{document_id}/analysis",
    response_model=AnalysisResultOut,
    status_code=status.HTTP_200_OK,
    summary="Get existing analysis results",
    description="Retrieves the saved analysis result (extracted entities, risk flags, draft reply) for a document.",
)
def get_document_analysis(
    document_id: str,
    db: Session = Depends(get_db),
) -> AnalysisResultOut:
    analysis = db.query(AnalysisResult).filter(AnalysisResult.document_id == document_id).first()
    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No analysis found for document with ID {document_id}. Run analyze first."
        )
    return analysis


@router.get(
    "",
    response_model=list[DocumentSummaryOut],
    status_code=status.HTTP_200_OK,
    summary="List all documents",
)
def list_documents(
    skip: int = Query(default=0, ge=0, description="Number of records to skip (for pagination)"),
    limit: int = Query(default=20, ge=1, le=100, description="Maximum number of records to return (1–100)"),
    db: Session = Depends(get_db),
) -> list[DocumentSummaryOut]:
    return db.query(Document).order_by(Document.upload_date.desc()).offset(skip).limit(limit).all()


@router.get(
    "/{document_id}",
    response_model=DocumentOut,
    status_code=status.HTTP_200_OK,
    summary="Get document details",
)
def get_document(
    document_id: str,
    db: Session = Depends(get_db),
) -> DocumentOut:
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} was not found."
        )
    return doc


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document and its resources",
    description=(
        "Deletes a document from the database (cascading to AnalysisResult and ChatMessage), "
        "removes its chunks from ChromaDB, and deletes its physical PDF file from the local uploads folder."
    ),
)
def delete_document(
    document_id: str,
    db: Session = Depends(get_db),
):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} was not found."
        )
    
    # Delete physical file from disk.
    # Prefer the exact path stored on the document row (set at upload time).
    # Fall back to fuzzy mtime matching for legacy rows that predate the file_path column.
    if doc.file_path:
        file_path = Path(doc.file_path)
    else:
        file_path = find_physical_file(doc)

    if file_path:
        try:
            file_path.unlink(missing_ok=True)
            logger.info("Deleted physical file %s for document id=%s", file_path, document_id)
        except Exception as exc:
            logger.error("Failed to delete physical file %s for document id=%s: %s", file_path, document_id, exc)
    else:
        logger.warning("Could not find physical file on disk to delete for document id=%s", document_id)

    # Delete chunks from ChromaDB
    try:
        from app.utils.vector_store import delete_document_chunks
        delete_document_chunks(document_id)
    except Exception as exc:
        logger.error("Failed to delete chunks for document_id=%s: %s", document_id, exc)

    # Delete document row (cascades to AnalysisResult and ChatMessage)
    db.delete(doc)
    db.commit()
    logger.info("Deleted document id=%s and all associated data", document_id)
    return
