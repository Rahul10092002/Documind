class DocuMindBaseError(Exception):
    """Base exception class for DocuMind application."""
    status_code: int = 500
    detail: str = "Internal server error"

    def __init__(self, detail: str = None):
        self.detail = detail or self.__class__.detail
        super().__init__(self.detail)


class DocumentNotFoundError(DocuMindBaseError):
    status_code = 404
    detail = "Document not found"


class ExtractionFailedError(DocuMindBaseError):
    status_code = 422
    detail = "Entity extraction failed"


class UnsupportedFileTypeError(DocuMindBaseError):
    status_code = 415
    detail = "File type not supported. Supported: PDF, DOCX, TXT"


class LLMProviderError(DocuMindBaseError):
    status_code = 503
    detail = "LLM provider unavailable. Try again later."


class VectorStoreError(DocuMindBaseError):
    status_code = 503
    detail = "Vector store unavailable"


class LanguageDetectionError(DocuMindBaseError):
    status_code = 422
    detail = "Could not detect document language"
