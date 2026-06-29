import logging
logger = logging.getLogger(__name__)
from .state import DocuMindState
from app.extractors import detect_language

def detect_language_agent(state: DocuMindState) -> DocuMindState:
    state["current_step"] = "detecting_language"
    try:
        text=state['raw_text']

        language, confidence = detect_language(text)
        if not language:
            language = "en"
            confidence = 1.0

        # Map detected language to prompt_locale
        if language in ("hi", "hi-Latn"):
            prompt_locale = "hindi"
        else:
            prompt_locale = "english"

        logger.info(f"Language detected: {language} with confidence {confidence}, mapped locale: {prompt_locale}")
        state.update({
            'detected_language': language,
            'language_confidence': confidence,
            'prompt_locale': prompt_locale,
            'current_step': f"Language detected: {language} (confidence: {confidence})",
        })
    except Exception as e:
        state["errors"].append(str(e))
        state["retry_count"] += 1
        state["current_step"] = "failed"
        
    return state