from typing import List, Optional

try:
    # pyrefly: ignore [missing-import]
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except Exception as e:
    raise ImportError(
        "langchain is required for text chunking. Install with 'pip install langchain_text_splitters'"
    ) from e


def split_text(
    text: str,
    chunk_size: int = 700,
    chunk_overlap: int = 100,
    separators: Optional[List[str]] = None,
) -> List[str]:
    """Split `text` into chunks using LangChain's RecursiveCharacterTextSplitter.

    Defaults aim for chunks ~500-800 characters with ~100 overlap.

    Args:
        text: Raw input text to chunk.
        chunk_size: Maximum characters per chunk (default 700).
        chunk_overlap: Number of characters overlap between chunks (default 100).
        separators: Optional list of separators to prefer when splitting.

    Returns:
        A list of text chunks.
    """
    if not text:
        return []

    if separators is None:
        separators = ["\n\n", "\n", " ", ""]

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=separators,
    )

    # RecursiveCharacterTextSplitter provides split_text
    return splitter.split_text(text)
