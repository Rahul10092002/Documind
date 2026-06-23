import json
import logging
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from app.utils.rag import get_llm
from app.utils.regex_parser import extract_entities_via_regex

logger = logging.getLogger(__name__)


class ExtractedEntities(BaseModel):
    """Pydantic schema for structured output extraction."""
    dates: List[str] = Field(default=[], description="List of dates mentioned in the document (e.g. agreement date, payment dates, execution date)")
    amounts: List[str] = Field(default=[], description="List of currency/monetary amounts mentioned in the document (e.g. sale price, advance, balances)")
    parties: List[str] = Field(default=[], description="List of full names of parties involved (e.g. seller, buyer, witnesses, scribe)")
    obligations: List[str] = Field(default=[], description="List of key obligations, conditions, and rules (who must do what)")


def clean_and_parse_json(response_text: str) -> Dict[str, Any]:
    """Cleans potential Markdown code block wrapping from the LLM response,
    extracts the JSON substring, and parses it as JSON.
    """
    cleaned = response_text.strip()
    
    # Try to find the JSON object boundaries to ignore conversational prefixes/suffixes
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        cleaned = cleaned[first_brace:last_brace + 1]
    
    # If the response is wrapped in ```json ... ``` or ``` ... ```, extract the inner text
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
        
    return json.loads(cleaned)


def extract_entities_via_llm(text: str, language: str = None) -> Dict[str, Any]:
    """Prompts the Groq LLM to extract dates, amounts, parties, and obligations using sequential QA prompts.
    
    Returns a dictionary of list of strings, or a fallback empty dictionary on failure.
    """
    fallback = {
        "dates": [],
        "amounts": [],
        "parties": [],
        "obligations": []
    }
    
    if not text or not text.strip():
        return fallback

    truncated_text = text[:30000]

    qa_prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are a document analysis assistant. Use ONLY the provided document context to answer the user's question.\n"
            "STRICT RULES:\n"
            "1. Use ONLY the provided document context. Do NOT use outside knowledge, template examples, or make up names, dates, or details.\n"
            "2. Return ONLY the requested list. Do NOT write any introduction (like 'Here are the...'), explanations, or concluding remarks.\n"
            "3. If the answer is not present in the context, reply with an empty string."
        )),
        ("human", (
            "Document Context:\n"
            "<document>\n"
            "{context}\n"
            "</document>\n\n"
            "Question: {question}"
        ))
    ])

    extracted = {
        "dates": [],
        "amounts": [],
        "parties": [],
        "obligations": []
    }

    try:
        llm = get_llm()
        
        # 1. Extract Parties
        logger.info("Extracting parties via QA...")
        q_parties = (
            "Identify ONLY the direct parties to this legal transaction: "
            "seller (विक्रेता), buyer (क्रेता), and witnesses (गवाह/साक्षी). "
            "Do NOT include: fathers, deceased relatives, neighbors, road names, or government entities. "
            "Return ONLY their names as a comma-separated list."
        )
        msg_parties = qa_prompt.invoke({"context": truncated_text, "question": q_parties})
        resp_parties = llm.invoke(msg_parties)
        names = [n.strip() for n in resp_parties.content.split(",") if n.strip()]
        extracted["parties"] = [n for n in names if len(n) < 100 and "context" not in n.lower()]

        # 2. Extract Dates
        logger.info("Extracting dates via QA...")
        q_dates = (
            "Identify all the dates mentioned in this document (e.g., execution date, registration date, payment dates). "
            "Return ONLY these dates as a comma-separated list. Do not write any intro or explanation."
        )
        msg_dates = qa_prompt.invoke({"context": truncated_text, "question": q_dates})
        resp_dates = llm.invoke(msg_dates)
        dates = [d.strip() for d in resp_dates.content.split(",") if d.strip()]
        extracted["dates"] = [d for d in dates if len(d) < 50 and "context" not in d.lower()]

        # 3. Extract Amounts
        logger.info("Extracting amounts via QA...")
        q_amounts = (
            "Identify all the monetary or currency amounts mentioned in this document (e.g., sale price, advance, balance). "
            "Return ONLY these amounts as a comma-separated list. Do not write any intro or explanation."
        )
        msg_amounts = qa_prompt.invoke({"context": truncated_text, "question": q_amounts})
        resp_amounts = llm.invoke(msg_amounts)
        amounts = [a.strip() for a in resp_amounts.content.split(",") if a.strip()]
        extracted["amounts"] = [a for a in amounts if len(a) < 50 and "context" not in a.lower()]

        # 4. Extract Obligations
        logger.info("Extracting obligations via QA...")
        q_obligations = (
            "List the key obligations, duties, or conditions imposed on the parties in this document (who must do what). "
            "Return them as a clean bulleted list (one obligation per line) in Devanagari/Hindi script. Do not write any intro or explanation."
        )
        msg_obligations = qa_prompt.invoke({"context": truncated_text, "question": q_obligations})
        resp_obligations = llm.invoke(msg_obligations)
        lines = [line.strip("-*• ").strip() for line in resp_obligations.content.splitlines() if line.strip()]
        extracted["obligations"] = [line for line in lines if len(line) > 5 and "context" not in line.lower()]

        logger.info("Groq LLM sequential QA extraction completed successfully.")
        return extracted
        
    except Exception as e:
        logger.error("Failed to extract entities via LLM QA: %s", e, exc_info=True)
        return fallback


def merge_extracted_entities(regex_entities: Dict[str, Any], llm_entities: Dict[str, Any]) -> Dict[str, Any]:
    """Merges and deduplicates lists of entities from the regex pass and the LLM pass."""
    merged = {
        "dates": [],
        "amounts": [],
        "parties": [],
        "obligations": []
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
