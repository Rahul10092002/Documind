import os
import re
import shutil
import logging
from pathlib import Path
from typing import Optional, Union
from langchain_core.documents import Document as LangchainDocument

import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image

logger = logging.getLogger(__name__)

def configure_tesseract() -> bool:
    """Auto-configure Tesseract path on Windows if not in PATH."""
    if shutil.which("tesseract"):
        return True
    
    current_cmd = pytesseract.pytesseract.tesseract_cmd
    if current_cmd and current_cmd != "tesseract" and Path(current_cmd).exists():
        return True
        
    if os.name == "nt":
        possible_tess_paths = [
            Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Tesseract-OCR" / "tesseract.exe",
            Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")) / "Tesseract-OCR" / "tesseract.exe",
            Path(os.environ.get("LocalAppData", f"C:\\Users\\{os.environ.get('USERNAME', '')}\\AppData\\Local")) / "Programs" / "Tesseract-OCR" / "tesseract.exe",
            Path("C:\\Program Files\\Tesseract-OCR\\tesseract.exe"),
            Path("C:\\Program Files (x86)\\Tesseract-OCR\\tesseract.exe"),
        ]
        for path in possible_tess_paths:
            if path.exists():
                pytesseract.pytesseract.tesseract_cmd = str(path)
                logger.info("Auto-configured Tesseract path: %s", path)
                return True
    return False

# Run at module import time
configure_tesseract()

def find_poppler_path() -> Optional[str]:
    """Find poppler path on Windows if not in PATH."""
    if shutil.which("pdftoppm"):
        return None
    
    possible_poppler_dirs = [
        Path("C:\\Program Files\\poppler\\bin"),
        Path("C:\\Program Files (x86)\\poppler\\bin"),
        Path("C:\\poppler\\bin"),
        Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "poppler" / "bin",
        Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")) / "poppler" / "bin",
    ]
    for p in possible_poppler_dirs:
        if p.exists() and (p / "pdftoppm.exe").exists():
            logger.info("Auto-configured Poppler path: %s", p)
            return str(p)
    return None

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

def is_scanned_pdf(docs: list, min_chars_per_page: int = 50) -> bool:
    """
    Agar average chars per page < 50 hai,
    toh likely scanned hai.
    """
    if not docs:
        return True
    
    total_chars = sum(len(doc.page_content.strip()) for doc in docs)
    avg_chars = total_chars / len(docs)
    
    return avg_chars < min_chars_per_page

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

def extract_text_with_ocr(pdf_bytes: bytes, language: str = None) -> str:
    """
    Scanned PDF ke pages ko images mein convert karo,
    phir Tesseract se OCR karo.
    """
    pages = extract_pages_with_ocr(pdf_bytes, language)
    return "\n".join(pages)

def extract_pages_with_ocr(pdf_bytes: bytes, language: str = None) -> list[str]:
    """
    Scanned PDF ke pages ko images mein convert karo,
    phir Tesseract se OCR karo page-by-page.
    """
    # Ensure Tesseract is configured dynamically (in case of post-startup install)
    configure_tesseract()
    
    import io
    images = []
    
    # Try converting using PyMuPDF (fitz) first to avoid Poppler dependency
    if _PYMUPDF_AVAILABLE:
        try:
            logger.info("Converting PDF pages to images using PyMuPDF (no Poppler required)...")
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            for page in doc:
                pix = page.get_pixmap(dpi=300)  # Render page to high-quality image
                img_data = pix.tobytes("png")
                images.append(Image.open(io.BytesIO(img_data)))
            doc.close()
        except Exception as e:
            logger.warning("PyMuPDF page rendering failed: %s. Falling back to pdf2image.", e)
            images = []
            
    # Fallback to pdf2image (requires Poppler) if PyMuPDF failed or is not available
    if not images:
        poppler_p = find_poppler_path()
        try:
            logger.info("Converting PDF pages to images using pdf2image (requires Poppler)...")
            images = convert_from_bytes(pdf_bytes, dpi=300, poppler_path=poppler_p)
        except Exception as e:
            logger.error(
                "Failed to convert PDF pages to images for OCR. "
                "PyMuPDF failed and pdf2image (Poppler) is not available/configured. "
                "Error: %s", e
            )
            raise RuntimeError(
                "Failed to convert PDF to images for OCR. "
                "Please ensure PyMuPDF is working or Poppler is installed and configured."
            ) from e
        
    tess_lang = "hin+eng" if (language in ("hi", "hi-Latn") or language is None) else "eng"
    
    extracted_pages = []
    try:
        for idx, img in enumerate(images):
            img_conv = img.convert("L")  # Grayscale for better OCR accuracy
            text = pytesseract.image_to_string(img_conv, lang=tess_lang)
            extracted_pages.append(text)
    except Exception as e:
        error_msg = str(e)
        # If it failed due to missing Hindi traineddata, fall back to English
        if "hin" in tess_lang and ("failed loading language" in error_msg.lower() or "error opening data file" in error_msg.lower() or "tessdata" in error_msg.lower()):
            logger.warning("Hindi OCR language pack 'hin' not found. Falling back to English OCR. Error: %s", e)
            tess_lang = "eng"
            extracted_pages = []
            for idx, img in enumerate(images):
                try:
                    img_conv = img.convert("L")
                    text = pytesseract.image_to_string(img_conv, lang=tess_lang)
                    extracted_pages.append(text)
                except Exception as retry_err:
                    logger.error("Tesseract OCR failed during retry on page %d: %s", idx + 1, retry_err)
                    raise RuntimeError(
                        "Tesseract OCR is not installed or not configured on the system. Cannot OCR scanned PDF."
                    ) from retry_err
        else:
            logger.error("Tesseract OCR failed: %s", e)
            raise RuntimeError(
                "Tesseract OCR is not installed or not configured on the system. Cannot OCR scanned PDF."
            ) from e
            
    return extracted_pages

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


