import re
import logging
import asyncio
from typing import List, Dict, Any
from pydantic import BaseModel, Field

from app.llm import default_llm_client
from app.vectordb import split_text
from app.llm.prompt_templates import get_risk_analysis_prompt
from langchain_core.output_parsers import JsonOutputParser
from langchain_classic.output_parsers import OutputFixingParser

logger = logging.getLogger(__name__)

# Preserve keywords to keep during independent boilerplate cleaning (corrected Hindi spellings)
PRESERVE_KEYWORDS = {
    "shall", "must", "obligated", "liable", "indemnify", "terminate", "penalty", "damages",
    "चाहिए", "बाध्य", "दायित्व"
}

class RiskFlag(BaseModel):
    clause: str = Field(description="The clause text from the document.")
    reason: str = Field(description="The reason why this clause is a risk.")
    level: str = Field(description="The risk level: HIGH, MEDIUM, or LOW.")

class RiskAnalysisOutput(BaseModel):
    risk_flags: List[RiskFlag] = Field(default=[], description="List of identified risk flags.")
    risk_obligation_summary: str = Field(default="", description="A summary of the risks and obligations.")


def clean_text_for_risk(raw_text: str) -> str:
    """Pre-processes raw text to remove page numbers, repetitive headers/footers,
    normalize whitespace, and clean boilerplate while preserving legal risk/obligation indicators.
    """
    if not raw_text:
        return ""

    lines = raw_text.split('\n')
    cleaned_lines = []

    # Page indicator patterns
    page_patterns = [
        re.compile(r'^\s*page\s+\d+\s*$', re.IGNORECASE),
        re.compile(r'^\s*page\s+\d+\s+of\s+\d+\s*$', re.IGNORECASE),
        re.compile(r'^\s*-\s*\d+\s*-\s*$', re.IGNORECASE),
        re.compile(r'^\s*\[\s*\d+\s*\]\s*$', re.IGNORECASE),
        re.compile(r'^\s*\d+\s+of\s+\d+\s*$', re.IGNORECASE),
        re.compile(r'^\s*पृष्ठ\s*\d+\s*$', re.IGNORECASE),
        re.compile(r'^\s*पेज\s*\d+\s*$', re.IGNORECASE),
    ]

    for line in lines:
        line_strip = line.strip()
        if not line_strip:
            cleaned_lines.append("")
            continue

        line_lower = line_strip.lower()

        # Keep lines containing significant keywords
        if any(kw in line_lower for kw in PRESERVE_KEYWORDS):
            cleaned_lines.append(line)
            continue

        # Check page patterns
        is_page_num = False
        for pattern in page_patterns:
            if pattern.match(line_strip):
                is_page_num = True
                break
        if is_page_num:
            continue

        # Remove repetitive dashes/separators
        if re.match(r'^\s*[-*_+=#]{3,}\s*$', line_strip):
            continue

        cleaned_lines.append(line)

    cleaned_text = '\n'.join(cleaned_lines)

    # Normalize whitespace
    cleaned_text = re.sub(r'[ \t]+', ' ', cleaned_text)
    cleaned_text = re.sub(r'\r', '', cleaned_text)
    cleaned_text = re.sub(r'\n{3,}', '\n\n', cleaned_text)

    return cleaned_text.strip()


def merge_and_arbitrate_risks(risk_flags_list: List[List[RiskFlag]]) -> List[Dict[str, Any]]:
    """Deduplicates risk flags and arbitrates conflicting risk levels.
    Risk level priority: HIGH > MEDIUM > LOW.
    """
    level_priority = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
    merged_flags = {}

    for chunk_flags in risk_flags_list:
        for flag in chunk_flags:
            clause = flag.clause.strip()
            reason = flag.reason.strip()
            level = flag.level.strip().upper()

            if not clause:
                continue

            if level not in level_priority:
                level = "LOW"

            clause_lower = clause.lower()
            if clause_lower not in merged_flags:
                merged_flags[clause_lower] = {
                    "clause": clause,
                    "reason": reason,
                    "level": level
                }
            else:
                existing_level = merged_flags[clause_lower]["level"]
                if level_priority[level] > level_priority[existing_level]:
                    merged_flags[clause_lower]["level"] = level
                    merged_flags[clause_lower]["reason"] = reason
                elif level_priority[level] == level_priority[existing_level]:
                    # Same level - prefer the more detailed (longer) reason
                    if len(reason) > len(merged_flags[clause_lower]["reason"]):
                        merged_flags[clause_lower]["reason"] = reason

    return list(merged_flags.values())


