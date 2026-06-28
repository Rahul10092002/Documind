from typing import List, Optional
from langchain_core.documents import Document
from typing_extensions import TypedDict

class DocuMindState(TypedDict):
    document_id:str
    file_path:str
    raw_bytes:bytes
    raw_text:str
    documents:list[Document]
    is_scanned:bool
    char_count:int
    detected_language:str
    language_confidence:float
    prompt_locale:str
    ner_entities:dict
    llm_entities:dict
    merged_entities:dict
    risk_flags_raw:list[dict]
    risk_flags_deduped:list[dict]
    executive_summary:str
    retrieved_chunks:list[Document]
    rag_answer:str
    confidence_score:float
    suggested_questions:list[str]
    draft_reply:str
    current_step:str
    errors:list[str]
    retry_count:int
    pipeline_type:str
   
    