def extract_text_and_docs_from_pdf(
    pdf_path: Union[str, Path], 
    language_hint: Optional[str] = None
) -> tuple[str, list[LangchainDocument]]:
    """Primary entry point for PDF text extraction that returns both full text and chunkable docs.
    
    Automatically handles scanned PDFs via OCR and normalizes text.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
        
    docs = []
    raw_text = ""
    
    # Try standard PDF text extraction
    try:
        from langchain_community.document_loaders import PyMuPDFLoader
        loader = PyMuPDFLoader(str(pdf_path))
        docs = loader.load()
        for doc in docs:
            doc.page_content = normalize_devanagari(doc.page_content)
            doc.metadata.update({
                "source": str(path),
                "file_name": path.name,
                "extension": path.suffix.lower(),
                "language": language_hint,
            })
        raw_text = "\n".join(d.page_content for d in docs)
        
    except Exception as exc:
        logger.warning("PyMuPDFLoader failed: %s, attempting raw fitz/pdfplumber fallbacks...", exc)
        
        pages_text = []
        if _PYMUPDF_AVAILABLE:
            try:
                doc = fitz.open(str(pdf_path))
                pages_text = [page.get_text() for page in doc]
                doc.close()
            except Exception as fitz_exc:
                logger.warning("Raw PyMuPDF failed: %s", fitz_exc)
        
        if not pages_text and _PDFPLUMBER_AVAILABLE:
            try:
                with pdfplumber.open(pdf_path) as pdf:
                    for page in pdf.pages:
                        t = page.extract_text()
                        pages_text.append(t if t else "")
            except Exception as plumber_exc:
                logger.warning("pdfplumber failed: %s", plumber_exc)
                
        # Reconstruct docs list
        docs = [
            LangchainDocument(
                page_content=normalize_devanagari(txt),
                metadata={
                    "source": str(path),
                    "file_name": path.name,
                    "extension": path.suffix.lower(),
                    "language": language_hint,
                    "page": i,
                }
            )
            for i, txt in enumerate(pages_text)
        ]
        raw_text = "\n".join(d.page_content for d in docs)
        
    # Check if scanned PDF
    if is_scanned_pdf(docs):
        logger.warning(f"Scanned PDF detected: {pdf_path}. Falling back to OCR.")
        file_bytes = path.read_bytes()
        # Perform OCR page-by-page
        ocr_pages = extract_pages_with_ocr(file_bytes, language=language_hint)
        
        # Reconstruct docs with OCR'd page content
        docs = [
            LangchainDocument(
                page_content=normalize_devanagari(txt),
                metadata={
                    "source": str(path),
                    "file_name": path.name,
                    "extension": path.suffix.lower(),
                    "language": language_hint,
                    "page": i,
                }
            )
            for i, txt in enumerate(ocr_pages)
        ]
        raw_text = "\n".join(d.page_content for d in docs)
        logger.info("Successfully OCR'd scanned PDF. Extracted %d chars.", len(raw_text))
            
    return normalize_devanagari(raw_text), docs


def extract_text_from_pdf(pdf_path: Union[str, Path], language_hint: Optional[str] = None) -> str:
    """Primary entry point for PDF text extraction.
    
    Automatically selects the best extractor based on available libraries and triggers OCR if scanned.
    
    Args:
        pdf_path: Path to the PDF file.
        language_hint: Language code context for OCR (optional).
    
    Returns:
        Normalized text string ready for downstream processing.
    """
    raw_text, _ = extract_text_and_docs_from_pdf(pdf_path, language_hint)
    return raw_text


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
