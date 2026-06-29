import logging
import asyncio
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from app.dependencies import get_db_session as get_db
from app.models import Document, AnalysisResult
from app.schemas import AnalysisResultOut
from app.services import agenerate_risk_and_draft
from app.extractors.entity_extraction import run_full_entity_extraction
from app.main import limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["extraction"])

async def _run_document_analysis(document_id: str, db: Session) -> AnalysisResult:
    """Internal helper to execute or re-run the full analysis and update/create the AnalysisResult."""
    from app.routers.documents import find_physical_file
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} was not found."
        )

    logger.info("Running manual analyze request for document id=%s", document_id)
    
    # Normalizing existing raw text if it contains visual-order Devanagari characters or double spaces
    from app.extractors.pdf_extraction import normalize_devanagari_text
    raw_text = doc.raw_text or ""
    normalized_text = normalize_devanagari_text(raw_text)
    if normalized_text != raw_text:
        logger.info("Normalizing and re-indexing raw text for document id=%s", document_id)
        doc.raw_text = normalized_text
        db.commit()
        db.refresh(doc)
        
        # Re-index chunks in ChromaDB
        from app.vectordb import delete_document_chunks, split_text, split_documents, add_document_chunks
        try:
            delete_document_chunks(doc.id)
            
            # Try to load the original PDF to preserve page numbers
            physical_file = find_physical_file(doc)
            if physical_file and physical_file.exists():
                from langchain_community.document_loaders import PyMuPDFLoader
                from app.extractors.pdf_extraction import normalize_devanagari
                
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

    # Offload blocking LLM calls to a thread pool
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
@limiter.limit("10/minute")
async def analyze_document_put(
    request: Request,
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
