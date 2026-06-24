import logging
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from app.utils.llm_client import default_llm_client
from app.utils.regex_parser import extract_entities_via_regex
from app.utils.prompt_templates import get_entity_extraction_prompt

logger = logging.getLogger(__name__)


class ExtractedEntities(BaseModel):
    """Pydantic schema for structured output extraction."""
    dates: List[str] = Field(default=[], description="List of dates mentioned in the document (e.g. agreement date, payment dates, execution date)")
    amounts: List[str] = Field(default=[], description="List of currency/monetary amounts mentioned in the document (e.g. sale price, advance, balances)")
    parties: List[str] = Field(default=[], description="List of full names of parties involved (e.g. seller, buyer, witnesses, scribe)")
    obligations: List[str] = Field(default=[], description="List of key obligations, conditions, and rules (who must do what)")
    suggested_questions: List[str] = Field(default=[], description="List of suggested questions based on the document type and content")



def extract_entities_via_llm(text: str, language: str = None) -> Dict[str, Any]:
    """Prompts the Groq LLM to extract dates, amounts, parties, and obligations using a single structured call.
    
    Returns a dictionary of list of strings, or a fallback empty dictionary on failure.
    """
    fallback = {
        "dates": [],
        "amounts": [],
        "parties": [],
        "obligations": [],
        "suggested_questions": []
    }
    
    if not text or not text.strip():
        return fallback

    truncated_text = text[:30000]

    is_hindi = language in ("hi", "hi-Latn", "hindi", "hinglish")
    lang_instruction = "in Hindi (Devanagari script)" if is_hindi else "in English"
    questions_lang = "Hindi (Devanagari script)" if is_hindi else "English"

    qa_prompt = get_entity_extraction_prompt(lang_instruction, questions_lang)

    try:
        logger.info("Extracting all entities in a single structured call...")
        structured_llm = default_llm_client.get_structured_llm(ExtractedEntities)
        chain = qa_prompt | structured_llm
        result = chain.invoke({"context": truncated_text})
        
        extracted = {
            "dates": [d.strip() for d in result.dates if d.strip() and len(d) < 50 and "context" not in d.lower()],
            "amounts": [a.strip() for a in result.amounts if a.strip() and len(a) < 50 and "context" not in a.lower()],
            "parties": [n.strip() for n in result.parties if n.strip() and len(n) < 100 and "context" not in n.lower()],
            "obligations": [line.strip("-*• ").strip() for line in result.obligations if line.strip() and len(line) > 5 and "context" not in line.lower()],
            "suggested_questions": [q.strip("? .,:-").strip() + "?" for q in result.suggested_questions if q.strip() and len(q) > 5 and len(q) < 150]
        }

        logger.info("Structured entity extraction completed successfully.")
        return extracted
        
    except Exception as e:
        logger.error("Failed to extract entities via structured LLM: %s", e, exc_info=True)
        return fallback


def merge_extracted_entities(regex_entities: Dict[str, Any], llm_entities: Dict[str, Any]) -> Dict[str, Any]:
    """Merges and deduplicates lists of entities from the regex pass and the LLM pass."""
    merged = {
        "dates": [],
        "amounts": [],
        "parties": [],
        "obligations": [],
        "suggested_questions": []
    }
    
    # Merge and deduplicate helper function
    def merge_key(key: str):
        seen = set()
        combined = regex_entities.get(key, []) + llm_entities.get(key, [])
        for item in combined:
            if key == "amounts":
                import re
                item_clean = re.sub(r'^[\s.,:\-]+|[\s.,]+$', '', item)
            else:
                item_clean = item.strip(" .,:-").strip()
            if item_clean and item_clean.lower() not in seen:
                seen.add(item_clean.lower())
                merged[key].append(item_clean)
                
    for key in ["dates", "amounts", "parties", "obligations"]:
        merge_key(key)
        
    merged["suggested_questions"] = llm_entities.get("suggested_questions", [])
    return merged


def run_full_entity_extraction(text: str, language: str = None) -> Dict[str, Any]:
    """Runs a regex pass followed by an LLM pass and merges the results into a single clean entity dict."""
    logger.info("Starting regex entity extraction pass...")
    regex_entities = extract_entities_via_regex(text)
    
    logger.info("Starting LLM entity extraction pass...")
    llm_entities = extract_entities_via_llm(text, language=language)
    
    logger.info("Merging extraction results...")
    final_entities = merge_extracted_entities(regex_entities, llm_entities)
    return final_entities
