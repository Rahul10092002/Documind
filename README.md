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

## ✨ Features (Refactored Status)

| Feature | Status | Description |
|:---|:---:|:---|
| PDF Text Extraction | ✅ | Extracts PDF text and normalizes Devanagari Unicode using PyMuPDF |
| 3-Stage Language Detection | ✅ | Detects Hindi (`hi`), Hinglish (`hi-Latn`), or English (`en`) |
| Vector Indexing | ✅ | Recursive chunking and storage in ChromaDB via HuggingFace locally |
| RAG conversational Q&A | ✅ | Context-grounded chat endpoint with standalone query rephrasing |
| Structured Entity Extraction | ✅ | Dual-pass parsing (Regex + LLM structured schema) for dates, amounts, parties |
| Risk Assessment & Drafting | ✅ | LLM assessment of unfair terms and response draft generation |
| Next.js Unified Workspace | ✅ | Unified tabbed dashboard UI (Upload, Extraction, Risks, and Chat panels) |
| LangGraph Orchestration | ✅ | Wired multi-agent sequential & parallel StateGraph DAG pipeline |
| Production Reliability | ✅ | Tenacity retries, slowapi rate limiting, structlog request middleware, and Alembic migrations |
| Docker Containerization | ✅ | Fully packaged stack with Docker Compose and local PostgreSQL support |

---

## 🏗️ Architecture

### LangGraph Multi-Agent Pipeline Flow

The backend utilizes **LangGraph** to coordinate ingestion, language detection, entities extraction, and risk flagging:

```
           START
             │
             ▼
      ┌─────────────┐
      │   ingest    │  (Ingestion Agent: Extract text / OCR)
      └──────┬──────┘
             │
             ├─── [If Ingestion Fails] ───► END
             ▼
      ┌─────────────┐
      │   detect    │  (Language Detect Agent: Hindi, English, Hinglish heuristics)
      └──────┬──────┘
             │
      ┌──────┴──────┐  [Parallel Execution Branch]
      ▼             ▼
┌───────────┐ ┌───────────┐
│  extract  │ │ risk_flag │  (NER/LLM Metadata Extraction & Risk Profiling)
└─────┬─────┘ └─────┬─────┘
      │             │
      └──────┬──────┘
             ▼
            END
```

**Conversational RAG Chat Flow** (interactive, on-demand):
```
/documents/{id}/chat ──► Standalone Rephrase ──► ChromaDB Similarity Search ──► Groq/Gemini QA Prompt
```

---

## 🛠️ Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Backend** | Python 3.11+, FastAPI, Uvicorn | REST API backend server |
| **Agentic Framework** | LangGraph | Multi-agent DAG state management |
| **PDF Parsing** | PyMuPDF (`fitz`) | Text extraction & Unicode Devanagari visual-order correction |
| **Language Detection** | Custom heuristics + `langdetect` | Unicode checks and Hinglish loanword heuristics |
| **Text Chunking** | LangChain `RecursiveCharacterTextSplitter` | Preserves page numbers for downstream citation |
| **Embeddings** | `sentence-transformers/all-MiniLM-L6-v2` | Runs locally, no API cost, 384-dimension vector output |
| **Vector Store** | ChromaDB (`PersistentClient`) | Local vector storage with L2-distance scored filtering |
| **LLMs** | Groq (`llama-3.3-70b-versatile`) | Primary entity, risk, and Q&A engine with deterministic temperature |
| **LLM Fallback** | Gemini (`gemini-2.5-flash`) | Automatic client failover when Groq rate limits are hit |
| **LLM Retries** | Tenacity | Resilient exponential retry loops for API stability |
| **Database** | PostgreSQL / SQLite + SQLAlchemy | Persistent metadata, analysis data, and chat timeline history |
| **Database Migrations** | Alembic | Versioned database schema updates |
| **Structured Logging** | Structlog | Clean HTTP JSON request profiling |
| **Rate Limiter** | SlowAPI | Protects endpoints against API quota exhaustion |
| **Frontend** | Next.js 15 + TypeScript + Tailwind CSS | Responsive, unified drag-and-drop workspace UI |

---

## 📁 Project Structure

