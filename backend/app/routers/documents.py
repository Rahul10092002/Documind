import asyncio
import logging
import io
from pathlib import Path
from datetime import datetime, timezone

import fitz
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status, BackgroundTasks
from fastapi.responses import StreamingResponse

from sqlalchemy.orm import Session

from app.dependencies import get_db_session as get_db
from app.database import SessionLocal
from app.models import Document, DocumentStatus, ChatMessage, MessageRole, AnalysisResult
from app.schemas import DocumentOut, DocumentSummaryOut, ChatRequest, ChatResponse, ChatMessageOut, AnalysisResultOut
from app.vectordb import split_text, split_documents, add_document_chunks
from app.extractors import extract_text_from_pdf, detect_language, extract_entities_via_regex, run_full_entity_extraction
from app.services import answer_question, aanswer_question, agenerate_risk_and_draft

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

        # 3. Invoke LangGraph pipeline
        doc.detailed_status = "Running LangGraph analysis pipeline..."
        db.commit()

        from app.agents.graph import graph
        
        initial_state = {
            "document_id": doc_id,
            "file_path": str(dest_path),
            "raw_bytes": contents,
            "raw_text": "",
            "documents": [],
            "is_scanned": False,
            "char_count": 0,
            "detected_language": "en",
            "detected_boilerplate": [],
            "language_confidence": 1.0,
            "prompt_locale": "english",
            "ner_entities": {},
            "llm_entities": {},
            "merged_entities": {},
            "risk_flags_raw": [],
            "risk_flags_deduped": [],
            "executive_summary": "",
            "risk_analysis_partial": False,
            "executive_summary_available": False,
            "retrieved_chunks": [],
            "rag_answer": "",
            "confidence_score": 0.0,
            "suggested_questions": [],
            "draft_reply": "",
            "current_step": "ingest",
            "errors": [],
            "retry_count": 0,
            "pipeline_type": "pdf"
        }

        result = await graph.ainvoke(initial_state)

        if result.get("errors"):
            raise RuntimeError(f"Pipeline errors: {'; '.join(result['errors'])}")

        # 4. Save pipeline results to Database
        doc.raw_text = result.get("raw_text", "")
        doc.language = result.get("detected_language", "en")
        
        # 5. Index chunks
        doc.detailed_status = "Indexing content for search..."
        db.commit()
        chunks = await asyncio.to_thread(split_documents, result.get("documents", []))
        await asyncio.to_thread(add_document_chunks, document_id=doc.id, chunks=chunks, filename=doc.filename)

        # 6. Save Analysis Result
        doc.detailed_status = "Finalizing analysis..."
        db.commit()
        
        analysis = AnalysisResult(
            document_id=doc.id,
            extracted_entities=result.get("merged_entities", {}),
            risk_flags=result.get("risk_flags_deduped", []),
            risk_obligation_summary=result.get("executive_summary", "")
        )
        db.add(analysis)

        # Mark as completed
        doc.status = DocumentStatus.completed
        doc.detailed_status = "Completed"
        db.commit()
        logger.info("Background task: Successfully indexed and analyzed document id=%s using LangGraph", doc_id)

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
        from app.vectordb.vector_store import delete_document_chunks
        delete_document_chunks(document_id)
    except Exception as exc:
        logger.error("Failed to delete chunks for document_id=%s: %s", document_id, exc)

    # Delete document row (cascades to AnalysisResult and ChatMessage)
    db.delete(doc)
    db.commit()
    logger.info("Deleted document id=%s and all associated data", document_id)
    return


