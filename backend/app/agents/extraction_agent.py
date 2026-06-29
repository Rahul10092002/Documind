import logging
from typing import List, Dict, Any

from .state import DocuMindState
from app.extractors.entity_extraction import (
    clean_legal_text,
    run_spacy_ner,
    run_hf_ner,
    run_regex_extraction,
    run_llm_chunked_extraction,
    merge_all_entities,
)

logger = logging.getLogger(__name__)




async def extraction_agent(state: DocuMindState) -> DocuMindState:
    """Asynchronous extraction agent. Pre-processes text, executes NER tools and LLM,
    and merges/deduplicates extracted legal entities.
    """
    state["current_step"] = "extracting_ner"
    
    try:
        clean_result = clean_legal_text(state.get("raw_text", ""), state.get("documents", []))
        text = clean_result["clean_text"]
        state["detected_boilerplate"] = clean_result["boilerplates"]
        
        if not text:
            state["llm_entities"] = {
                "dates": [], "amounts": [], "parties": [], "obligations": [], "suggested_questions": []
            }
            state["ner_entities"] = {
                "spacy": {
                    "contracting_parties": [], "timeline_dates": [], "monetary_amounts": [],
                    "locations": [], "signatories": []
                },
                "huggingface": {
                    "contracting_parties": [], "locations": [], "signatories": []
                },
                "regex": {
                    "dates": [], "amounts": []
                }
            }
            state["merged_entities"] = {
                "parties": [], "dates": [], "amounts": [], "obligations": [], "locations": [], "suggested_questions": []
            }
            return state

        locale = state.get("prompt_locale", "english")

        # Run extraction steps
        spacy_ents = run_spacy_ner(text, locale)
        hf_ents = run_hf_ner(text, locale)
        regex_ents = run_regex_extraction(text)
        llm_ents = await run_llm_chunked_extraction(text)

        # Merge and deduplicate
        merged = merge_all_entities(spacy_ents, hf_ents, regex_ents, llm_ents)

        # Update state
        state["llm_entities"] = llm_ents
        state["ner_entities"] = {
            "spacy": spacy_ents,
            "huggingface": hf_ents,
            "regex": regex_ents
        }
        state["merged_entities"] = merged
        
        state["current_step"] = f"Entities extracted: {len(merged['parties'])} parties, {len(merged['dates'])} dates, {len(merged['amounts'])} amounts"

    except Exception as e:
        logger.error(f"Extraction agent failed: {e}")
        state.setdefault("errors", []).append(str(e))
        state["retry_count"] = state.get("retry_count", 0) + 1
        state["current_step"] = "failed"
        
    return state
