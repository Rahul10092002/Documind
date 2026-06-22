import logging
from langdetect import detect, LangDetectException

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Common Romanized Hindi / Hinglish words used as a lightweight heuristic.
# These are high-frequency words that rarely appear in plain English text.
# ---------------------------------------------------------------------------
_HINGLISH_WORDS: frozenset[str] = frozenset(
    {
        "hai", "hain", "nahi", "nahin", "kya", "aur", "yeh", "woh",
        "mein", "hum", "tum", "aap", "karo", "karna", "karein", "kar",
        "bhi", "sirf", "lekin", "magar", "par", "to", "ki", "ke", "ka",
        "ek", "do", "teen", "accha", "theek", "bilkul", "zaroor",
        "abhi", "phir", "bahut", "bohot", "thoda", "zyada", "baat",
        "log", "dil", "din", "raat", "ghar", "kaam", "naam", "pyaar",
    }
)

# Devanagari Unicode block: U+0900–U+097F
_DEVANAGARI_START = 0x0900
_DEVANAGARI_END = 0x097F

# Minimum ratio of Devanagari chars to declare the text as Hindi/Devanagari.
_DEVANAGARI_RATIO_THRESHOLD = 0.10

# Minimum proportion of Hinglish tokens to trigger the "hi-Latn" code.
_HINGLISH_TOKEN_THRESHOLD = 0.08


def detect_language(text: str) -> str | None:
    """Detect the dominant language of *text* and return an ISO 639-1 code.

    Detection strategy (applied in priority order):

    1. **Devanagari scan** – If ≥10 % of non-whitespace characters fall in the
       Devanagari Unicode block (U+0900–U+097F) the text is classified as
       Hindi (``"hi"``).  This catches Hindi documents and Hinglish writing
       that mixes Devanagari with Latin script, avoiding the frequent
       misclassification by ``langdetect`` as Bengali or Nepali.

    2. **Romanized Hinglish heuristic** – Tokenise the first 2 000 characters
       into lowercase words and count how many match a curated set of
       high-frequency Hindi loanwords written in Latin script.  If the hit
       ratio exceeds 8 % of all tokens the function returns ``"hi-Latn"``
       (a BCP-47 tag indicating Hindi in Latin script / code-switched
       Hinglish), so downstream prompts can be tuned for bilingual content.

    3. **langdetect fallback** – For all other text (plain English, other
       languages) the standard ``langdetect`` library is used.

    Returns ``None`` if the input is empty or detection fails at every stage.
    """
    if not text:
        return None

    snippet = text[:2000]

    # ── Stage 1: Devanagari Unicode range check ──────────────────────────────
    non_ws_chars = [ch for ch in snippet if not ch.isspace()]
    if non_ws_chars:
        devanagari_count = sum(
            1
            for ch in non_ws_chars
            if _DEVANAGARI_START <= ord(ch) <= _DEVANAGARI_END
        )
        ratio = devanagari_count / len(non_ws_chars)
        if ratio >= _DEVANAGARI_RATIO_THRESHOLD:
            logger.debug(
                "Devanagari ratio %.2f ≥ threshold → classifying as 'hi'", ratio
            )
            return "hi"

    # ── Stage 2: Romanized Hinglish heuristic ────────────────────────────────
    tokens = [tok for tok in snippet.lower().split() if tok.isalpha()]
    if tokens:
        hit_count = sum(1 for tok in tokens if tok in _HINGLISH_WORDS)
        hit_ratio = hit_count / len(tokens)
        if hit_ratio >= _HINGLISH_TOKEN_THRESHOLD:
            logger.debug(
                "Hinglish hit ratio %.2f (%d/%d tokens) → classifying as 'hi-Latn'",
                hit_ratio,
                hit_count,
                len(tokens),
            )
            return "hi-Latn"

    # ── Stage 3: langdetect fallback ─────────────────────────────────────────
    try:
        return detect(snippet)
    except LangDetectException:
        logger.warning("langdetect failed to identify language for snippet.")
        return None
