from pathlib import Path
from typing import Optional, Union
from langchain_core.documents import Document as LangchainDocument

def extract_text_from_file(
    file_path: Union[str, Path], 
    language_hint: Optional[str] = None
) -> tuple[str, list[LangchainDocument]]:
    """Read plain text from files."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Text file not found: {file_path}")
    
    try:
        raw_text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        raise RuntimeError(f"Failed to read text file {file_path}: {e}") from e
    
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
