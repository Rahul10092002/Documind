import re
import logging
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)

try:
    import fitz  # PyMuPDF
    _PYMUPDF_AVAILABLE = True
except ImportError:
    _PYMUPDF_AVAILABLE = False

try:
    import pdfplumber
    _PDFPLUMBER_AVAILABLE = True
except ImportError:
    _PDFPLUMBER_AVAILABLE = False


def normalize_devanagari(text: str) -> str:
    """Clean invisible Unicode artifacts injected by PDF parsers."""
    import re
    text = text.replace('\u200b', ' ')
    text = text.replace('\u200c', '')
    text = text.replace('\u200d', '')
    text = text.replace('\x00', '')
    text = re.sub(r' {2,}', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# Maintain backward compatibility with documents.py
normalize_devanagari_text = normalize_devanagari


def extract_text_pymupdf(pdf_path: Union[str, Path]) -> str:
    """Extract text using PyMuPDF — correct Devanagari Unicode order.
    
    Returns normalized text ready for regex and LLM processing.
    """
    if not _PYMUPDF_AVAILABLE:
        raise ImportError("PyMuPDF not installed. Run: pip install pymupdf")
    
    doc = fitz.open(str(pdf_path))
    pages_text = []
    
    for page_num, page in enumerate(doc):
        try:
            text = page.get_text()
            pages_text.append(text)
        except Exception as e:
            logger.warning("Page %d extraction failed: %s", page_num + 1, e)
            pages_text.append("")
    
    doc.close()
    raw_text = "\n".join(pages_text)
    return normalize_devanagari(raw_text)


def extract_text_from_pdf(pdf_path: Union[str, Path], language_hint: Optional[str] = None) -> str:
    """Primary entry point for PDF text extraction.
    
    Automatically selects the best extractor based on available libraries.
    
    Args:
        pdf_path: Path to the PDF file.
        language_hint: Not used, kept for backward compatibility.
    
    Returns:
        Normalized text string ready for downstream processing.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    
    try:
        from langchain_community.document_loaders import PyMuPDFLoader
        loader = PyMuPDFLoader(str(pdf_path))
        docs = loader.load()
        return normalize_devanagari("\n".join([d.page_content for d in docs]))
    except Exception as exc:
        logger.warning("PyMuPDFLoader failed: %s, attempting fallback...", exc)
        if _PYMUPDF_AVAILABLE:
            doc = fitz.open(pdf_path)
            pages_text = [page.get_text() for page in doc]
            doc.close()
            return normalize_devanagari("\n".join(pages_text))
        else:
            # pdfplumber fallback
            import pdfplumber
            pages_text = []
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        pages_text.append(t)
            return normalize_devanagari("\n".join(pages_text))


# ─── Quick verification helper ──────────────────────────────────────────────

def verify_devanagari_quality(text: str) -> dict:
    """Sanity-check extracted text for known Devanagari corruption patterns.
    
    Returns a dict with quality flags so you can catch bad extractions early.
    
    Usage:
        text = extract_text_from_pdf("doc.pdf")
        quality = verify_devanagari_quality(text)
        if not quality["ok"]:
            logger.error("Bad extraction: %s", quality["issues"])
    """
    issues = []
    
    # pdfplumber i-matra displacement: ि appears at start of word
    displaced_i = re.findall(r'(?<!\S)ि\S+', text)
    if displaced_i:
        issues.append(f"i-matra displacement detected ({len(displaced_i)} cases). "
                      f"Switch to PyMuPDF. Example: '{displaced_i[0]}'")
    
    # Null bytes (pdfplumber artifact for certain glyphs)
    null_count = text.count('\x00')
    if null_count > 0:
        issues.append(f"{null_count} null bytes in text — pdfplumber artifact.")
    
    # Residual ZW spaces (should be 0 after normalize_devanagari)
    zw_count = text.count('\u200b')
    if zw_count > 10:
        issues.append(f"{zw_count} Zero Width Spaces remain — normalize_devanagari() not called?")
    
    # Check if text is suspiciously short (possible scanned PDF)
    word_count = len(text.split())
    if word_count < 50:
        issues.append(f"Very short extraction ({word_count} words) — PDF may be image-based/scanned.")
    
    return {
        "ok": len(issues) == 0,
        "word_count": word_count,
        "issues": issues
    }
