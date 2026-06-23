import os
import sys
import json
import re
from typing import Dict, Any

# Ensure standard output uses UTF-8 to prevent console encoding issues on Windows
sys.stdout.reconfigure(encoding='utf-8')

# Ensure the backend directory is in python path and change directory
backend_path = os.path.dirname(os.path.abspath(__file__))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)
os.chdir(backend_path)

from app.database import SessionLocal
from app.models import Document
from app.utils.pdf_extraction import normalize_devanagari_text
from app.utils.rag import get_llm
from app.utils.entity_extraction import ExtractedEntities

from app.database import SessionLocal
from app.models import Document
from app.utils.pdf_extraction import normalize_devanagari_text
from app.utils.rag import get_llm
from langchain_core.prompts import ChatPromptTemplate

def test_hindi_document_extraction():
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == 2).first()
        if not doc:
            print("ERROR: Document with ID 2 was not found in the database.")
            return

        print(f"Document ID: {doc.id}")
        print(f"Filename: {doc.filename}")
        print("-" * 50)

        raw_text = doc.raw_text or ""
        normalized_text = normalize_devanagari_text(raw_text)
        print("--- NORMALIZED TEXT PREVIEW ---")
        print(normalized_text[:300])
        print("-" * 50)

        print("Invoking ChatGroq with sequential QA prompts...")
        llm = get_llm()

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

        truncated_text = normalized_text[:30000]
        extracted = {
            "dates": [],
            "amounts": [],
            "parties": [],
            "obligations": []
        }

        # 1. Extract Parties
        print("Extracting parties...")
        q_parties = (
            "Identify the full names of all individuals or organizations involved as parties in this document "
            "(e.g., seller/विक्रेता, buyer/क्रेता, witnesses/गवाह, scribe/लेखक). "
            "Return ONLY their names as a comma-separated list in Devanagari script. Do not write any intro or explanation."
        )
        msg_parties = qa_prompt.invoke({"context": truncated_text, "question": q_parties})
        resp_parties = llm.invoke(msg_parties)
        names = [n.strip() for n in resp_parties.content.split(",") if n.strip()]
        extracted["parties"] = [n for n in names if len(n) < 100 and "context" not in n.lower()]

        # 2. Extract Dates
        print("Extracting dates...")
        q_dates = (
            "Identify all the dates mentioned in this document (e.g., execution date, registration date, payment dates). "
            "Return ONLY these dates as a comma-separated list. Do not write any intro or explanation."
        )
        msg_dates = qa_prompt.invoke({"context": truncated_text, "question": q_dates})
        resp_dates = llm.invoke(msg_dates)
        dates = [d.strip() for d in resp_dates.content.split(",") if d.strip()]
        extracted["dates"] = [d for d in dates if len(d) < 50 and "context" not in d.lower()]

        # 3. Extract Amounts
        print("Extracting amounts...")
        q_amounts = (
            "Identify all the monetary or currency amounts mentioned in this document (e.g., sale price, advance, balance). "
            "Return ONLY these amounts as a comma-separated list. Do not write any intro or explanation."
        )
        msg_amounts = qa_prompt.invoke({"context": truncated_text, "question": q_amounts})
        resp_amounts = llm.invoke(msg_amounts)
        amounts = [a.strip() for a in resp_amounts.content.split(",") if a.strip()]
        extracted["amounts"] = [a for a in amounts if len(a) < 50 and "context" not in a.lower()]

        # 4. Extract Obligations
        print("Extracting obligations...")
        q_obligations = (
            "List the key obligations, duties, or conditions imposed on the parties in this document (who must do what). "
            "Return them as a clean bulleted list (one obligation per line) in Devanagari/Hindi script. Do not write any intro or explanation."
        )
        msg_obligations = qa_prompt.invoke({"context": truncated_text, "question": q_obligations})
        resp_obligations = llm.invoke(msg_obligations)
        lines = [line.strip("-*• ").strip() for line in resp_obligations.content.splitlines() if line.strip()]
        extracted["obligations"] = [line for line in lines if len(line) > 5 and "context" not in line.lower()]

        # Print results
        print("\n--- EXTRACTED ENTITIES ---")
        print(json.dumps(extracted, indent=2, ensure_ascii=False))

    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    test_hindi_document_extraction()
