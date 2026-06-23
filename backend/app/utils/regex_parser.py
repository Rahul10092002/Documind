import re


def normalize_text(text: str) -> str:
    """Remove invisible Unicode artifacts that break Devanagari regex matching.
    PyMuPDF injects U+200B (Zero Width Space) between syllables in Devanagari text.
    """
    text = text.replace('\u200b', ' ')   # Zero Width Space → regular space
    text = text.replace('\u200c', '')    # Zero Width Non-Joiner → remove
    text = text.replace('\u200d', '')    # Zero Width Joiner → remove
    text = text.replace('\x00', '')      # Null byte (pdfplumber artifact) → remove
    text = re.sub(r' {2,}', ' ', text)  # Collapse multiple spaces
    return text.strip()



# ---------------------------------------------------------------------------
# Regex Patterns for Date Extraction
# ---------------------------------------------------------------------------

# 1. Numerical dates: DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD (English & Devanagari digits)
_NUMERICAL_DATE_PATTERN = re.compile(
    r"(?<!\w)(?:0?[1-9]|[12][0-9]|3[01]|[०-३]?[०-९])[/\-\.](?:0?[1-9]|1[0-2]|[०]?[१-९]|[१][०-२])[/\-\.](?:\d{4}|\d{2}|[०-९]{4}|[०-९]{2})(?!\w)"
    r"|"
    r"(?<!\w)(?:\d{4}|[०-९]{4})[/\-\.](?:0?[1-9]|1[0-2]|[०]?[१-९]|[१][०-२])[/\-\.](?:0?[1-9]|[12][0-9]|3[01]|[०-३]?[०-९])(?!\w)"
)

# 2. English textual dates: "15th August 2025", "Aug 15, 2025"
_ENG_MONTHS = (
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
)
_ENG_TEXTUAL_DATE_PATTERN = re.compile(
    rf"(?<!\w)(?:(?:0?[1-9]|[12][0-9]|3[01])(?:st|nd|rd|th)?[\s\-]+{_ENG_MONTHS}[\s\-]+(?:\d{{4}}|\d{{2}})|{_ENG_MONTHS}[\s\-]+(?:0?[1-9]|[12][0-9]|3[01])(?:st|nd|rd|th)?(?:\s*,\s*|[\s\-]+)(?:\d{{4}})|(?:0?[1-9]|[12][0-9]|3[01])(?:st|nd|rd|th)?[\s\-]+{_ENG_MONTHS})(?!\w)",
    re.IGNORECASE
)

# 3. Hindi textual dates: "18 जून 2026", "१५ अगस्त २०२५"
_HINDI_MONTHS = (
    r"(?:जनवरी|फ़रवरी|फरवरी|मार्च|अप्रैल|मई|जून|जुलाई|अगस्त|सितम्बर|सितंबर|"
    r"अक्टूबर|अक्टुबर|नवम्बर|नवंबर|दिसम्बर|दिसंबर|"
    r"चैत्र|वैशाख|ज्येष्ठ|आषाढ़|श्रावण|भाद्रपद|भादो|आश्विन|क्वार|कार्तिक|मार्गशीर्ष|अगहन|पौष|माघ|फाल्गुन)"
)
_HINDI_TEXTUAL_DATE_PATTERN = re.compile(
    rf"(?<!\w)(?:[0-3]?[0-9]|[०-३]?[०-९])[\s\-]*{_HINDI_MONTHS}[\s\-]*(?:,\s*)?(?:\d{{4}}|[०-९]{{4}})?(?!\w)"
)