# NOTE: This function is intentionally slow (up to ~5 min for 15 chunks at Semaphore(3)).
# Must be called from a background task (Celery/FastAPI BackgroundTasks) — never from a
# synchronous request handler or you will hit gateway timeouts.
async def run_risk_flagging(raw_text: str, prompt_locale: str, char_count: int) -> Dict[str, Any]:
    """Runs the risk flagging and analysis flow on raw_text."""
    # 1. Boilerplate Cleaning
    cleaned_text = clean_text_for_risk(raw_text)
    if not cleaned_text:
        return {
            "risk_flags_raw": [],
            "risk_flags_deduped": [],
            "executive_summary": "",
            "executive_summary_available": False,
            "analysis_coverage": {
                "chunks_total": 0,
                "chunks_timed_out": 0,
                "is_partial": False
            }
        }

    # 2. Chunking Decision
    chunks = split_text(
        cleaned_text,
        chunk_size=12000,
        chunk_overlap=2400,
        separators=["\n\n", "\n", ". ", " ", ""]
    )

    # Limit to max 15 chunks for resource safety
    chunks = chunks[:15]

    response_lang = "Hindi (in Devanagari script)" if prompt_locale == "hindi" else "English"

    # Set up parser and chain exactly as in agenerate_risk_and_draft
    parser = JsonOutputParser(pydantic_object=RiskAnalysisOutput)
    fixing_parser = OutputFixingParser.from_llm(
        parser=parser,
        llm=default_llm_client.get_primary_llm()
    )
    # Activate truncation note if char_count exceeds 30,000 characters
    prompt_template = get_risk_analysis_prompt(
        response_lang=response_lang, 
        is_truncated=(char_count > 30000)
    ).partial(
        format_instructions=parser.get_format_instructions()
    )
    llm = default_llm_client.get_resilient_llm()
    chain = prompt_template | llm | fixing_parser

    sem = asyncio.Semaphore(3)
    CHUNK_TIMEOUT = 60.0  # seconds - budget for 12k-char chunk + OutputFixingParser retry
    timed_out_chunks = 0

    async def analyze_chunk(chunk: str, idx: int) -> RiskAnalysisOutput:
        # Nonlocal access to timed_out_chunks is safe since asyncio is single-threaded;
        # this must be reviewed if ThreadPoolExecutor or multiprocessing is introduced.
        nonlocal timed_out_chunks
        async with sem:
            try:
                res = await asyncio.wait_for(chain.ainvoke({"context": chunk}), timeout=CHUNK_TIMEOUT)
                
                # Normalize response format into RiskAnalysisOutput
                if isinstance(res, dict):
                    flags = []
                    for f in res.get("risk_flags", []):
                        lvl = f.get("level", f.get("severity", "LOW"))
                        flags.append(RiskFlag(
                            clause=f.get("clause", ""),
                            reason=f.get("reason", ""),
                            level=lvl
                        ))
                    return RiskAnalysisOutput(
                        risk_flags=flags,
                        risk_obligation_summary=res.get("risk_obligation_summary", "")
                    )
                return res
            except asyncio.TimeoutError:
                timed_out_chunks += 1
                logger.warning(f"Chunk {idx} timed out after {CHUNK_TIMEOUT}s")
                return RiskAnalysisOutput(risk_flags=[], risk_obligation_summary="")
            except Exception as e:
                logger.error(f"Error analyzing risk for chunk {idx}: {e}")
                return RiskAnalysisOutput(risk_flags=[], risk_obligation_summary="")

    tasks = [analyze_chunk(c, i) for i, c in enumerate(chunks)]
    results = await asyncio.gather(*tasks)

    # 3. Deduplication and Severity Arbitration Pass
    raw_flags_list = []
    chunk_summaries = []
    raw_flags_dicts = []

    for res in results:
        if not res:
            continue
        raw_flags_list.append(res.risk_flags)
        if res.risk_obligation_summary.strip():
            chunk_summaries.append(res.risk_obligation_summary.strip())
        
        # Collect raw flags normalized to uppercase
        for f in res.risk_flags:
            raw_flags_dicts.append({
                "clause": f.clause,
                "reason": f.reason,
                "level": f.level.strip().upper() if f.level else "LOW"
            })

    deduped_flags = merge_and_arbitrate_risks(raw_flags_list)

    # 4. Generate Executive Summary
    executive_summary = ""
    executive_summary_available = False
    
    if chunk_summaries:
        combined_summaries_text = "\n\n".join(
            f"--- Section {i+1} ---\n{summary}" 
            for i, summary in enumerate(chunk_summaries)
        )
        
        consolidated_summary_prompt = (
            "You are an expert legal advisor and document intelligence assistant.\n"
            "Your task is to merge the following section summaries of a document into a single, cohesive, formal executive summary.\n"
            f"The final summary MUST be written in {response_lang} and be between 200 and 300 words.\n"
            "It must cover:\n"
            "1. Key obligations of each party\n"
            "2. Key financial terms and conditions\n"
            "3. Top identified risks and liabilities\n\n"
            "Avoid repeating identical points. Organize the final summary into logical paragraphs.\n"
            "Section Summaries:\n"
            f"{combined_summaries_text}\n\n"
            "Generate the consolidated summary text. Do NOT add any preamble, greeting, or conversational explanation."
        )
        
        try:
            messages = [
                {"role": "system", "content": "You are a document analysis assistant."},
                {"role": "user", "content": consolidated_summary_prompt}
            ]
            # Consolidating summary uses a lighter 15s budget
            executive_summary = await asyncio.wait_for(default_llm_client.aask(messages), timeout=15.0)
            executive_summary_available = True
        except Exception as e:
            logger.error("Failed to consolidate summaries: %s", e)
            executive_summary = "\n\n".join(chunk_summaries)
            executive_summary_available = True
    else:
        # Ran, but no chunks produced a summary
        if len(chunks) > 0 and timed_out_chunks < len(chunks):
            executive_summary_available = True
        else:
            executive_summary_available = False

    return {
        "risk_flags_raw": raw_flags_dicts,
        "risk_flags_deduped": deduped_flags,
        "executive_summary": executive_summary,
        "executive_summary_available": executive_summary_available,
        "analysis_coverage": {
            "chunks_total": len(chunks),
            "chunks_timed_out": timed_out_chunks,
            "is_partial": timed_out_chunks > 0
        }
    }
