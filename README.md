# 🧠 DocuMind — Agentic Document Intelligence Platform

<div align="center">

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-Multi--Agent-FF6B35?style=for-the-badge)
![Next.js](https://img.shields.io/badge/Next.js-Frontend-000000?style=for-the-badge&logo=nextdotjs&logoColor=white)
![ChromaDB](https://img.shields.io/badge/ChromaDB-Vector%20Store-6366f1?style=for-the-badge)

**An Agentic Document Intelligence Platform for Hindi · English · Hinglish documents.**  
Upload legal or government documents → get extraction, risk analysis, draft reply, and conversational Q&A — powered by a LangGraph multi-agent pipeline.

[Features](#-features) • [Architecture](#-architecture) • [Tech Stack](#-tech-stack) • [Setup](#-setup) • [API Reference](#-api-reference) • [Database Schema](#-database-schema)

</div>

---

## 📌 Problem Statement

Millions of Indians receive legal notices, government circulars, rent agreements, and bank documents they struggle to understand — especially when written in formal Hindi or mixed Hindi-English. DocuMind solves this by:

- **Extracting** key dates, amounts, parties, and obligations automatically
- **Flagging** risky or confusing clauses in plain language
- **Drafting** a reply letter the user can send
- **Answering** follow-up questions about the document in natural language

---

## ✨ Features (Phase 1)

| Feature | Status |
|---------|--------|
| PDF Upload & Text Extraction (PyMuPDF) | ✅ |
| Language Detection — Hindi / English / Hinglish | ✅ |
| Text Chunking + ChromaDB Vector Store | ✅ |
| RAG-based Q&A via `/chat` endpoint | ✅ |
| Entity Extraction — dates, amounts, parties (regex + LLM) | ✅ |
| Risk Flag Generation + Draft Reply Letter | ✅ |
| LangGraph Pipeline wiring all agents | ✅ |
| Next.js Frontend — Upload → Analyze → Chat flow | ✅ |

---

## 🏗️ Architecture

### LangGraph Agent Pipeline

The analysis pipeline is a **LangGraph StateGraph** where each node is a standalone agent. RAG/chat runs separately as an on-demand endpoint.

```
PDF Upload (/upload)
     │
     ▼
┌──────────────────────────────┐
│  Node 1: Ingestion Agent     │  Extract raw text via PyMuPDF
│                              │  Save to documents table
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│  Node 2: Language Agent      │  Detect Hindi / English / Hinglish
│                              │  (Devanagari Unicode + langdetect)
└──────────────┬───────────────┘
               │
       ┌───────┴────────┐
       │  Conditional   │  Route: Hindi prompt vs English prompt
       └───────┬────────┘
               │
               ▼
┌──────────────────────────────┐
│  Node 3: Extraction Agent    │  Regex pass + Groq LLM pass
│                              │  → dates, amounts, parties, obligations
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│  Node 4: Risk + Draft Agent  │  One Groq call → risk_flags[] + draft_text
│                              │  Language-aware output
└──────────────┬───────────────┘
               │
               ▼
        Final State saved
        to analysis_results
```

**RAG Chat** (separate, interactive endpoint):
```
/chat  →  Embed question  →  ChromaDB similarity search (by document_id)
       →  Retrieve top-k chunks  →  Groq LLM answer  →  Store in chat_messages
```

### Shared State (LangGraph TypedDict)

```python
class DocumentState(TypedDict):
    raw_text: str
    language: str          # "hindi" | "english" | "hinglish"
    extracted_entities: dict   # dates, amounts, parties, obligations
    risk_flags: list[dict]     # [{clause, reason}]
    draft_text: str
```

---

## 🛠️ Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Backend** | Python 3.10+, FastAPI, Uvicorn | REST API server |
| **PDF Parsing** | PyMuPDF (`fitz`) | Text extraction from PDFs |
| **Language Detection** | Unicode range check + `langdetect` | Hindi/English/Hinglish routing |
| **Text Chunking** | LangChain `RecursiveCharacterTextSplitter` | Chunk size 500–800 chars, overlap 100 |
| **Embeddings** | `sentence-transformers/all-MiniLM-L6-v2` | Local, free, no API cost |
| **Vector Store** | ChromaDB (`PersistentClient`) | Semantic search by document |
| **LLM** | Groq `llama-3.3-70b-versatile` via `langchain-groq` | Extraction, risk, draft, Q&A |
| **Agent Orchestration** | LangGraph `StateGraph` | Node/edge pipeline with conditional routing |
| **Database** | PostgreSQL + SQLAlchemy | Documents, analysis, chat history |
| **Frontend** | Next.js 14 + Tailwind CSS | Upload → Analyze → Chat UI |

---

## 📁 Project Structure

```
documind/
├── backend/
│   ├── main.py                      # FastAPI app, router registration
│   ├── api/
│   │   └── routes/
│   │       ├── upload.py            # POST /upload — PDF ingest
│   │       ├── analyze.py           # POST /analyze — full LangGraph pipeline
│   │       └── chat.py              # POST /chat — RAG Q&A
│   ├── agents/
│   │   ├── pipeline.py              # LangGraph StateGraph definition
│   │   ├── ingestion_agent.py       # Node 1: PyMuPDF text extraction
│   │   ├── language_agent.py        # Node 2: Detect Hindi/English/Hinglish
│   │   ├── extraction_agent.py      # Node 3: Regex + LLM entity extraction
│   │   └── risk_draft_agent.py      # Node 4: Risk flags + draft reply
│   ├── rag/
│   │   ├── chunker.py               # RecursiveCharacterTextSplitter setup
│   │   ├── embedder.py              # all-MiniLM-L6-v2 embedding
│   │   ├── vector_store.py          # ChromaDB client + upsert/query
│   │   └── qa.py                    # answer_question() — RAG core function
│   ├── db/
│   │   ├── database.py              # SQLAlchemy engine + session
│   │   └── models.py                # ORM models: Document, AnalysisResult, ChatMessage
│   ├── core/
│   │   ├── config.py                # .env settings via Pydantic
│   │   └── llm_client.py            # Groq client wrapper
│   └── requirements.txt
├── frontend/
│   ├── app/
│   │   ├── page.tsx                 # Upload page (drag-and-drop)
│   │   ├── analyze/[id]/page.tsx    # Analysis results display
│   │   └── chat/[id]/page.tsx       # Chat interface
│   ├── components/
│   │   ├── UploadZone.tsx
│   │   ├── EntityCard.tsx
│   │   ├── RiskFlagsPanel.tsx
│   │   ├── DraftReplyBox.tsx
│   │   └── ChatWindow.tsx
│   └── package.json
├── sample_docs/                     # Test documents (rent agreement, circular, bank notice)
├── .env.example
├── .gitignore
└── README.md
```

---

## 🗄️ Database Schema

Three intentionally simple tables — no over-engineering for a 3-week project:

```sql
-- Uploaded documents
CREATE TABLE documents (
    id          SERIAL PRIMARY KEY,
    filename    TEXT NOT NULL,
    upload_date TIMESTAMP DEFAULT NOW(),
    language    TEXT,                  -- detected: hindi / english / hinglish
    raw_text    TEXT,
    status      TEXT DEFAULT 'pending' -- pending / processed / failed
);

-- Analysis output per document
CREATE TABLE analysis_results (
    id                  SERIAL PRIMARY KEY,
    document_id         INTEGER REFERENCES documents(id),
    extracted_entities  JSONB,  -- { dates:[], amounts:[], parties:[], obligations:[] }
    risk_flags          JSONB,  -- [{ clause: "...", reason: "..." }]
    draft_text          TEXT
);

-- Chat history per document
CREATE TABLE chat_messages (
    id          SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id),
    role        TEXT,   -- 'user' | 'assistant'
    content     TEXT,
    created_at  TIMESTAMP DEFAULT NOW()
);
```

> **Design note:** `extracted_entities` and `risk_flags` are stored as single JSON columns rather than normalized tables. This keeps queries simple and is appropriate for a project of this scope.

---

## ⚙️ Setup & Installation

### Prerequisites

- Python 3.10+
- Node.js 18+
- PostgreSQL running locally (or a free cloud DB)
- Groq API Key — free at [console.groq.com](https://console.groq.com)

### 1. Clone the Repository

```bash
git clone https://github.com/your-username/documind.git
cd documind
```

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate        # Linux/Mac
# venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp ../.env.example .env
# Fill in your values (see below)
```

### 3. Environment Variables

```env
# LLM
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/documind

# ChromaDB
CHROMA_PERSIST_DIR=./chroma_db

# Embeddings (runs locally, no API key needed)
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

# Chunking
CHUNK_SIZE=700
CHUNK_OVERLAP=100
RAG_TOP_K=4

# File Upload
UPLOAD_DIR=./uploaded_docs
MAX_FILE_SIZE_MB=10
```

### 4. Initialize Database & Run Backend

```bash
# Create tables
python -c "from db.database import engine; from db.models import Base; Base.metadata.create_all(engine)"

# Start server
uvicorn main:app --reload --port 8000
```

- API: `http://localhost:8000`
- Swagger Docs: `http://localhost:8000/docs`

### 5. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Frontend: `http://localhost:3000`

---

## 🔌 API Reference

### `POST /upload`
Upload a PDF. Extracts text, detects language, stores chunks in ChromaDB.

```bash
curl -X POST http://localhost:8000/upload \
  -F "file=@rent_agreement.pdf"
```

```json
{
  "document_id": 1,
  "filename": "rent_agreement.pdf",
  "language": "hindi",
  "status": "processed"
}
```

---

### `POST /analyze`
Run the full LangGraph pipeline on an uploaded document. Returns extraction + risk flags + draft reply.

```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"document_id": 1}'
```

```json
{
  "document_id": 1,
  "extracted_entities": {
    "dates": ["15/08/2025", "01/09/2025"],
    "amounts": ["₹12,000", "₹50,000"],
    "parties": ["राम कुमार", "श्याम लाल"],
    "obligations": ["किरायेदार हर महीने की 5 तारीख को भुगतान करेगा"]
  },
  "risk_flags": [
    {
      "clause": "मकान मालिक बिना नोटिस के किसी भी समय समझौता रद्द कर सकता है",
      "reason": "यह क्लॉज़ किरायेदार के लिए अनुचित है — बिना नोटिस के निकाले जाने का जोखिम है"
    }
  ],
  "draft_text": "सेवा में,\nश्री राम कुमार जी,\n\nआपके द्वारा भेजे गए किराया समझौते के संदर्भ में..."
}
```

---

### `POST /chat`
Ask a question about an uploaded document (RAG-based).

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"document_id": 1, "question": "इस दस्तावेज़ में किराया कितना है?"}'
```

```json
{
  "answer": "दस्तावेज़ के अनुसार मासिक किराया ₹12,000 है, जो हर महीने की 5 तारीख तक देना होगा।",
  "sources_used": 3
}
```

---

## 🌐 Language Detection Logic

```python
def detect_language(text: str) -> str:
    # Check for Devanagari Unicode range U+0900–U+097F
    devanagari_chars = [c for c in text if '\u0900' <= c <= '\u097F']
    ratio = len(devanagari_chars) / len(text)

    if ratio > 0.3:
        return "hindi"          # Mostly Devanagari → Hindi
    elif ratio > 0.05:
        return "hinglish"       # Some Devanagari mixed in → Hinglish
    else:
        return "english"        # Fallback via langdetect
```

Used to route LLM prompts — Hindi documents get Hindi-language prompts, English documents get English prompts.

---

## 🧪 Test Documents

For reliable demos, use documents where text extraction works cleanly:

| Document Type | Language | Why It Works Well |
|---------------|----------|-------------------|
| Rent Agreement | Hindi | Clear parties, amounts, dates |
| Government Circular | Hindi/English | Risk flags easy to identify |
| Bank Notice | English | Structured, entity-rich |

> **Tip:** Avoid heavily scanned or low-quality image PDFs. If needed, paste clean text into a PDF manually for demo reliability.

---

## 🎯 Demo Flow (for Presentation)

1. **Upload** a Hindi rent agreement PDF
2. Hit **Analyze** → show extracted entities (dates, amounts, parties)
3. Show **Risk Flags** — "this clause is unfair because..."
4. Show **Draft Reply** generated in Hindi
5. Switch to **Chat** → ask "किराया कितना है?" → get grounded answer

---

## 🗺️ Roadmap

| Phase | Scope | Status |
|-------|-------|--------|
| **Phase 1** — Core Platform | Upload, Extract, Risk, RAG Chat, LangGraph, Next.js UI | ✅ Complete |
| **Phase 2** — Resume Showcase | Auth, Cross-doc search, 8+ Indic languages, Docker, Cloud deploy | 🔄 Planned |

---

## 👨‍💻 Author

**Rahul Patidar**  
MCA Student · DAVV Indore · Full Stack + AI/GenAI Developer

[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-0077B5?style=flat&logo=linkedin)](https://linkedin.com/in/your-profile)
[![GitHub](https://img.shields.io/badge/GitHub-Follow-181717?style=flat&logo=github)](https://github.com/your-username)

---

## 📄 License

© 2026 Rahul Patidar. All rights reserved.

---

<div align="center">
Made with ❤️ in Indore, India 🇮🇳
</div>