```
documind/
├── backend/
│   ├── app/
│   │   ├── main.py                   # FastAPI app, Lifespan, exceptions & rate-limiting configs
│   │   ├── config.py                 # Pydantic Settings (env config, LLM parameters)
│   │   ├── database.py               # SQLAlchemy engine & session factory
│   │   ├── exceptions.py             # Custom hierarchy under DocuMindBaseError
│   │   ├── dependencies.py           # Dependency Injection provider (get_db_session, get_llm_client, get_vector_client)
│   │   ├── models.py                 # ORM Models (Document, AnalysisResult, ChatMessage)
│   │   ├── schemas.py                # Pydantic schemas
│   │   ├── agents/
│   │   │   ├── graph.py              # Compiled LangGraph StateGraph DAG
│   │   │   ├── state.py              # DocuMindState TypedDict definition
│   │   │   ├── ingestion_agent.py    # Document text and layout ingestion node
│   │   │   ├── language_detect_agent.py # Language and locale detection node
│   │   │   ├── extraction_agent.py   # Spacy/HF/LLM entities extraction node
│   │   │   └── risk_flagging_agent.py # Boilerplate cleanup and risk review node
│   │   ├── extractors/               # Domain extractors (PDF, Word, OCR, NER, Risk, Reports)
│   │   ├── llm/                      # Resilient LLM clients, retries & prompt version registry
│   │   ├── vectordb/                 # Text chunking, retrievers, and VectorStoreClient abstraction
│   │   ├── middleware/               # Structured logging middleware
│   │   └── routers/
│   │       ├── documents.py          # Upload, List, Get, Delete routes
│   │       ├── extraction.py         # Analyze trigger endpoints
│   │       ├── reports.py            # PDF report exports
│   │       └── health.py             # System /health and /ready routes
│   ├── alembic/                      # Database version-controlled migration files
│   ├── scripts/                      # Utility and checker scripts
│   ├── tests/
│   │   ├── unit/                     # Isolation unit tests
│   │   ├── integration/              # Agentic E2E pipeline integration tests
│   │   └── conftest.py               # Database and client testing fixtures
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── app/
│   │   ├── layout.tsx                # layouts, styles & providers
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
├── docker-compose.yml                # Multi-container orchestration stack
└── README.md
```

---

## 🗄️ Database Schema

Three relational database tables configured with cascading deletes at both the SQLAlchemy ORM and database constraints layer:

```sql
-- Uploaded documents metadata
CREATE TABLE documents (
    id              VARCHAR(36) PRIMARY KEY, -- UUID v4
    filename        VARCHAR(255) NOT NULL,
    file_path       VARCHAR(512),
    upload_date     TIMESTAMP WITH TIME ZONE NOT NULL,
    language        VARCHAR(10),             -- "hi", "hi-Latn", "en", etc.
    raw_text        TEXT,
    status          VARCHAR(20) NOT NULL     -- 'pending' / 'processing' / 'completed' / 'failed'
    detailed_status VARCHAR(255)
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
- Python 3.11+
- Node.js 20+
- Docker & Docker Compose (optional for postgres setup)
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
DATABASE_URL=postgresql://admin:postgres_password@localhost:5432/documind

# Chroma Vector Store
CHROMA_PATH=chroma_db
CHROMA_COLLECTION_NAME=documents
EMBEDDING_MODEL_NAME=all-MiniLM-L6-v2
```

### 3. Run using Docker Compose (Recommended)
You can run the entire platform, including database, vector store, and API server, with one command:
```bash
docker-compose up --build
```

### 4. Manual Backend Execution
```bash
cd backend
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Apply migrations
alembic upgrade head

uvicorn app.main:app --reload --port 8000
```
* Backend Swagger Docs will be available at: `http://localhost:8000/docs`

### 5. Frontend Execution
```bash
cd ../frontend
npm install
npm run dev
```
* Open your browser to: `http://localhost:3000`

---

## 🔌 API Reference

### `POST /documents/upload`
Uploads a document and returns the created document metadata. Analysis is scheduled asynchronously in the background.
* **Request:** Form-Data containing a `file` field (.pdf).
* **Response Status:** `201 Created`
* **Response Body:** `DocumentOut` schema.

---

### `PUT /documents/{document_id}/analysis`
Executes or updates the analysis pipeline on the document's stored text (uses rate limiter).
* **Request:** URL Path containing `document_id`.
* **Response Status:** `200 OK`
* **Response Body:** `AnalysisResultOut` (entities, risk flags, draft letter).

---

### `POST /documents/{document_id}/chat`
Query the document context using conversational RAG.
* **Request:** Body matching `{"question": "..."}`
* **Response Status:** `200 OK`

---

## 🌐 Language Detection Logic

The language detection logic in `language_detection.py` processes the **first 2,000 characters** in 3 stages:
1. **Devanagari character ratio check**: If $\ge$ 10% of characters lie in the `U+0900-U+097F` range, returns `"hi"` (Hindi).
2. **Romanized Hinglish token check**: Compares tokenized words against a high-frequency Hinglish dictionary. If the hit ratio is $\ge$ 8%, returns `"hi-Latn"` (Hinglish).
3. **langdetect fallback**: Uses `langdetect` library as a fallback to identify English (`en`) or other generic ISO languages.

---

## ⚠️ Limitations & Notes
- **30,000 Character LLM Limit:** Due to prompt constraints, both entity extraction and risk/draft pipelines truncate the document text to the **first 30,000 characters**.
- **MIME Verification:** File uploads verify PDF MIME types and magic bytes (`%PDF`) first to block executable bypasses.

---

## 📄 License
© 2026 Rahul Patidar. All rights reserved.