# Labeled dates: prefixed by दिनांक, तारीख, तिथि (e.g. दिनांक २१/१२/२०२३, तारीख 15)
_LABELED_DATE_PATTERN = re.compile(
    r"(?:दिनांक|तारीख|तिथि)\s*[:\-]?\s*"
    r"(?:[0-3]?[0-9]|[०-३]?[०-९])"
    r"(?:\s*[/\-\.]\s*(?:[0-1]?[0-9]|[०-१]?[०-९]))?"
    r"(?:\s*[/\-\.]\s*(?:\d{2,4}|[०-९]{2,4}))?"
    rf"(?:\s+{_HINDI_MONTHS})?"
    r"(?:\s+(?:\d{4}|[०-९]{4}))?",
    re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Regex Patterns for Currency Amounts
# ---------------------------------------------------------------------------

_CURRENCY_SYMBOLS = r"(?:₹|Rs\.?|RS\.?|INR|रुपयों|रुपये|रुपया|रु\.?|Rupees?|rupees?)"
_SCALES = r"(?:lakhs?|crores?|millions?|thousands?|लाख|करोड़|हजार|हज़ार)"
_NUMERIC_PATTERN = r"(?:\d{1,3}(?:,\d{2})*(?:,\d{3})|\d{1,3}(?:,\d{3})+|\d+)"
_DEV_NUMERIC_PATTERN = r"(?:[०-९]{1,3}(?:,[०-९]{2})*(?:,[०-९]{3})|[०-९]{1,3}(?:,[०-९]{3})+|[०-९]+)"

# Matches: ₹50,000, Rs. 10 Lakh, ₹ 1.5 Crore, ₹५०,०००, रु. १० लाख
_PREFIX_CURRENCY_PATTERN = re.compile(
    rf"(?:₹|Rs\.?|RS\.?|INR|रु\.?)\s*(?:{_NUMERIC_PATTERN}|{_DEV_NUMERIC_PATTERN})(?:\.\d{{1,2}})?(?:\s*{_SCALES})?(?:/-)?",
    re.IGNORECASE
)

# Use (?!\w) instead of \b at the end because Devanagari vowel signs like 'े' (in 'रुपये')
# are considered non-word characters (Marks) in Python's regex module, causing \b to fail.
_SUFFIX_CURRENCY_PATTERN = re.compile(
    rf"(?<!\w)(?:{_NUMERIC_PATTERN}|{_DEV_NUMERIC_PATTERN})(?:\.\d{{1,2}})?\s*(?:/-)?\s*(?:{_CURRENCY_SYMBOLS}|{_SCALES}\s*{_CURRENCY_SYMBOLS}?)(?!\w)",
    re.IGNORECASE
)

_HINDI_NUMBER_WORDS = (
    r"(?:एक|दो|तीन|चार|पाँच|पांच|छः|छह|सात|आठ|नौ|दस|"
    r"ग्यारह|बारह|तेरह|चौदह|पंद्रह|सोलह|सत्रह|अठारह|उन्नीस|बीस|"
    r"इक्कीस|बाईस|तेईस|चौबीस|पच्चीस|छब्बीस|सत्ताईस|अट्ठाईस|उनतीस|"
    r"तीस|चालीस|पचास|साठ|सत्तर|अस्सी|नब्बे|"
    r"सौ|हजार|लाख|करोड़)"
)
_WORD_AMOUNT_PATTERN = re.compile(
    rf"{_HINDI_NUMBER_WORDS}(?:\s+{_HINDI_NUMBER_WORDS}){{1,6}}\s*(?:रुपये|रुपया|रु\.?)?\s*(?:मात्र)?",
    re.IGNORECASE
)


def extract_dates(text: str) -> list[str]:
    """Extract date patterns from Hindi/English legal text."""
    if not text:
        return []

    found = []
    for match in _NUMERICAL_DATE_PATTERN.finditer(text):
        found.append(match.group(0).strip())
    for match in _ENG_TEXTUAL_DATE_PATTERN.finditer(text):
        found.append(match.group(0).strip())
    for match in _HINDI_TEXTUAL_DATE_PATTERN.finditer(text):
        found.append(match.group(0).strip())
    for match in _LABELED_DATE_PATTERN.finditer(text):
        found.append(match.group(0).strip())

    seen = set()
    unique_dates = []
    for d in found:
        d_clean = d.strip(" .,:-")
        if d_clean and d_clean.lower() not in seen:
            seen.add(d_clean.lower())
            unique_dates.append(d_clean)

    return unique_dates


def extract_currencies(text: str) -> list[str]:
    """Extract currency amounts from Hindi/English legal text."""
    if not text:
        return []

    found = []
    for match in _PREFIX_CURRENCY_PATTERN.finditer(text):
        found.append(match.group(0).strip())
    for match in _SUFFIX_CURRENCY_PATTERN.finditer(text):
        found.append(match.group(0).strip())
    for match in _WORD_AMOUNT_PATTERN.finditer(text):
        val = match.group(0).strip()
        if len(val) > 3:
            found.append(val)

    seen = set()
    unique_currencies = []
    for c in found:
        c_clean = re.sub(r'^[\s.,:\-]+|[\s.,]+$', '', c)
        if c_clean and c_clean.lower() not in seen:
            seen.add(c_clean.lower())
            unique_currencies.append(c_clean)

    # Fragment filter — remove entries that are substrings of a larger amount
    def _remove_fragments(amounts: list[str]) -> list[str]:
        final = []
        for amt in unique_currencies:
            is_fragment = any(amt != other and amt in other for other in unique_currencies)
            if not is_fragment:
                final.append(amt)
        return final

    return _remove_fragments(unique_currencies)


def extract_entities_via_regex(text: str) -> dict:
    """Run all regex extractors on input text and return organized dictionary."""
    text = normalize_text(text)
    return {
        "dates": extract_dates(text),
        "amounts": extract_currencies(text),
        "parties": [],       # handled by LLM pass
        "obligations": []    # handled by LLM pass
    }
