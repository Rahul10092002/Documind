import logging
import re
import spacy
import asyncio
from difflib import SequenceMatcher
from typing import Dict, Any, List, Tuple
from transformers import pipeline
from pydantic import BaseModel, Field

from app.llm import default_llm_client
from app.llm.prompt_templates import (
    get_entity_extraction_prompt,
    get_entity_extraction_prefiltered_prompt,
)
from app.extractors.regex_parser import (
    extract_entities_via_regex,
    detect_entity_signals,
    window_score,
    normalize_text,
)
from app.vectordb.text_chunking import split_text

logger = logging.getLogger(__name__)

# Constants
_CONTEXT_SENTENCES = 2
_PREFILTER_THRESHOLD = 8_000
_SECONDARY_RANKER_MAX_WINDOWS = 10
_CHARS_PER_TOKEN_ESTIMATE = 4

MAX_LLM_CHUNKS = 10  # Cost control: limit number of chunks processed via LLM
HF_TOKEN_LIMIT = 400
HF_OVERLAP = 50
LLM_TIMEOUT_SECONDS = 15.0

# Global caches for loaded models
_nlp_cache: Dict[str, spacy.language.Language] = {}
_hf_nlp_cache: Dict[str, Any] = {}

# Pre-compiled Regex patterns
_PAGE_PATTERNS = [
    re.compile(r'^\s*page\s+\d+\s*$', re.IGNORECASE),
    re.compile(r'^\s*page\s+\d+\s+of\s+\d+\s*$', re.IGNORECASE),
    re.compile(r'^\s*-\s*\d+\s*-\s*$', re.IGNORECASE),
    re.compile(r'^\s*\[\s*\d+\s*\]\s*$', re.IGNORECASE),
    re.compile(r'^\s*\d+\s+of\s+\d+\s*$', re.IGNORECASE),
    re.compile(r'^\s*पृष्ठ\s*\d+\s*$', re.IGNORECASE),
    re.compile(r'^\s*पेज\s*\d+\s*$', re.IGNORECASE),
]

_BOILERPLATE_PHRASES = ["WHEREAS", "NOW THEREFORE", "IN WITNESS WHEREOF", "अनुबंध", "शर्तें"]

class ExtractedEntities(BaseModel):
    """Pydantic schema for structured output extraction."""
    dates: List[str] = Field(default=[], description="List of dates mentioned in the document (e.g. agreement date, payment dates, execution date)")
    amounts: List[str] = Field(default=[], description="List of currency/monetary amounts mentioned in the document (e.g. sale price, advance, balances)")
    parties: List[str] = Field(default=[], description="List of full names of parties involved (e.g. seller, buyer, witnesses, scribe)")
    obligations: List[str] = Field(default=[], description="List of key obligations, conditions, and rules (who must do what)")
    suggested_questions: List[str] = Field(default=[], description="List of suggested questions based on the document type and content")


def get_spacy_model(locale: str) -> spacy.language.Language:
    """Retrieve or load the appropriate spaCy model based on the locale."""
    model_name = "xx_ent_wiki_sm" if locale == "hindi" else "en_core_web_lg"
    
    if model_name not in _nlp_cache:
        logger.info(f"Loading spaCy model: {model_name}")
        print(f"Loading spaCy model: {model_name}...")
        try:
            _nlp_cache[model_name] = spacy.load(model_name)
        except OSError as e:
            logger.error(f"spaCy model '{model_name}' not found at runtime. Fallback to blank model: {e}")
            _nlp_cache[model_name] = spacy.blank("hi" if locale == "hindi" else "en")
                
    return _nlp_cache[model_name]


def get_hf_pipeline(locale: str) -> Any:
    """Retrieve or load the appropriate HuggingFace NER pipeline based on the locale."""
    hf_model_name = "mirfan899/hindi-bert-ner" if locale == "hindi" else "dslim/bert-base-NER"
    
    if hf_model_name not in _hf_nlp_cache:
        logger.info(f"Loading HuggingFace NER pipeline: {hf_model_name}")
        print(f"Loading/Downloading HuggingFace NER pipeline: {hf_model_name} (this might take a moment)...")
        _hf_nlp_cache[hf_model_name] = pipeline(
            "token-classification", 
            model=hf_model_name, 
            aggregation_strategy="simple"
        )
    return _hf_nlp_cache[hf_model_name]


