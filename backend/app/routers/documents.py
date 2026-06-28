import asyncio
import logging
import io
from pathlib import Path
from datetime import datetime, timezone

import fitz
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status, BackgroundTasks
from fastapi.responses import StreamingResponse

from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
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
from app.utils.pdf_generator import generate_analysis_pdf

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



async def process_document_background(doc_id: str, filename: str, contents: bytes):
    db = SessionLocal()
    try:
        # 1. Locate/verify Document
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            logger.error("Background task: Document with ID %s not found in DB.", doc_id)
            return

        # 2. Save PDF to disk
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y%m%d_%H%M%S_%f")
        safe_filename = Path(filename).name
        dest_path = UPLOAD_DIR / f"{timestamp}_{safe_filename}"
        
        try:
            dest_path.write_bytes(contents)
            doc.file_path = str(dest_path)
            db.commit()
            logger.info("Background task: Saved uploaded file to %s", dest_path)
        except OSError as exc:
            logger.error("Background task: Failed to save file to disk: %s", exc)
            raise exc

        # 3. Extract text
        doc.detailed_status = "Reading & extracting structure..."
        db.commit()
        
        try:
            from app.utils.pdf_extraction import extract_text_and_docs_from_pdf
            raw_text, docs = await asyncio.to_thread(extract_text_and_docs_from_pdf, dest_path)
            doc.raw_text = raw_text
            db.commit()
            logger.info("Background task: Extracted %d chars from %s", len(raw_text), dest_path.name)
        except Exception as exc:
            logger.error("Background task: Text extraction failed: %s", exc)
            raise exc

        # 4. Detect language
        doc.detailed_status = "Detecting language..."
        db.commit()
        language = await asyncio.to_thread(detect_language, raw_text)
        doc.language = language
        db.commit()

        # 5. Index chunks
        doc.detailed_status = "Indexing content for search..."
        db.commit()
        chunks = await asyncio.to_thread(split_documents, docs)
        await asyncio.to_thread(add_document_chunks, document_id=doc.id, chunks=chunks, filename=doc.filename)

        # 6. Extract key details
        doc.detailed_status = "Extracting key details..."
        db.commit()
        entities = await asyncio.to_thread(run_full_entity_extraction, raw_text, language=language)

        # 7. Perform risk review
        doc.detailed_status = "Performing risk review..."
        db.commit()
        try:
            risk_draft = await agenerate_risk_and_draft(raw_text, language=language)
            risk_flags = risk_draft.get("risk_flags", [])
            risk_obligation_summary = risk_draft.get("risk_obligation_summary", "")
        except Exception as exc:
            logger.error("Background task: Failed to generate risk/draft: %s", exc)
            risk_flags = []
            risk_obligation_summary = ""

        analysis = AnalysisResult(
            document_id=doc.id,
            extracted_entities=entities,
            risk_flags=risk_flags,
            risk_obligation_summary=risk_obligation_summary
        )
        db.add(analysis)

        # Mark as completed
        doc.status = DocumentStatus.completed
        doc.detailed_status = "Completed"
        db.commit()
        logger.info("Background task: Successfully indexed and analyzed document id=%s", doc_id)

    except Exception as exc:
        logger.error("Background task: Processing failed for document id=%s: %s", doc_id, exc)
        try:
            doc = db.query(Document).filter(Document.id == doc_id).first()
            if doc:
                doc.status = DocumentStatus.failed
                doc.detailed_status = f"Failed: {str(exc)}"
                db.commit()
        except Exception as e:
            logger.error("Background task: Failed to update document status to failed: %s", e)
        try:
            if 'dest_path' in locals() and dest_path.exists():
                dest_path.unlink(missing_ok=True)
                logger.info("Background task: Cleaned up file from disk: %s", dest_path)
        except Exception as cleanup_exc:
            logger.error("Background task: Failed to cleanup file %s: %s", dest_path, cleanup_exc)
    finally:
        db.close()


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
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="PDF file to upload"),
    db: Session = Depends(get_db),
) -> DocumentOut:
    # ── 1. Read bytes and validate magic header BEFORE writing to disk ───────
    contents = await file.read()
    if not contents.startswith(b"%PDF"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="File is not a valid PDF (invalid magic bytes). Only PDF files are accepted.",
        )

    # ── 2. Create the document row in state 'processing' immediately ───
    now = datetime.now(timezone.utc)
    doc = Document(
        filename=Path(file.filename).name,
        upload_date=now,
        status=DocumentStatus.processing,
        detailed_status="Reading & extracting structure...",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    logger.info("Inserted document id=%s (%s), status set to processing", doc.id, doc.filename)

    # ── 3. Queue the background processing task ───
    background_tasks.add_task(
        process_document_background,
        doc.id,
        file.filename,
        contents,
    )

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


@router.post(
    "/{document_id}/chat/stream",
    summary="Ask a question about a document and stream progress updates",
    description="Takes a document ID and a question, runs RAG pipeline and yields progress updates as SSE chunks before returning final answer."
)
async def chat_with_document_stream(
    document_id: str,
    payload: ChatRequest,
    db: Session = Depends(get_db),
):
    import json
    # 1. Check if the document exists
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} was not found."
        )

    async def event_generator():
        # We use a Queue to pass steps and final results from the pipeline callback
        queue = asyncio.Queue()

        async def enqueue_step(step_name: str):
            await queue.put(("step", step_name))

        # Start the RAG pipeline in a background task
        async def run_pipeline():
            try:
                rag_response = await aanswer_question(
                    document_id=document_id,
                    question=payload.question,
                    db=db,
                    on_step=enqueue_step
                )
                await queue.put(("answer", rag_response))
            except Exception as e:
                logger.error("RAG pipeline failed in stream: %s", e)
                await queue.put(("error", str(e)))

        task = asyncio.create_task(run_pipeline())

        while True:
            item_type, val = await queue.get()
            if item_type == "step":
                yield f"step:{val}\n"
            elif item_type == "answer":
                # Store message in DB
                try:
                    user_msg = ChatMessage(
                        document_id=document_id,
                        role=MessageRole.user,
                        content=payload.question
                    )
                    assistant_msg = ChatMessage(
                        document_id=document_id,
                        role=MessageRole.assistant,
                        content=val["answer"]
                    )
                    db.add(user_msg)
                    db.add(assistant_msg)
                    db.commit()
                    logger.info("Saved user query and assistant response for document_id=%s in chat_messages (stream)", document_id)
                except Exception as db_exc:
                    logger.error("Failed to save chat exchange to database (stream): %s", db_exc)

                # Serialize final payload
                chat_resp = {
                    "answer": val["answer"],
                    "document_id": val["document_id"],
                    "chunks_used": val["chunks_used"],
                    "confidence": val["confidence"],
                    "sources": val["sources"],
                    "suggested_questions": val.get("suggested_questions", [])
                }
                yield f"answer:{json.dumps(chat_resp)}\n"
                break
            elif item_type == "error":
                yield f"error:{val}\n"
                break

        await task

    return StreamingResponse(event_generator(), media_type="text/event-stream")


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


from app.utils.pdf_generator import generate_analysis_pdf


@router.get(
    "/{document_id}/export",
    summary="Export analysis results as PDF",
    description="Generates and returns a downloadable A4 PDF report with all document analysis results.",
)
def export_analysis_pdf(
    document_id: str,
    db: Session = Depends(get_db),
):
    doc_row = db.query(Document).filter(Document.id == document_id).first()
    if not doc_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} was not found."
        )
        
    analysis = db.query(AnalysisResult).filter(AnalysisResult.document_id == document_id).first()
    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No analysis results found for document {document_id}. Please analyze the document first."
        )
        
    try:
        pdf_data = generate_analysis_pdf(doc_row.filename, analysis)
    except Exception as e:
        logger.error("Failed to generate PDF report for document %s: %s", document_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate PDF report: {e}"
        )
        
    safe_filename = Path(doc_row.filename).stem
    headers = {
        "Content-Disposition": f"attachment; filename=DocMind_Analysis_{safe_filename}.pdf"
    }
    return StreamingResponse(
        io.BytesIO(pdf_data),
        media_type="application/pdf",
        headers=headers
    )
