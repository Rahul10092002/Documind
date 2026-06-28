import logging
from pathlib import Path
from typing import Optional, Union
import pytesseract
from PIL import Image
from langchain_core.documents import Document as LangchainDocument

logger = logging.getLogger(__name__)

def extract_image_text_and_docs(
    image_path: Union[str, Path], 
    language_hint: Optional[str] = None
) -> tuple[str, list[LangchainDocument]]:
    """Extract text from an image file using Tesseract OCR."""
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")
        
    tess_lang = "hin+eng" if (language_hint in ("hi", "hi-Latn") or language_hint is None) else "eng"
    
    try:
        img = Image.open(path)
        img_conv = img.convert("L")  # Grayscale for better OCR accuracy
        img_conv = img_conv.point(lambda x: 0 if x < 150 else 255)  # Binary thresholding
        raw_text = pytesseract.image_to_string(img_conv, lang=tess_lang)
    except Exception as e:
        logger.warning("OCR failed with lang %s, falling back to English. Error: %s", tess_lang, e)
        try:
            raw_text = pytesseract.image_to_string(img_conv, lang="eng")
        except Exception as retry_err:
            logger.error("Image OCR failed: %s", retry_err)
            raise RuntimeError(f"OCR failed for image {image_path}: {retry_err}") from retry_err

    if not raw_text.strip():
        logger.warning("OCR produced no text for image: %s", image_path)
        raise RuntimeError(f"No readable text found in image: {image_path}")

    docs = [
        LangchainDocument(
            page_content=raw_text,
            metadata={
                "source": str(path),
                "file_name": path.name,
                "extension": path.suffix.lower(),
                "language": language_hint,
            }
        )
    ]
    return raw_text, docs
