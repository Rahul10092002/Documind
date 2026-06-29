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
        "se", "tha", "thi",
    }
)

# Devanagari Unicode block: U+0900–U+097F
_DEVANAGARI_START = 0x0900
_DEVANAGARI_END = 0x097F

# Minimum ratio of Devanagari chars to declare the text as Hindi/Devanagari.
_DEVANAGARI_RATIO_THRESHOLD = 0.10

# Minimum proportion of Hinglish tokens to trigger the "hi-Latn" code.
_HINGLISH_TOKEN_THRESHOLD = 0.08


_ENGLISH_WORDS: frozenset[str] = frozenset(
    {
        "the", "and", "of", "to", "in", "is", "that", "it", "was", "for",
        "on", "are", "as", "with", "this", "by", "an", "be", "shall",
        "agreement", "contract", "party", "parties", "herein", "thereof"
    }
)


def detect_language(text: str) -> tuple[str | None, float]:
    """Detect the dominant language of *text* and return (ISO 639-1 code, confidence).

    Detection strategy (applied in priority order):

    1. **Devanagari scan** – If ≥10 % of non-whitespace characters fall in the
       Devanagari Unicode block (U+0900–U+097F) the text is classified as
       Hindi (``"hi"``).

    2. **Romanized Hinglish heuristic** – Tokenise the first 2 000 characters
       into lowercase words and count how many match a curated set of
       high-frequency Hindi loanwords written in Latin script.

    3. **English word heuristic** – Count high-frequency English words in the
       tokenized snippet. If above threshold, instantly classify as English (``"en"``).

    4. **langdetect fallback** – For all other text (plain English, other
       languages) the standard ``langdetect`` library is used.

    Returns ``(None, 0.0)`` if the input is empty or detection fails.
    """
    if not text:
        return None, 0.0

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
            return "hi", ratio

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
            return "hi-Latn", 0.75

    # ── Stage 3: English word heuristic ──────────────────────────────────────
    if tokens:
        eng_count = sum(1 for tok in tokens if tok in _ENGLISH_WORDS)
        eng_ratio = eng_count / len(tokens)
        if eng_ratio >= 0.05:
            logger.debug(
                "English hit ratio %.2f (%d/%d tokens) → classifying as 'en'",
                eng_ratio,
                eng_count,
                len(tokens),
            )
            return "en", 0.99

    # ── Stage 3: langdetect fallback ─────────────────────────────────────────
    try:
        lang = detect(snippet)
        if lang:
            return lang, 0.60
        return None, 0.0
    except LangDetectException:
        logger.warning("langdetect failed to identify language for snippet.")
        return None, 0.0
