from pathlib import Path
from langchain_community.document_loaders import PyPDFLoader


def extract_text_from_pdf(file_path: Path) -> str:
    """Return concatenated plain text from all pages of a PDF using PyPDFLoader."""
    loader = PyPDFLoader(str(file_path))
    docs = loader.load()
    return "\n".join([doc.page_content for doc in docs]).strip()
