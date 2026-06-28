import logging
import re
from typing import Dict, Any, List, Tuple
from pydantic import BaseModel, Field
from app.utils.llm_client import default_llm_client
from app.utils.regex_parser import (
    extract_entities_via_regex,
    detect_entity_signals,
    window_score,
    normalize_text,
)
from app.utils.prompt_templates import (
    get_entity_extraction_prompt,
    get_entity_extraction_prefiltered_prompt,
)

logger = logging.getLogger(__name__)

# Number of sentences to expand on each side of a matched signal.
# Kept as a module constant for easy tuning; add to settings only if
# environment-specific configuration is required.
_CONTEXT_SENTENCES = 2

# Character threshold above which the pre-filter pipeline is used instead
# of the naive chunking path.  Short documents bypass the filter entirely.
_PREFILTER_THRESHOLD = 8_000

# If the filtered context is still larger than this after Phase 2 expansion,
# the secondary window ranker trims it to the top N windows.
_SECONDARY_RANKER_MAX_WINDOWS = 10

# Rough chars-per-token estimate used when the API does not return usage metadata.
_CHARS_PER_TOKEN_ESTIMATE = 4


class ExtractedEntities(BaseModel):
    """Pydantic schema for structured output extraction."""
    dates: List[str] = Field(default=[], description="List of dates mentioned in the document (e.g. agreement date, payment dates, execution date)")
    amounts: List[str] = Field(default=[], description="List of currency/monetary amounts mentioned in the document (e.g. sale price, advance, balances)")
    parties: List[str] = Field(default=[], description="List of full names of parties involved (e.g. seller, buyer, witnesses, scribe)")
    obligations: List[str] = Field(default=[], description="List of key obligations, conditions, and rules (who must do what)")
    suggested_questions: List[str] = Field(default=[], description="List of suggested questions based on the document type and content")


def clean_boilerplate(text: str) -> str:
    """Cleans up boilerplate such as obvious page numbers/headers from the text,
    with safeguards to avoid deleting legal clause numbers or lines containing key verbs.
    """
    if not text:
        return ""
    
    # Common keywords to preserve lines (verbs/terms indicating obligations or transacting clauses)
    preserve_keywords = {
        "shall", "agree", "agreed", "agrees", "obligated", "obligation", "covenant", "covenants",
        "होगा", "होगी", "करना", "करना होगा", "करता", "करती", "सहमति", "अनुबंध", "शर्त", "शर्ते", "शर्तें"
    }
    
    # Page indicator patterns
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
            
        # Safeguard check: keep lines containing significant keywords
        line_lower = line_strip.lower()
        if any(keyword in line_lower for keyword in preserve_keywords):
            cleaned_lines.append(line)
            continue
            
        # Check if it matches page patterns
        is_boilerplate = False
        for pattern in page_patterns:
            if pattern.match(line_strip):
                is_boilerplate = True
                break
                
        # If it's just a number, check if it's likely a page number (e.g. len > 2 digits).
        # Standalone single/double digits are preserved (could be section/clause markers).
        if re.match(r'^\s*\d+\s*$', line_strip):
            if len(line_strip) > 2:
                is_boilerplate = True
                
        # Remove repetitive dashes/separators
        if re.match(r'^\s*[-*_+=#]{3,}\s*$', line_strip):
            is_boilerplate = True
            
        if not is_boilerplate:
            cleaned_lines.append(line)
            
    return '\n'.join(cleaned_lines)


