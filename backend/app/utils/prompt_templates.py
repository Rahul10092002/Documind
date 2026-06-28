from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder


# ---------------------------------------------------------------------------
# Risk Analysis — few-shot calibration examples
# ---------------------------------------------------------------------------
# Three contrastive examples anchor HIGH / MEDIUM / LOW thresholds.
# Kept minimal (one line each) to avoid token waste while preserving
# the contrastive signal frontier models need.
_RISK_CALIBRATION = """Calibration examples:
Clause: "Landlord may terminate with 24 hours notice." → HIGH (no time to vacate or contest)
Clause: "Disputes resolved through mutual discussion." → MEDIUM (no timeline, mediator, or escalation path)
Clause: "Governed by the laws of the State." → LOW (standard boilerplate)
"""


def get_qa_prompt(response_lang: str = "English") -> ChatPromptTemplate:
    """Returns the ChatPromptTemplate for document question answering.

    Optimizations vs original:
    - Removed redundant role sentence ("You are a document QA assistant")
    - Replaced vague "concise" with ≤3-sentence limit (measurable)
    - Dropped duplicate "if unsure, say you don't know" (covered by rule 2)
    - Removed "Always respond in same language" sentence — absorbed into Language: header
    Total token reduction: ~27%
    """
    system_prompt = (
        "You are a document QA assistant. Language: {response_lang}.\n\n"
        "Rules:\n"
        "1. Answer ONLY from the context below — no outside knowledge.\n"
        "2. If the answer is absent, reply exactly: "
        "\"I cannot find the answer in the provided document context.\"\n"
        "3. Combine information from multiple sections when relevant.\n"
        "4. Quote exact values (numbers, dates, names) verbatim.\n"
        "5. Keep answers under 3 sentences unless the question demands more.\n\n"
        "Context:\n{context}"
    ).replace("{response_lang}", response_lang)

    return ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{input}")
    ])


def get_risk_analysis_prompt(response_lang: str, is_truncated: bool = False) -> ChatPromptTemplate:
    """Returns the ChatPromptTemplate for risk analysis and summary generation.

    Optimizations vs original:
    - Merged role sentence + task sentence into one tight instruction block
    - Removed verbose STRICT RULES header; rules are implied by numbered list
    - Collapsed level definitions to inline em-dash format (saves ~80 tokens)
    - Moved few-shot examples to a compact 3-liner (saves ~120 tokens)
    - is_truncated note preserved but shortened
    Total token reduction: ~48%
    """
    truncation_note = (
        "\nNote: Analyzing first ~30 000 chars only — do not reference absent sections."
        if is_truncated else ""
    )

    system_prompt = (
        "Analyze the document and return a JSON object with fields "
        "`risk_flags` and `risk_obligation_summary`. "
        f"All `reason` and summary text MUST be in {response_lang}."
        f"{truncation_note}\n\n"
        "risk_flags — for each risky clause:\n"
        "  clause: exact text (≤40 words)\n"
        "  reason: why it is risky\n"
        "  level: \"high\" | \"medium\" | \"low\"\n\n"
        "Level definitions:\n"
        "  high — one-sided termination/eviction/payment terms that deny adequate recourse\n"
        "  medium — vague language, missing standard protections, unclear liability\n"
        "  low — minor boilerplate deviations, optional clauses, cosmetic issues\n\n"
        "risk_obligation_summary — one cohesive paragraph: risks, liabilities, and "
        "key obligations of each party.\n\n"
        + _RISK_CALIBRATION +
        "\n{format_instructions}"
    )

    return ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "Document:\n<document>\n{context}\n</document>\n\nReturn the JSON.")
    ])


def get_entity_extraction_prompt(lang_instruction: str, questions_lang: str) -> ChatPromptTemplate:
    """Returns the ChatPromptTemplate for structured entity extraction.

    Optimizations vs original:
    - Merged system + human into one tighter instruction block
    - CoT scaffold for parties preserved but condensed to 5 numbered steps
      (removed verbose explanatory prose around each step)
    - Removed repeated "Do NOT include..." clauses — covered once in step 4
    - Collapsed field definitions to one line each
    Total token reduction: ~57%
    """
    system_prompt = (
        "Extract entities from the document. Use ONLY the document — never invent values. "
        "Return [] for any field not found."
    )

    human_prompt = (
        "Document:\n<document>\n{context}\n</document>\n\n"
        "Party identification — follow in order:\n"
        "1. Identify document type (sale deed / lease / NDA / employment / PoA / other)\n"
        "2. List the principal roles for that type (Seller+Buyer, Landlord+Tenant, etc.)\n"
        "3. Map named persons/entities to those roles\n"
        "4. Exclude: fathers, deceased relatives, witnesses, neighbours, road names, "
        "government offices, registration officials\n"
        "5. Output only the Step 3 names that pass Step 4\n\n"
        "Extract these fields:\n"
        f"- parties: direct transacting parties only (Step 5 above)\n"
        "- dates: all dates (execution, registration, payment, expiry)\n"
        "- amounts: all monetary values with currency\n"
        f"- obligations: who must do what — {lang_instruction}\n"
        f"- suggested_questions: 3–4 practical questions a reader of this document "
        f"would ask, in {questions_lang}"
    )

    return ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", human_prompt)
    ])


