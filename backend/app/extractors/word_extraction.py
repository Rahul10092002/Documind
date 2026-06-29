import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Union
from langchain_core.documents import Document as LangchainDocument

def extract_word_text_and_docs(
    word_path: Union[str, Path], 
    language_hint: Optional[str] = None
) -> tuple[str, list[LangchainDocument]]:
    """Extract text from Word (.docx) documents using native zip and XML parsing."""
    path = Path(word_path)
    if not path.exists():
        raise FileNotFoundError(f"Word file not found: {word_path}")
        
    paragraphs = []
    try:
        with zipfile.ZipFile(path) as docx:
            xml_content = docx.read('word/document.xml')
            root = ET.fromstring(xml_content)
            
            for paragraph in root.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'):
                texts = [node.text for node in paragraph.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t') if node.text]
                if texts:
                    text = "".join(texts).strip()
                    if text:
                        paragraphs.append(text)
    except Exception as e:
        raise RuntimeError(f"Failed to extract text from Word document {word_path}: {e}") from e
        
    raw_text = "\n".join(paragraphs)
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
