# 🧠 DocuMind — Agentic Document Intelligence Platform

<div align="center">

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-Frontend-000000?style=for-the-badge&logo=nextdotjs&logoColor=white)
![ChromaDB](https://img.shields.io/badge/ChromaDB-Vector%20Store-6366f1?style=for-the-badge)

**An Agentic Document Intelligence Platform for Hindi · English · Hinglish documents.**  
Upload legal or government documents → get entity extraction, risk analysis, draft reply, and conversational Q&A — powered by a multi-agent backend pipeline.

[Features](#-features) • [Architecture](#-architecture) • [Tech Stack](#-tech-stack) • [Setup](#-setup) • [API Reference](#-api-reference) • [Database Schema](#-database-schema)

</div>

---

## 📌 Problem Statement

Millions of Indians receive legal notices, government circulars, rent agreements, and bank documents they struggle to understand — especially when written in formal Hindi or mixed Hindi-English (Hinglish). DocuMind solves this by:

- **Extracting** key dates, amounts, parties, and obligations automatically.
- **Flagging** risky or one-sided clauses in plain language.
- **Drafting** a response letter in the document's native language.
- **Answering** follow-up questions about the document in natural language (RAG).

---

## ✨ Features (Phase 1 Status)

| Feature | Status | Description |
|:---|:---:|:---|
| PDF Text Extraction | ✅ | Extracts PDF text and normalizes Devanagari Unicode using PyMuPDF |
| 3-Stage Language Detection | ✅ | Detects Hindi (`hi`), Hinglish (`hi-Latn`), or English (`en`) |
| Vector Indexing | ✅ | Recursive chunking and storage in ChromaDB via HuggingFace locally |
| RAG conversational Q&A | ✅ | Context-grounded chat endpoint with standalone query rephrasing |
| Structured Entity Extraction | ✅ | Dual-pass parsing (Regex + LLM structured schema) for dates, amounts, parties |
| Risk Assessment & Drafting | ✅ | LLM assessment of unfair terms and response draft generation |
| Next.js Unified Workspace | ✅ | Unified tabbed dashboard UI (Upload, Extraction, Risks, and Chat panels) |
| LangGraph Orchestration | 🔄 | Currently sequential Python services. **StateGraph wiring is planned for Phase 2.** |

---

## 🏗️ Architecture

### Document Processing and Analysis Pipeline

The analysis pipeline processes documents end-to-end at the time of upload, indexing text chunks and running parallel analysis:

```
PDF Upload (/documents/upload)
     │
     ▼
┌──────────────────────────────┐
│     1. PyMuPDF Ingestion     │  Extract raw text & normalize Devanagari Unicode
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│    2. Language Detection     │  Scan Devanagari range -> Hinglish word list check -> langdetect
└──────────────┬───────────────┘
               │
               ├─────────────────────────┐
               ▼ (Chroma Vector Store)   ▼ (Metadata Extraction)
┌──────────────────────────────┐ ┌──────────────────────────────────────────────────┐
│      3. Text Chunking        │ │       4. Dual-Pass Entity Extraction             │
│ RecursiveCharacterSplitter   │ │ Regex Date & Currency Check + LLM Pydantic Schema│
└──────────────┬───────────────┘ └────────────────────────┬─────────────────────────┘
               │                                          │
               ▼                                          ▼
┌──────────────────────────────┐ ┌──────────────────────────────────────────────────┐
│   5. Embeddings Indexing     │ │       6. Risk Assessment & Draft Reply           │
│ Local all-MiniLM-L6-v2       │ │ Groq LLM (llama-3.3-70b) / Gemini 2.5 Fallback   │
└──────────────────────────────┘ └────────────────────────┬─────────────────────────┘
                                                          │
                                                          ▼
                                            💾 Saved to analysis_results
```

**Conversational RAG Chat Flow** (interactive, on-demand):
```
/documents/{id}/chat ──► Standalone Rephrase ──► ChromaDB Similarity Search ──► Groq/Gemini QA Prompt
```

---

## 🛠️ Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Backend** | Python 3.10+, FastAPI, Uvicorn | REST API backend server |
| **PDF Parsing** | PyMuPDF (`fitz`) | Text extraction & Unicode Devanagari visual-order correction |
| **Language Detection** | Custom heuristics + `langdetect` | Unicode checks and Hinglish loanword heuristics |
| **Text Chunking** | LangChain `RecursiveCharacterTextSplitter` | Preserves page numbers for downstream citation |
| **Embeddings** | `sentence-transformers/all-MiniLM-L6-v2` | Runs locally, no API cost, 384-dimension vector output |
| **Vector Store** | ChromaDB (`PersistentClient`) | Local vector storage with L2-distance scored filtering |
| **LLMs** | Groq (`llama-3.3-70b-versatile`) | Primary entity, risk, and Q&A engine with deterministic temperature |
| **LLM Fallback** | Gemini (`gemini-2.5-flash`) | Automatic client failover when Groq rate limits are hit |
| **Database** | PostgreSQL / SQLite + SQLAlchemy | Persistent metadata, analysis data, and chat timeline history |
| **Frontend** | Next.js 16 + TypeScript + Tailwind CSS | Responsive, unified drag-and-drop workspace UI |

---

## 📁 Project Structure

```
documind/
├── backend/
│   ├── app/
│   │   ├── main.py                   # FastAPI initialization & lifespan management
│   │   ├── config.py                 # Pydantic Settings (env config, LLM parameters)
│   │   ├── database.py               # SQLAlchemy engine & session factory
│   │   ├── models.py                 # ORM Models (Document, AnalysisResult, ChatMessage)
│   │   ├── schemas.py                # Pydantic schema contracts for endpoints
│   │   ├── routers/
│   │   │   └── documents.py          # Unified /documents API routes (9 routes)
│   │   └── utils/
│   │       ├── answer_service.py     # RAG, SQL chat history & risk/draft generator
│   │       ├── entity_extraction.py  # Regex + LLM dual-pass metadata extraction
│   │       ├── language_detection.py # Devanagari range, Hinglish scan, and langdetect
│   │       ├── llm_client.py         # Resilient LLM wrapper with retry & Gemini fallback
│   │       ├── pdf_extraction.py     # Text extraction & Devanagari normalization
│   │       ├── prompt_templates.py   # Centralized LangChain prompts (QA, Risk, Rephrase)
│   │       ├── text_chunking.py      # RecursiveCharacterTextSplitter wrappers
│   │       ├── vector_retriever.py   # Scored similarity search with L2 filtering
│   │       └── vector_store.py       # ChromaDB persistent client wrapper
│   └── requirements.txt
├── frontend/
│   ├── app/
│   │   ├── layout.tsx                # Root layouts, global styles & providers
│   │   ├── page.tsx                  # Landing workspace & uploader
│   │   ├── documents/[id]/page.tsx   # Unified tabbed workspace page
│   │   ├── analyze/[id]/page.tsx     # Direct route alias to Risk/Draft tab
│   │   └── chat/[id]/page.tsx        # Direct route alias to Chat tab
│   ├── components/
│   │   ├── UploadZone.tsx            # Drag-and-drop file uploader
│   │   ├── Sidebar.tsx               # Left-side navigation of uploaded files
│   │   ├── ExtractionView.tsx        # Key metadata & entities visualizer
│   │   ├── RiskAnalysisView.tsx      # Risk warnings & response draft editor
│   │   └── ChatView.tsx              # RAG chat interface
│   └── package.json
└── README.md
```

---

## 🗄️ Database Schema

Three relational database tables configured with cascading deletes at both the SQLAlchemy ORM and database constraints layer:

```sql
-- Uploaded documents metadata
CREATE TABLE documents (
    id          VARCHAR(36) PRIMARY KEY, -- UUID v4
    filename    VARCHAR(255) NOT NULL,
    file_path   VARCHAR(512),
    upload_date TIMESTAMP WITH TIME ZONE NOT NULL,
    language    VARCHAR(10),             -- "hi", "hi-Latn", "en", etc.
    raw_text    TEXT,
    status      VARCHAR(20) NOT NULL     -- 'pending' / 'processing' / 'completed' / 'failed'
);

-- Stored AI extraction and risk assessment analysis 
CREATE TABLE analysis_results (
    id                      SERIAL PRIMARY KEY,
    document_id             VARCHAR(36) REFERENCES documents(id) ON DELETE CASCADE UNIQUE,
    extracted_entities      JSON,            -- merged regex & LLM entities
    risk_flags              JSON,            -- array of flagged risky clauses
    risk_obligation_summary TEXT             -- draft response letter content
);

-- Document Q&A chat history logs
CREATE TABLE chat_messages (
    id          SERIAL PRIMARY KEY,
    document_id VARCHAR(36) REFERENCES documents(id) ON DELETE CASCADE,
    role        VARCHAR(20) NOT NULL,    -- 'user' or 'assistant'
    content     TEXT NOT NULL,
    created_at  TIMESTAMP WITH TIME ZONE NOT NULL
);
```

---

## ⚙️ Setup & Installation

### Prerequisites
- Python 3.10+
- Node.js 20+
- PostgreSQL running locally (automatically falls back to local SQLite `documind.db` if unavailable)
- Groq API Key (console.groq.com)
- Google AI Studio API Key (optional fallback, aistudio.google.com)

### 1. Clone & Position
```bash
git clone https://github.com/Rahul10092002/documind.git
cd documind
```

### 2. Backend Environment Configuration
Create a `.env` file under `backend/` following this template:
```env
# LLM Providers
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_your_groq_key_here
GOOGLE_API_KEY=AIzaSy_your_gemini_key_here
ENABLE_GEMINI_FALLBACK=true

# Database (Leave blank to fallback automatically to SQLite backend/documind.db)
DATABASE_URL=postgresql://postgres:password@localhost:5432/documind

# Chroma Vector Store
CHROMA_PATH=chroma_db
CHROMA_COLLECTION_NAME=documents
EMBEDDING_MODEL_NAME=all-MiniLM-L6-v2
```

### 3. Backend Execution
```bash
cd backend
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
* Backend Swagger Docs will be available at: `http://localhost:8000/docs`

### 4. Frontend Execution
```bash
cd ../frontend
npm install
npm run dev
```
* Open your browser to: `http://localhost:3000`

---

## 🔌 API Reference

### `POST /documents/upload`
Uploads a document, extracts content, runs language detection, indexes chunks to ChromaDB, extracts entities, assesses risk, and triggers draft generation.
* **Request:** Form-Data containing a `file` field (.pdf).
* **Response Status:** `201 Created`
* **Response Body:** `DocumentOut` schema.

---

### `PUT /documents/{document_id}/analysis`
Idempotently executes or updates the analysis pipeline on the document's stored text (used for repairs or re-runs).
* **Request:** URL Path containing `document_id`.
* **Response Status:** `200 OK`
* **Response Body:** `AnalysisResultOut` (entities, risk flags, draft letter).

---

### `POST /documents/{document_id}/chat`
Query the document context using conversational RAG. Standalone questions are automatically rephrased if chat history is present.
* **Request:** Body matching `{"question": "..."}`
* **Response Status:** `200 OK`
* **Response Body:**
```json
{
  "answer": "The agreement terminates on December 31, 2026.",
  "document_id": "a1b2c3d4-...",
  "chunks_used": 3,
  "confidence": "high",
  "sources": [
    {
      "filename": "lease_agreement.pdf",
      "chunk_index": 2,
      "page_content": "This agreement shall remain in full force...",
      "score": 0.42,
      "page": 3
    }
  ]
}
```

---

## 🌐 Language Detection Logic

The language detection logic in `language_detection.py` processes the **first 2,000 characters** in 3 stages:
1. **Devanagari character ratio check**: If $\ge$ 10% of characters lie in the `U+0900-U+097F` range, returns `"hi"` (Hindi).
2. **Romanized Hinglish token check**: Compares tokenized words against a high-frequency Hinglish dictionary. If the hit ratio is $\ge$ 8%, returns `"hi-Latn"` (Hinglish).
3. **langdetect fallback**: Uses `langdetect` library as a fallback to identify English (`en`) or other generic ISO languages.

---

## ⚠️ Limitations & Notes
* **30,000 Character LLM Limit:** Due to prompt constraints, both entity extraction and risk/draft pipelines truncate the document text to the **first 30,000 characters**. Text beyond this range will not be processed by the LLM (logged at `WARNING` level).
* **MIME Verification Warning:** File uploads verify PDF MIME types, but checking the file extension is not security-sufficient. Uploads check the magic bytes (`%PDF`) first to block executable bypasses.

---

## 🗺️ Project Roadmap

- [x] **Phase 1 (Current)**: Text extraction, ChromaDB RAG, fallback resilient LLMs, dual-pass entity parsing, risk flagging, response draft generation, Next.js dashboard UI.
- [ ] **Phase 2 (Next)**: Orchestrate analysis pipeline using a 6-node LangGraph `StateGraph`, configure Google Gemini API as primary driver, package with Docker Compose, and deploy live on AWS EC2.

---

## 👨‍💻 Author

**Rahul Patidar**  
DAVV Indore · Full Stack GenAI Developer  
* [LinkedIn](https://linkedin.com/in/rahulpatidar21) · [GitHub](https://github.com/Rahul10092002)

---

## 📄 License
© 2026 Rahul Patidar. All rights reserved.