def clean_boilerplate(text: str) -> str:
    """Cleans up boilerplate such as obvious page numbers/headers from the text,
    with safeguards to avoid deleting legal clause numbers or lines containing key verbs.
    """
    if not text:
        return ""
    
    preserve_keywords = {
        "shall", "agree", "agreed", "agrees", "obligated", "obligation", "covenant", "covenants",
        "होगा", "होगी", "करना", "करना होगा", "करता", "करती", "सहमति", "अनुबंध", "शर्त", "शर्ते", "शर्तें"
    }
    
    page_patterns = [
        re.compile(r'^\s*page\s+\d+\s*$', re.IGNORECASE),
        re.compile(r'^\s*page\s+\d+\s+of\s+\d+\s*$', re.IGNORECASE),
        re.compile(r'^\s*-\s*\d+\s*-\s*$', re.IGNORECASE),
        re.compile(r'^\s*\[\s*\d+\s*\]\s*$', re.IGNORECASE),
        re.compile(r'^\s*\d+\s+of\s+\d+\s*$', re.IGNORECASE),
    ]
    
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        line_strip = line.strip()
        if not line_strip:
            cleaned_lines.append("")
            continue
            
        line_lower = line_strip.lower()
        if any(keyword in line_lower for keyword in preserve_keywords):
            cleaned_lines.append(line)
            continue
            
        is_boilerplate = False
        for pattern in page_patterns:
            if pattern.match(line_strip):
                is_boilerplate = True
                break
                
        if re.match(r'^\s*\d+\s*$', line_strip):
            if len(line_strip) > 2:
                is_boilerplate = True
                
        if re.match(r'^\s*[-*_+=#]{3,}\s*$', line_strip):
            is_boilerplate = True
            
        if not is_boilerplate:
            cleaned_lines.append(line)
            
    return '\n'.join(cleaned_lines)


def clean_legal_text(raw_text: str, documents: List[Any]) -> Dict[str, Any]:
    """Pre-processes raw text to remove page numbers, repetitive headers/footers,
    normalize whitespace, and flag/extract legal boilerplate phrases.
    """
    if not raw_text:
        return {"clean_text": "", "boilerplates": []}

    repetitive_lines = set()
    
    if len(documents) > 1:
        line_counts = {}
        for page in documents:
            page_lines = [line.strip().lower() for line in page.page_content.split('\n') if line.strip()]
            unique_page_lines = set()
            for idx, line in enumerate(page_lines):
                if idx < 3 or idx >= len(page_lines) - 3:
                    unique_page_lines.add(line)
            
            for line in unique_page_lines:
                line_counts[line] = line_counts.get(line, 0) + 1
        
        for line, count in line_counts.items():
            if count / len(documents) >= 0.5:
                if len(line) > 5 and not any(bp in line for bp in ["whereas", "now therefore", "witness"]):
                    repetitive_lines.add(line)

    lines = raw_text.split('\n')
    cleaned_lines = []
    boilerplates = []
    
    for phrase in _BOILERPLATE_PHRASES:
        if phrase.lower() in raw_text.lower():
            logger.info(f"Flagged legal boilerplate phrase: '{phrase}'")
            boilerplates.append(phrase)

    for line in lines:
        line_strip = line.strip()
        if not line_strip:
            cleaned_lines.append("")
            continue

        is_page_num = False
        for pattern in _PAGE_PATTERNS:
            if pattern.match(line_strip):
                is_page_num = True
                break
        if is_page_num:
            continue

        if line_strip.lower() in repetitive_lines:
            continue

        cleaned_lines.append(line)

    cleaned_text = '\n'.join(cleaned_lines)
    
    cleaned_text = re.sub(r'[ \t]+', ' ', cleaned_text)
    cleaned_text = re.sub(r'\r', '', cleaned_text)
    cleaned_text = re.sub(r'\n{3,}', '\n\n', cleaned_text)
    
    return {
        "clean_text": cleaned_text.strip(),
        "boilerplates": sorted(list(set(boilerplates)))
    }


