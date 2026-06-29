import io
import logging
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.dependencies import get_db_session as get_db
from app.models import Document, AnalysisResult
from app.extractors.pdf_generator import generate_analysis_pdf

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["reports"])

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
