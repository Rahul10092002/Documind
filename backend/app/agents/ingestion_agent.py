from .state import DocuMindState

from app.extractors.pdf_extraction import (
    extract_text_and_docs_from_pdf,
    is_scanned_pdf,
)
from app.extractors.word_extraction import extract_word_text_and_docs
from app.extractors.image_extraction import extract_image_text_and_docs
from app.extractors.text_extraction import extract_text_from_file


def _ingest(state: DocuMindState, extractor) -> DocuMindState:
    """Generic document ingestion."""

    raw_text, documents = extractor(
        state["file_path"],
        language_hint=state["prompt_locale"],
    )

    state.update(
        {
            "raw_text": raw_text,
            "documents": documents,
            "is_scanned": is_scanned_pdf(documents),
            "char_count": len(raw_text),
        }
    )

    return state


PIPELINE_HANDLERS = {
    "pdf": extract_text_and_docs_from_pdf,
    "word": extract_word_text_and_docs,
    "image": extract_image_text_and_docs,
    "text": extract_text_from_file,
}


def ingestion_agent(state: DocuMindState) -> DocuMindState:
    """Extract and process document content."""

    state["current_step"] = "ingesting"

    try:
        pipeline = state["pipeline_type"]

        extractor = PIPELINE_HANDLERS.get(pipeline)
        if extractor is None:
            raise ValueError(f"Unsupported pipeline type: {pipeline}")

        state = _ingest(state, extractor)

    except Exception as e:
        state["errors"].append(str(e))
        state["retry_count"] += 1
        state["current_step"] = "failed"
    
    return state