def merge_chunk_extractions(extractions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Merges and deduplicates lists of entities from all chunk extraction results.
    
    Deduplicates case-insensitively while preserving the casing from the first occurrence.
    Suggested questions are ranked by frequency (consensus) and then sorted.
    """
    merged = {
        "dates": [],
        "amounts": [],
        "parties": [],
        "obligations": [],
        "suggested_questions": []
    }
    
    # Track lowercased entities to enforce uniqueness, mapping to the first encountered original string
    seen = {
        "dates": {},
        "amounts": {},
        "parties": {},
        "obligations": {},
    }
    
    # Aggregate questions first with their frequency count
    question_counts = {}
    
    for ext in extractions:
        for key in ["dates", "amounts", "parties", "obligations"]:
            items = ext.get(key, [])
            for item in items:
                # Basic cleaning
                if key == "amounts":
                    item_clean = re.sub(r'^[\s.,:\-]+|[\s.,]+$', '', item)
                else:
                    item_clean = item.strip(" .,:-").strip()
                
                if not item_clean:
                    continue
                
                item_lower = item_clean.lower()
                if item_lower not in seen[key]:
                    seen[key][item_lower] = item_clean  # Store the first occurrence string
                    merged[key].append(item_clean)
                    
        # Process suggested questions
        questions = ext.get("suggested_questions", [])
        for q in questions:
            q_clean = q.strip("? .,:-").strip()
            if not q_clean:
                continue
            if not q_clean.endswith("?"):
                q_clean += "?"
                
            q_lower = q_clean.lower()
            if q_lower not in question_counts:
                # Store tuple of [first_seen_casing, count]
                question_counts[q_lower] = [q_clean, 1]
            else:
                question_counts[q_lower][1] += 1
                
    # Rank suggested questions:
    # 1. Higher frequency (consensus) first
    # 2. Longer length as tie-breaker
    # Return top 5
    sorted_questions = sorted(
        question_counts.values(),
        key=lambda x: (x[1], len(x[0])),
        reverse=True
    )
    merged["suggested_questions"] = [item[0] for item in sorted_questions[:5]]
    
    return merged


def extract_entities_via_llm(text: str, language: str = None) -> Dict[str, Any]:
    """Prompts the Groq/Gemini LLM to extract dates, amounts, parties, and obligations.
    
    It pre-chunks the text using recursive splitting with 20% overlap, runs structured extraction
    on all chunks in parallel (max_workers=3), and merges the results.
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

    cleaned_text = clean_boilerplate(text)
    if not cleaned_text.strip():
        cleaned_text = text  # Safety fallback if cleaning stripped everything

    # Split text into chunks (~3000 tokens/12000 chars, 20%/2400 chars overlap)
    from app.utils.text_chunking import split_text
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
    
    # Process only up to 15 chunks to avoid abuse or infinite LLM loops
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
            
            # Log actual token usage from the API response
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
                f"Failed structured extraction on chunk {chunk_index + 1}/{len(chunks_to_process)} "
                f"(len={len(chunk_text)}, snippet='{chunk_snippet}'): {e}", 
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
                logger.error(f"Thread for chunk {chunk_idx + 1} raised an exception: {e}")
                
    if not all_extractions:
        return fallback

    logger.info("Merging extracted entities from all chunks...")
    merged_results = merge_chunk_extractions(all_extractions)
    logger.info("Structured entity extraction completed successfully.")
    return merged_results



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
    """Runs a regex pass followed by an LLM pass and merges the results.

    For documents longer than ``_PREFILTER_THRESHOLD`` characters the LLM pass
    uses the hybrid pre-filter pipeline (regex signal detection → context
    window expansion → single LLM call on ~3 k chars) instead of the naive
    chunking path.  Shorter documents continue to use the existing chunked
    path unchanged.
    """
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


# ---------------------------------------------------------------------------
# Pre-filter pipeline helpers
# ---------------------------------------------------------------------------

def build_filtered_context(
    text: str,
    context_sentences: int = _CONTEXT_SENTENCES,
) -> str:
    """Phase 2 of the pre-filter pipeline: context window expansion.

    Locates sentence boundaries in *text*, then for each entity signal found
    by :func:`detect_entity_signals` expands a window of
    ``±context_sentences`` sentences around the match.  Overlapping windows
    are merged (gap tolerance: 200 chars).  The resulting excerpts are joined
    with ``"\u205f\u205f---\u205f\u205f"`` separators that the LLM prompt explicitly
    references.

    **Zero-signal fallback**: if no signals are found (e.g. garbled OCR or a
    purely tabular document) the first 4 000 characters of *text* are returned
    so the LLM always receives something meaningful.
    """
    normalised = normalize_text(text)

    # Phase 1: detect signal positions
    matches: List[Tuple[int, int, str]] = detect_entity_signals(normalised)

    # Zero-signal fallback — never return an empty string
    if not matches:
        logger.warning(
            "detect_entity_signals returned zero matches — falling back to "
            "first 4000 chars of original text."
        )
        return normalised[:4000]

    # Split into sentences; explicitly include Hindi danda । as a boundary
    sentences: List[str] = re.split(r'(?<=[.!?\u0964])\s+', normalised)
    if not sentences:
        return normalised[:4000]

    # Build a list of (sentence_start_char, sentence_end_char) spans
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
        """Return the index of the sentence that contains *char_pos*."""
        for i, (s, e) in enumerate(sent_spans):
            if s <= char_pos <= e:
                return i
        return len(sent_spans) - 1

    # Build raw windows around each signal match
    raw_windows: List[Tuple[int, int]] = []
    for match_start, match_end, _ in matches:
        idx = char_to_sent_idx(match_start)
        lo = max(0, idx - context_sentences)
        hi = min(len(sent_spans) - 1, idx + context_sentences)
        raw_windows.append((sent_spans[lo][0], sent_spans[hi][1]))

    if not raw_windows:
        return normalised[:4000]

    # Merge overlapping / nearby windows (200-char gap tolerance)
    raw_windows.sort(key=lambda w: w[0])
    merged: List[Tuple[int, int]] = [raw_windows[0]]
    for ws, we in raw_windows[1:]:
        prev_s, prev_e = merged[-1]
        if ws <= prev_e + 200:
            merged[-1] = (prev_s, max(prev_e, we))
        else:
            merged.append((ws, we))

    # Extract text slices and join with separator
    parts = [normalised[s:e].strip() for s, e in merged if normalised[s:e].strip()]
    return "\n\n---\n\n".join(parts)


def _log_validation_warnings(
    extracted: Dict[str, Any],
    original_text: str,
) -> None:
    """Cross-check LLM-extracted amounts against currency-pattern amounts.

    Uses :func:`extract_currencies` (which requires explicit currency signals
    such as ``₹``, ``Rs.``, ``INR``, ``lakh``, ``crore``, etc.) to find
    candidate amounts in *original_text*, then warns for any that are absent
    from the LLM *extracted* output and exceed ₹10 000 in value.

    Using currency-aware patterns (rather than a raw digit regex) prevents
    false positives from PIN codes, bank account numbers, reference numbers,
    and other non-financial digit sequences.  Non-blocking — never raises.
    """
    try:
        from app.utils.regex_parser import extract_currencies  # avoid circular import at module level

        llm_amounts_raw = " ".join(extracted.get("amounts", []))

        # extract_currencies requires currency markers — safe against false positives
        regex_amounts = extract_currencies(original_text)

        warned: set = set()  # deduplicate repeated warnings for the same token
        for amt_str in regex_amounts:
            # Parse the numeric value for threshold filtering
            digits_only = re.sub(r"[^\d.]", "", amt_str.replace(",", ""))
            try:
                val = float(digits_only) if digits_only else 0.0
            except ValueError:
                continue

            if val > 10_000 and amt_str not in llm_amounts_raw and amt_str not in warned:
                warned.add(amt_str)
                logger.warning(
                    "Possible missed amount: '%s' (value %.0f) found by regex "
                    "but not in LLM extraction output.",
                    amt_str, val,
                )
    except Exception as exc:  # pragma: no cover
        logger.debug("_log_validation_warnings failed silently: %s", exc)


def _log_token_usage(raw_message: Any, context_label: str = "") -> None:
    """Extract and log token usage from an LLM response message.

    Handles both Groq and Gemini ``response_metadata`` shapes:

    * **Groq** (OpenAI-compatible)::

        response_metadata = {
            "token_usage": {
                "prompt_tokens": 512,
                "completion_tokens": 128,
                "total_tokens": 640
            }, ...
        }

    * **Gemini**::

        response_metadata = {
            "usageMetadata": {
                "promptTokenCount": 512,
                "candidatesTokenCount": 128,
                "totalTokenCount": 640
            }, ...
        }

    Falls back to a ``"metadata unavailable"`` note if neither key is present
    (e.g. when a retry/fallback chain swallows the raw message object).
    """
    try:
        if raw_message is None:
            logger.info(
                "Token usage [%s]: metadata unavailable (raw_message is None).",
                context_label,
            )
            return

        meta = getattr(raw_message, "response_metadata", None) or {}

        # ── Groq / OpenAI-compatible ─────────────────────────────────────────
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

        # ── Gemini ────────────────────────────────────────────────────────────
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

        logger.info(
            "Token usage [%s]: metadata unavailable (keys found: %s).",
            context_label, list(meta.keys()) or "none",
        )
    except Exception as exc:
        logger.debug("_log_token_usage failed silently: %s", exc)


def extract_entities_via_llm_prefiltered(
    text: str,
    language: str = None,
) -> Dict[str, Any]:
    """Single-call LLM extraction on a regex pre-filtered context.

    Pipeline:
    1. **Phase 1 (free)**: :func:`build_filtered_context` uses regex signals
       to select only entity-bearing sentences with ±2 context neighbours.
    2. **Secondary ranker** (if filtered > 8 000 chars): ranks *windows*
       (not individual sentences) by aggregate signal count and keeps the top
       :data:`_SECONDARY_RANKER_MAX_WINDOWS`.  Windows are kept intact so the
       ±2 surrounding context sentences are never discarded.
    3. **Single LLM call** on the trimmed context using
       :func:`get_entity_extraction_prefiltered_prompt`.
    4. **Validation**: :func:`_log_validation_warnings` cross-checks amounts.

    Returns the same ``Dict[str, Any]`` shape as
    :func:`extract_entities_via_llm`.
    """
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

    # Phase 1 + 2: regex pre-filter + context window expansion
    filtered = build_filtered_context(cleaned_text)
    logger.info(
        "Pre-filter: original %d chars → filtered %d chars (%.0f%% reduction).",
        len(cleaned_text),
        len(filtered),
        max(0, 100 - len(filtered) * 100 / max(len(cleaned_text), 1)),
    )

    # Secondary window ranker — rank windows, not sentences
    if len(filtered) > _PREFILTER_THRESHOLD:
        logger.info(
            "Filtered context still %d chars — applying secondary window ranker.",
            len(filtered),
        )
        windows = filtered.split("\n\n---\n\n")
        top_windows = sorted(windows, key=window_score, reverse=True)[
            :_SECONDARY_RANKER_MAX_WINDOWS
        ]
        filtered = "\n\n---\n\n".join(top_windows)
        logger.info(
            "After secondary ranker: %d chars across %d windows.",
            len(filtered), len(top_windows),
        )

    # Build prompt + structured LLM chain
    is_hindi = language in ("hi", "hi-Latn", "hindi", "hinglish")
    lang_instruction = "in Hindi (Devanagari script)" if is_hindi else "in English"
    questions_lang = "Hindi (Devanagari script)" if is_hindi else "English"

    prompt = get_entity_extraction_prefiltered_prompt(lang_instruction, questions_lang)

    # Estimated input tokens before the call (4 chars ≈ 1 token)
    est_input_tokens = len(filtered) // _CHARS_PER_TOKEN_ESTIMATE
    logger.info(
        "Pre-filter LLM call: sending %d chars (~%d estimated input tokens).",
        len(filtered), est_input_tokens,
    )

    try:
        # Use include_raw=True so the raw AIMessage (with response_metadata)
        # is accessible for token-usage logging alongside the parsed output.
        structured_llm = default_llm_client.get_structured_llm(
            ExtractedEntities, include_raw=True
        )
        raw_chain = prompt | structured_llm
        raw_result = raw_chain.invoke({"context": filtered})

        # raw_result is a dict: {"raw": AIMessage, "parsed": ExtractedEntities, "parsing_error": ...}
        if isinstance(raw_result, dict):
            raw_message = raw_result.get("raw")
            result      = raw_result.get("parsed")
            parsing_err = raw_result.get("parsing_error")
        else:
            raw_message = None
            result      = raw_result
            parsing_err = None

        # Log actual token usage from the API response
        _log_token_usage(raw_message, context_label="entity-prefilter")

        if result is None:
            raise ValueError(
                f"Structured output parsing failed: {parsing_err}"
            )

        extracted: Dict[str, Any] = {
            "dates":      [d.strip() for d in result.dates      if d.strip() and len(d) < 50  and "context" not in d.lower()],
            "amounts":    [a.strip() for a in result.amounts    if a.strip() and len(a) < 50  and "context" not in a.lower()],
            "parties":    [n.strip() for n in result.parties    if n.strip() and len(n) < 100 and "context" not in n.lower()],
            "obligations":[line.strip("-*• ").strip() for line in result.obligations
                           if line.strip() and len(line) > 5 and "context" not in line.lower()],
            "suggested_questions": [
                q.strip("? .,:-").strip() + "?"
                for q in result.suggested_questions
                if q.strip() and 5 < len(q) < 150
            ],
        }

        _log_validation_warnings(extracted, text)
        logger.info(
            "Pre-filter extraction done: %d parties, %d dates, %d amounts, %d obligations.",
            len(extracted["parties"]), len(extracted["dates"]),
            len(extracted["amounts"]), len(extracted["obligations"]),
        )
        return extracted

    except Exception as exc:
        logger.error(
            "Pre-filter LLM extraction failed (filtered_len=%d): %s",
            len(filtered), exc, exc_info=True,
        )
        return fallback