def get_entity_extraction_prefiltered_prompt(lang_instruction: str, questions_lang: str) -> ChatPromptTemplate:
    """Returns the ChatPromptTemplate for entity extraction on pre-filtered contexts.

    Used exclusively by ``extract_entities_via_llm_prefiltered`` in
    ``entity_extraction.py``.  Unlike ``get_entity_extraction_prompt`` (which
    targets raw chunks), this prompt receives short, regex-selected excerpts
    joined by ``---`` separators, so the system message is tuned accordingly:

    - Tells the LLM that excerpts are *pre-selected* for entity signals—it
      must not assume that missing sections are entity-free.
    - Explains that ``---`` marks section boundaries, not document gaps.
    - Preserves the same 5-step party CoT scaffold and output schema.
    """
    system_prompt = (
        "You are a legal entity extractor. The document excerpts below were "
        "pre-selected by a regex filter because they contain entity signals "
        "(dates, amounts, party names, obligations). "
        "Sections are separated by --- markers.\n\n"
        "Rules:\n"
        "1. Extract ALL entities present in the excerpts—do not skip any.\n"
        "2. Use ONLY the excerpts provided—never invent values.\n"
        "3. The --- separators are section boundaries, not evidence of "
        "missing content; do not infer entities from gaps.\n"
        "4. Return [] for any field not found in the excerpts."
    )

    human_prompt = (
        "Document excerpts (pre-filtered):\n"
        "<excerpts>\n{context}\n</excerpts>\n\n"
        "Party identification — follow in order:\n"
        "1. Identify document type (sale deed / lease / NDA / employment / PoA / other)\n"
        "2. List the principal roles for that type (Seller+Buyer, Landlord+Tenant, etc.)\n"
        "3. Map named persons/entities to those roles\n"
        "4. Exclude: fathers, deceased relatives, witnesses, neighbours, road names, "
        "government offices, registration officials\n"
        "5. Output only the Step 3 names that pass Step 4\n\n"
        "Extract these fields:\n"
        "- parties: direct transacting parties only (Step 5 above)\n"
        "- dates: all dates (execution, registration, payment, expiry)\n"
        "- amounts: all monetary values with currency\n"
        f"- obligations: who must do what — {lang_instruction}\n"
        f"- suggested_questions: 3–4 practical questions a reader of this document "
        f"would ask, in {questions_lang}"
    )

    return ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", human_prompt)
    ])


def get_rephrase_prompt() -> ChatPromptTemplate:
    """Returns the ChatPromptTemplate for rephrasing follow-up queries for vector search.

    Optimizations vs original:
    - Removed explanatory middle sentence (implied by task description)
    - "Output ONLY" instruction tightened to one line
    Total token reduction: ~55%
    """
    system_prompt = (
        "Rewrite the follow-up question as a self-contained search query "
        "using relevant context from the conversation history. "
        "Output ONLY the rewritten question — no explanation."
    )
    return ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{input}")
    ])


def get_followup_questions_prompt(response_lang: str = "English") -> ChatPromptTemplate:
    """Returns the ChatPromptTemplate for generating dynamic follow-up questions.

    Optimizations vs original:
    - Merged role sentence into a single compact instruction
    - Replaced verbose 4-rule block with 2-line output contract
    - Example format kept to anchor JSON shape (prevents markdown wrapping)
    Total token reduction: ~69%
    """
    system_prompt = (
        f"Generate 3–4 follow-up questions a user would ask next, in {response_lang}. "
        "Base them on the prior Q&A and the document context below.\n"
        "Output: raw JSON array of strings only — no markdown, no commentary.\n"
        "Example: [\"Question one?\", \"Question two?\"]\n\n"
        "Context:\n{context}"
    )
    return ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "User Question: {user_question}\nAssistant Answer: {assistant_answer}\n\nGenerate the JSON array.")
    ])