def merge_chunk_extractions(extractions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Merges and deduplicates lists of entities from all chunk extraction results."""
    merged = {
        "dates": [],
        "amounts": [],
        "parties": [],
        "obligations": [],
        "suggested_questions": []
    }
    
    seen = {
        "dates": {},
        "amounts": {},
        "parties": {},
        "obligations": {},
    }
    
    question_counts = {}
    
    for ext in extractions:
        for key in ["dates", "amounts", "parties", "obligations"]:
            items = ext.get(key, [])
            for item in items:
                if key == "amounts":
                    item_clean = re.sub(r'^[\s.,:\-]+|[\s.,]+$', '', item)
                else:
                    item_clean = item.strip(" .,:-").strip()
                
                if not item_clean:
                    continue
                
                item_lower = item_clean.lower()
                if item_lower not in seen[key]:
                    seen[key][item_lower] = item_clean
                    merged[key].append(item_clean)
                    
        questions = ext.get("suggested_questions", [])
        for q in questions:
            q_clean = q.strip("? .,:-").strip()
            if not q_clean:
                continue
            if not q_clean.endswith("?"):
                q_clean += "?"
                
            q_lower = q_clean.lower()
            if q_lower not in question_counts:
                question_counts[q_lower] = [q_clean, 1]
            else:
                question_counts[q_lower][1] += 1
                
    sorted_questions = sorted(
        question_counts.values(),
        key=lambda x: (x[1], len(x[0])),
        reverse=True
    )
    merged["suggested_questions"] = [item[0] for item in sorted_questions[:5]]
    
    return merged


def run_spacy_ner(text: str, locale: str) -> Dict[str, List[str]]:
    """Run spaCy NER extraction and return categorized lists."""
    nlp = get_spacy_model(locale)
    doc = nlp(text)
    
    contracting_parties = []
    timeline_dates = []
    monetary_amounts = []
    locations = []
    signatories = []
    
    for ent in doc.ents:
        val = ent.text.strip()
        label = ent.label_
        if not val:
            continue
            
        if label == "ORG":
            contracting_parties.append(val)
        elif label == "DATE":
            timeline_dates.append(val)
        elif label == "MONEY":
            monetary_amounts.append(val)
        elif label in ("GPE", "LOC"):
            locations.append(val)
        elif label in ("PERSON", "PER"):
            signatories.append(val)

    def get_ordered_unique(lst: List[str]) -> List[str]:
        seen = set()
        return [x for x in lst if not (x.lower() in seen or seen.add(x.lower()))]

    return {
        "contracting_parties": get_ordered_unique(contracting_parties),
        "timeline_dates": get_ordered_unique(timeline_dates),
        "monetary_amounts": get_ordered_unique(monetary_amounts),
        "locations": get_ordered_unique(locations),
        "signatories": get_ordered_unique(signatories)
    }


def run_hf_ner(text: str, locale: str) -> Dict[str, List[str]]:
    """Chunk the text and run HuggingFace NER inference."""
    hf_contracting_parties = []
    hf_locations = []
    hf_signatories = []

    try:
        hf_nlp = get_hf_pipeline(locale)
        hf_chunks = split_text(text, chunk_size=HF_TOKEN_LIMIT, chunk_overlap=HF_OVERLAP)
        
        hf_results = []
        for chunk in hf_chunks:
            hf_results.extend(hf_nlp(chunk))
        
        for ent in hf_results:
            score = ent.get("score", 0.0)
            if score <= 0.85:
                continue
                
            val = ent.get("word", "").strip()
            val = val.replace("##", "").strip()
            if not val:
                continue
                
            label = ent.get("entity_group", ent.get("entity", "")).upper()
            
            if "ORG" in label:
                hf_contracting_parties.append(val)
            elif "LOC" in label or "GPE" in label:
                hf_locations.append(val)
            elif "PER" in label or "PERSON" in label:
                hf_signatories.append(val)
                
    except Exception as hf_err:
        logger.error(f"HuggingFace NER pipeline failed: {hf_err}")

    def get_ordered_unique(lst: List[str]) -> List[str]:
        seen = set()
        return [x for x in lst if not (x.lower() in seen or seen.add(x.lower()))]

    return {
        "contracting_parties": get_ordered_unique(hf_contracting_parties),
        "locations": get_ordered_unique(hf_locations),
        "signatories": get_ordered_unique(hf_signatories)
    }


def run_regex_extraction(text: str) -> Dict[str, List[str]]:
    """Extract dates and amounts via pre-defined regex patterns."""
    regex_dates = []
    regex_amounts = []
    try:
        regex_res = extract_entities_via_regex(text)
        regex_dates = regex_res.get("dates", [])
        regex_amounts = regex_res.get("amounts", [])
    except Exception as regex_err:
        logger.warning(f"Regex pre-extraction failed: {regex_err}")
        
    def get_ordered_unique(lst: List[str]) -> List[str]:
        seen = set()
        return [x for x in lst if not (x.lower() in seen or seen.add(x.lower()))]

    return {
        "dates": get_ordered_unique(regex_dates),
        "amounts": get_ordered_unique(regex_amounts)
    }


async def run_llm_chunked_extraction(text: str) -> Dict[str, List[str]]:
    """Split text into chunks, run LLM struct extraction in parallel."""
    llm_entities = {
        "dates": [],
        "amounts": [],
        "parties": [],
        "obligations": [],
        "suggested_questions": []
    }
    try:
        chunks = split_text(text, chunk_size=2500, chunk_overlap=300)
        target_chunks = chunks[:MAX_LLM_CHUNKS]
        
        sem = asyncio.Semaphore(3)
        
        async def invoke_chunk(chunk: str):
            async with sem:
                structured_llm = default_llm_client.get_structured_llm(ExtractedEntities)
                prompt = (
                    "Extract the following entities from this document chunk:\n"
                    "1. Dates (agreement date, execution dates, payment deadlines)\n"
                    "2. Amounts (monetary figures, price, consideration)\n"
                    "3. Parties (full names of contracting parties, buyer, seller, witnesses)\n"
                    "4. Obligations (specific duties/conditions, who must do what)\n"
                    "5. Suggested Questions (contextual follow-up questions)\n\n"
                    f"Chunk Content:\n{chunk}"
                )
                return await asyncio.wait_for(structured_llm.ainvoke(prompt), timeout=LLM_TIMEOUT_SECONDS)
            
        if target_chunks:
            tasks = [invoke_chunk(c) for c in target_chunks]
            llm_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            valid_extractions = []
            for res in llm_results:
                if isinstance(res, Exception):
                    err_msg = f"{type(res).__name__}: {res}" if str(res) else type(res).__name__
                    logger.error(f"LLM chunk extraction failed or timed out: {err_msg}")
                elif res is not None:
                    valid_extractions.append(res.model_dump() if hasattr(res, "model_dump") else res.dict())
            
            llm_entities = merge_chunk_extractions(valid_extractions)
    except Exception as llm_err:
        logger.error(f"Parallel LLM chunk extraction failed: {llm_err}")
        
    return llm_entities


def merge_all_entities(
    spacy_ents: Dict[str, List[str]], 
    hf_ents: Dict[str, List[str]], 
    regex_ents: Dict[str, List[str]], 
    llm_ents: Dict[str, List[str]]
) -> Dict[str, List[str]]:
    """Merge and deduplicate entities from all extraction sources."""
    
    def is_fuzzy_match(s1: str, s2: str) -> bool:
        if abs(len(s1) - len(s2)) > 5:
            return False
        if s1.lower() == s2.lower():
            return True
        return SequenceMatcher(None, s1.strip().lower(), s2.strip().lower()).ratio() > 0.85

    def normalize_date(date_str: str) -> str:
        ds = date_str.lower().strip().strip(" .,:-")
        ds = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', ds)
        match_num = re.search(r'(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})', ds)
        if match_num:
            day, month, year = match_num.groups()
            return f"{year}-{int(month):02d}-{int(day):02d}"
        match_iso = re.search(r'(\d{4})[/\-\.](\d{1,2})[/\-\.](\d{1,2})', ds)
        if match_iso:
            year, month, day = match_iso.groups()
            return f"{year}-{int(month):02d}-{int(day):02d}"
        return ds

    def normalize_amount(amount_str: str) -> str:
        cleaned = amount_str.lower().strip()
        cleaned = re.sub(r'[₹$€£\s,/\-]+', '', cleaned)
        cleaned = cleaned.replace("rs.", "").replace("inr", "").replace("rupees", "")
        return cleaned

    merged_parties: List[str] = []
    raw_parties_sources = [
        llm_ents.get("parties", []),
        hf_ents.get("signatories", []) + hf_ents.get("contracting_parties", []),
        spacy_ents.get("signatories", []) + spacy_ents.get("contracting_parties", [])
    ]
    for source in raw_parties_sources:
        for party in source:
            p_clean = party.strip()
            if not p_clean:
                continue
            is_dup = False
            for existing in merged_parties:
                if existing.lower() == p_clean.lower() or is_fuzzy_match(existing, p_clean):
                    is_dup = True
                    break
            if not is_dup:
                merged_parties.append(p_clean)

    merged_dates: List[str] = []
    seen_dates_normalized = set()
    raw_dates_sources = [
        llm_ents.get("dates", []),
        spacy_ents.get("timeline_dates", []),
        regex_ents.get("dates", [])
    ]
    for source in raw_dates_sources:
        for date_val in source:
            d_clean = date_val.strip()
            if not d_clean:
                continue
            norm = normalize_date(d_clean)
            if norm not in seen_dates_normalized:
                seen_dates_normalized.add(norm)
                merged_dates.append(d_clean)

    merged_amounts: List[str] = []
    seen_amounts_normalized = set()
    raw_amounts_sources = [
        llm_ents.get("amounts", []),
        spacy_ents.get("monetary_amounts", []),
        regex_ents.get("amounts", [])
    ]
    for source in raw_amounts_sources:
        for amt_val in source:
            a_clean = amt_val.strip()
            if not a_clean:
                continue
            norm = normalize_amount(a_clean)
            if norm not in seen_amounts_normalized:
                seen_amounts_normalized.add(norm)
                merged_amounts.append(a_clean)

    merged_locations: List[str] = []
    raw_locations_sources = [
        hf_ents.get("locations", []),
        spacy_ents.get("locations", [])
    ]
    for source in raw_locations_sources:
        for loc in source:
            l_clean = loc.strip()
            if not l_clean:
                continue
            is_dup = False
            for existing in merged_locations:
                if existing.lower() == l_clean.lower() or is_fuzzy_match(existing, l_clean):
                    is_dup = True
                    break
            if not is_dup:
                merged_locations.append(l_clean)

    return {
        "parties": merged_parties,
        "dates": merged_dates,
        "amounts": merged_amounts,
        "obligations": list(llm_ents.get("obligations", [])),
        "locations": merged_locations,
        "suggested_questions": list(llm_ents.get("suggested_questions", []))
    }


def extract_entities_via_llm(text: str, language: str = None) -> Dict[str, Any]:
    """Prompts the Groq/Gemini LLM to extract dates, amounts, parties, and obligations."""
    fallback = {
        "dates": [],
        "amounts": [],
        "parties": [],
        "obligations": [],
        "suggested_questions": []
    }
    
    if not text or not text.strip():
        return fallback

    cleaned_text = clean_boilerplate(text)
    if not cleaned_text.strip():
        cleaned_text = text

    chunks = split_text(
        cleaned_text,
        chunk_size=12000,
        chunk_overlap=2400,
        separators=["\n\n", "\n", ". ", " ", ""]
    )
    
    if not chunks:
        return fallback

    is_hindi = language in ("hi", "hi-Latn", "hindi", "hinglish")
    lang_instruction = "in Hindi (Devanagari script)" if is_hindi else "in English"
    questions_lang = "Hindi (Devanagari script)" if is_hindi else "English"

    qa_prompt = get_entity_extraction_prompt(lang_instruction, questions_lang)
    
    max_chunks = 15
    chunks_to_process = chunks[:max_chunks]
    
    logger.info(f"Starting structured entity extraction for {len(chunks_to_process)} chunks in parallel...")
    
    def extract_chunk(chunk_text: str, chunk_index: int) -> Dict[str, Any]:
        chunk_snippet = chunk_text[:100].replace('\n', ' ')
        try:
            logger.info(f"Extracting entities from chunk {chunk_index + 1}/{len(chunks_to_process)} (len={len(chunk_text)}, snippet='{chunk_snippet}')...")
            structured_llm = default_llm_client.get_structured_llm(ExtractedEntities, include_raw=True)
            chain = qa_prompt | structured_llm
            raw_result = chain.invoke({"context": chunk_text})
            
            if isinstance(raw_result, dict):
                raw_message = raw_result.get("raw")
                result = raw_result.get("parsed")
                parsing_err = raw_result.get("parsing_error")
            else:
                raw_message = None
                result = raw_result
                parsing_err = None
            
            _log_token_usage(raw_message, context_label=f"entity-chunk-{chunk_index + 1}")
            
            if result is None:
                raise ValueError(
                    f"Structured output parsing failed: {parsing_err}"
                )
            
            chunk_extracted = {
                "dates": [d.strip() for d in result.dates if d.strip() and len(d) < 50 and "context" not in d.lower()],
                "amounts": [a.strip() for a in result.amounts if a.strip() and len(a) < 50 and "context" not in a.lower()],
                "parties": [n.strip() for n in result.parties if n.strip() and len(n) < 100 and "context" not in n.lower()],
                "obligations": [line.strip("-*• ").strip() for line in result.obligations if line.strip() and len(line) > 5 and "context" not in line.lower()],
                "suggested_questions": [q.strip("? .,:-").strip() + "?" for q in result.suggested_questions if q.strip() and len(q) > 5 and len(q) < 150]
            }
            logger.info(f"Successfully extracted entities from chunk {chunk_index + 1}/{len(chunks_to_process)}.")
            return chunk_extracted
        except Exception as e:
            logger.error(
                f"Failed structured extraction on chunk {chunk_index + 1}/{len(chunks_to_process)}: {e}", 
                exc_info=True
            )
            return fallback

    all_extractions = []
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(extract_chunk, chunk, idx): idx for idx, chunk in enumerate(chunks_to_process)}
        for future in as_completed(futures):
            chunk_idx = futures[future]
            try:
                res = future.result()
                all_extractions.append(res)
            except Exception as e:
                logger.error(f"Thread for chunk {chunk_idx + 1} raised exception: {e}")
                
    if not all_extractions:
        return fallback

    logger.info("Merging extracted entities from all chunks...")
    merged_results = merge_chunk_extractions(all_extractions)
    return merged_results


def merge_extracted_entities(regex_entities: Dict[str, Any], llm_entities: Dict[str, Any]) -> Dict[str, Any]:
    """Merges and deduplicates lists of entities from regex pass and LLM pass."""
    merged = {
        "dates": [],
        "amounts": [],
        "parties": [],
        "obligations": [],
        "suggested_questions": []
    }
    
    def merge_key(key: str):
        seen = set()
        combined = regex_entities.get(key, []) + llm_entities.get(key, [])
        for item in combined:
            if key == "amounts":
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
    """Runs a regex pass followed by an LLM pass and merges the results."""
    logger.info("Starting regex entity extraction pass...")
    regex_entities = extract_entities_via_regex(text)

    logger.info("Starting LLM entity extraction pass...")
    if len(text) > _PREFILTER_THRESHOLD:
        logger.info(
            "Document length %d chars exceeds threshold %d — using pre-filter pipeline.",
            len(text), _PREFILTER_THRESHOLD,
        )
        llm_entities = extract_entities_via_llm_prefiltered(text, language=language)
    else:
        llm_entities = extract_entities_via_llm(text, language=language)

    logger.info("Merging extraction results...")
    final_entities = merge_extracted_entities(regex_entities, llm_entities)
    return final_entities


def build_filtered_context(
    text: str,
    context_sentences: int = _CONTEXT_SENTENCES,
) -> str:
    """Phase 2 of the pre-filter pipeline: context window expansion."""
    normalised = normalize_text(text)

    matches: List[Tuple[int, int, str]] = detect_entity_signals(normalised)

    if not matches:
        logger.warning("detect_entity_signals returned zero matches — falling back to first 4000 chars.")
        return normalised[:4000]

    sentences: List[str] = re.split(r'(?<=[.!?\u0964])\s+', normalised)
    if not sentences:
        return normalised[:4000]

    sent_spans: List[Tuple[int, int]] = []
    cursor = 0
    for sent in sentences:
        start = normalised.find(sent, cursor)
        if start == -1:
            start = cursor
        end = start + len(sent)
        sent_spans.append((start, end))
        cursor = end

    def char_to_sent_idx(char_pos: int) -> int:
        for i, (s, e) in enumerate(sent_spans):
            if s <= char_pos <= e:
                return i
        return len(sent_spans) - 1

    raw_windows: List[Tuple[int, int]] = []
    for match_start, match_end, _ in matches:
        idx = char_to_sent_idx(match_start)
        lo = max(0, idx - context_sentences)
        hi = min(len(sent_spans) - 1, idx + context_sentences)
        raw_windows.append((sent_spans[lo][0], sent_spans[hi][1]))

    if not raw_windows:
        return normalised[:4000]

    raw_windows.sort(key=lambda w: w[0])
    merged: List[Tuple[int, int]] = [raw_windows[0]]
    for ws, we in raw_windows[1:]:
        prev_s, prev_e = merged[-1]
        if ws <= prev_e + 200:
            merged[-1] = (prev_s, max(prev_e, we))
        else:
            merged.append((ws, we))

    parts = [normalised[s:e].strip() for s, e in merged if normalised[s:e].strip()]
    return "\n\n---\n\n".join(parts)


def _log_validation_warnings(
    extracted: Dict[str, Any],
    original_text: str,
) -> None:
    """Cross-check LLM-extracted amounts against currency-pattern amounts."""
    try:
        from app.extractors.regex_parser import extract_currencies

        llm_amounts_raw = " ".join(extracted.get("amounts", []))
        regex_amounts = extract_currencies(original_text)

        warned: set = set()
        for amt_str in regex_amounts:
            digits_only = re.sub(r"[^\d.]", "", amt_str.replace(",", ""))
            try:
                val = float(digits_only) if digits_only else 0.0
            except ValueError:
                continue

            if val > 10_000 and amt_str not in llm_amounts_raw and amt_str not in warned:
                warned.add(amt_str)
                logger.warning(
                    "Possible missed amount: '%s' (value %.0f) found by regex but not in LLM extraction.",
                    amt_str, val,
                )
    except Exception as exc:
        logger.debug("_log_validation_warnings failed: %s", exc)


def _log_token_usage(raw_message: Any, context_label: str = "") -> None:
    """Extract and log token usage from an LLM response message."""
    try:
        if raw_message is None:
            logger.info("Token usage [%s]: metadata unavailable (raw_message is None).", context_label)
            return

        meta = getattr(raw_message, "response_metadata", None) or {}

        usage = meta.get("token_usage") or meta.get("usage")
        if usage:
            prompt_tokens     = usage.get("prompt_tokens",     usage.get("input_tokens",  "?"))
            completion_tokens = usage.get("completion_tokens", usage.get("output_tokens", "?"))
            total_tokens      = usage.get("total_tokens", "?")
            logger.info(
                "Token usage [%s]: prompt=%s  completion=%s  total=%s",
                context_label, prompt_tokens, completion_tokens, total_tokens,
            )
            return

        gemini_usage = meta.get("usageMetadata")
        if gemini_usage:
            prompt_tokens     = gemini_usage.get("promptTokenCount",     "?")
            completion_tokens = gemini_usage.get("candidatesTokenCount", "?")
            total_tokens      = gemini_usage.get("totalTokenCount",      "?")
            logger.info(
                "Token usage [%s]: prompt=%s  completion=%s  total=%s",
                context_label, prompt_tokens, completion_tokens, total_tokens,
            )
            return

        logger.info("Token usage [%s]: metadata unavailable (keys found: %s).", context_label, list(meta.keys()) or "none")
    except Exception as exc:
        logger.debug("_log_token_usage failed: %s", exc)


def extract_entities_via_llm_prefiltered(
    text: str,
    language: str = None,
) -> Dict[str, Any]:
    """Single-call LLM extraction on a regex pre-filtered context."""
    fallback: Dict[str, Any] = {
        "dates": [],
        "amounts": [],
        "parties": [],
        "obligations": [],
        "suggested_questions": [],
    }

    if not text or not text.strip():
        return fallback

    cleaned_text = clean_boilerplate(text)
    if not cleaned_text.strip():
        cleaned_text = text

    filtered = build_filtered_context(cleaned_text)
    logger.info(
        "Pre-filter: original %d chars → filtered %d chars (%.0f%% reduction).",
        len(cleaned_text),
        len(filtered),
        max(0, 100 - len(filtered) * 100 / max(len(cleaned_text), 1)),
    )

    if len(filtered) > _PREFILTER_THRESHOLD:
        logger.info("Filtered context still %d chars — applying secondary window ranker.", len(filtered))
        windows = filtered.split("\n\n---\n\n")
        top_windows = sorted(windows, key=window_score, reverse=True)[:_SECONDARY_RANKER_MAX_WINDOWS]
        filtered = "\n\n---\n\n".join(top_windows)
        logger.info("After secondary ranker: %d chars across %d windows.", len(filtered), len(top_windows))

    is_hindi = language in ("hi", "hi-Latn", "hindi", "hinglish")
    lang_instruction = "in Hindi (Devanagari script)" if is_hindi else "in English"
    questions_lang = "Hindi (Devanagari script)" if is_hindi else "English"

    prompt = get_entity_extraction_prefiltered_prompt(lang_instruction, questions_lang)
    est_input_tokens = len(filtered) // _CHARS_PER_TOKEN_ESTIMATE
    logger.info("Pre-filter LLM call: sending %d chars (~%d estimated input tokens).", len(filtered), est_input_tokens)

    try:
        structured_llm = default_llm_client.get_structured_llm(ExtractedEntities, include_raw=True)
        raw_chain = prompt | structured_llm
        raw_result = raw_chain.invoke({"context": filtered})

        if isinstance(raw_result, dict):
            raw_message = raw_result.get("raw")
            result      = raw_result.get("parsed")
            parsing_err = raw_result.get("parsing_error")
        else:
            raw_message = None
            result      = raw_result
            parsing_err = None

        _log_token_usage(raw_message, context_label="entity-prefilter")

        if result is None:
            raise ValueError(f"Structured output parsing failed: {parsing_err}")

        extracted: Dict[str, Any] = {
            "dates":      [d.strip() for d in result.dates      if d.strip() and len(d) < 50  and "context" not in d.lower()],
            "amounts":    [a.strip() for a in result.amounts    if a.strip() and len(a) < 50  and "context" not in a.lower()],
            "parties":    [n.strip() for n in result.parties    if n.strip() and len(n) < 100 and "context" not in n.lower()],
            "obligations":[line.strip("-*• ").strip() for line in result.obligations if line.strip() and len(line) > 5 and "context" not in line.lower()],
            "suggested_questions": [q.strip("? .,:-").strip() + "?" for q in result.suggested_questions if q.strip() and 5 < len(q) < 150],
        }

        _log_validation_warnings(extracted, text)
        return extracted

    except Exception as exc:
        logger.error("Pre-filter LLM extraction failed: %s", exc, exc_info=True)
        return fallback
