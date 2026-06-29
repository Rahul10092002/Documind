import logging
from .state import DocuMindState
from app.extractors.risk_flagging_utils import run_risk_flagging

logger = logging.getLogger(__name__)


async def risk_flagging_agent(state: DocuMindState) -> DocuMindState:
    """Asynchronous risk flagging agent. Clean independent boilerplate removal,
    chunked risk evaluation, and deduplication/arbitration.
    """
    state["current_step"] = "flagging_risks"
    
    try:
        raw_text = state.get("raw_text", "")
        prompt_locale = state.get("prompt_locale", "english")
        char_count = state.get("char_count", len(raw_text))

        if not raw_text:
            state["risk_flags_raw"] = []
            state["risk_flags_deduped"] = []
            state["executive_summary"] = ""
            state["risk_analysis_partial"] = False
            state["executive_summary_available"] = False
            state["current_step"] = "No text provided for risk analysis"
            return state

        # Run the utilities flow
        result = await run_risk_flagging(
            raw_text=raw_text,
            prompt_locale=prompt_locale,
            char_count=char_count
        )

        # Update state with the results (appending raw flags as per append mode reducer)
        state["risk_flags_raw"] = state.get("risk_flags_raw", []) + result.get("risk_flags_raw", [])
        state["risk_flags_deduped"] = result.get("risk_flags_deduped", [])
        state["executive_summary"] = result.get("executive_summary", "")
        
        coverage = result.get("analysis_coverage", {})
        is_partial = coverage.get("is_partial", False)
        state["risk_analysis_partial"] = is_partial
        state["executive_summary_available"] = result.get("executive_summary_available", False)

        if is_partial:
            state["current_step"] = (
                f"Risk analysis complete (PARTIAL — {coverage.get('chunks_timed_out', 0)} chunks dropped): "
                f"{len(state['risk_flags_deduped'])} risks identified"
            )
        else:
            state["current_step"] = f"Risk analysis complete: {len(state['risk_flags_deduped'])} risks identified"

    except Exception as e:
        logger.error(f"Risk flagging agent failed: {e}")
        state.setdefault("errors", []).append(str(e))
        state["retry_count"] = state.get("retry_count", 0) + 1
        state["current_step"] = "failed"

    return state