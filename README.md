# 🧠 DocuMind — Agentic Document Intelligence Platform

<div align="center">

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-Multi--Agent-FF6B35?style=for-the-badge)
![Next.js](https://img.shields.io/badge/Next.js-Frontend-000000?style=for-the-badge&logo=nextdotjs&logoColor=white)
![ChromaDB](https://img.shields.io/badge/ChromaDB-Vector%20Store-6366f1?style=for-the-badge)
![Groq](https://img.shields.io/badge/Groq-LLaMA3-F97316?style=for-the-badge)

**An intelligent, multilingual document processing platform powered by a LangGraph agentic pipeline.**  
Supports Hindi · English · Hinglish documents with AI-driven extraction, risk flagging, draft generation, and RAG-based Q&A.

[Features](#-features) • [Architecture](#-architecture) • [DB Schema](#-database-schema) • [API Endpoints](#-api-endpoints) • [Setup](#-setup--installation) • [Demo](#-demo-flow)

</div>

---

## 📌 Overview

DocuMind is a full-stack **Agentic Document Intelligence Platform** built as an MCA Major Project at DAVV Indore. It processes uploaded documents (PDF/DOCX/TXT) through a **LangGraph-orchestrated pipeline** that performs language detection, entity extraction, risk analysis, draft generation, and conversational Q&A — with native support for **Hindi, English, and Hinglish** documents.

> Built to solve a real problem: thousands of Indians receive legal notices, rent agreements, bank letters, and government circulars in complex language they can't easily understand. DocuMind reads it for them.

---

## ✨ Features (Phase 1)

| Feature | Description |
|---|---|
| 📄 **PDF Upload & Text Extraction** | Upload a PDF, extract raw text via PyMuPDF |
| 🌐 **Language Detection** | Devanagari Unicode range check + `langdetect` fallback for Hindi/English/Hinglish |
| 🔪 **Smart Chunking** | `RecursiveCharacterTextSplitter` with 500–800 char chunks, 100 char overlap |
| 🧮 **Vector Embeddings** | `sentence-transformers/all-MiniLM-L6-v2` stored in ChromaDB (local, no API cost) |
| 💬 **RAG-based Q&A** | Semantic retrieval + Groq (llama-3.3-70b-versatile) answer generation |
| 🔍 **Entity Extraction** | Hybrid: Regex (dates, amounts, ₹) + LLM structured JSON extraction |
| ⚠️ **Risk Flagging** | LLM identifies risky clauses with reasoning in Hindi/English |
| 📝 **Draft Reply Generation** | Auto-generates a draft reply letter matching document language |
| 🤖 **LangGraph Pipeline** | State-based graph: Ingestion → Extraction → Risk+Draft with conditional routing |
| 🖥️ **Next.js Frontend** | Upload → Analyze → Chat full flow with loading states and error handling |

---

## 🏗️ Architecture

### LangGraph Pipeline (One-Shot Analysis)

```
PDF Upload (/upload)
     │
     ▼
┌─────────────────────┐
│  Node 1             │  PyMuPDF text extraction
│  Ingestion          │  → documents table (raw_text, language, status)
└──────────┬──────────┘
           │
           ▼
    [Conditional Edge]
    language == "hindi" → Hindi prompt path
    language == "english" → English prompt path
           │
           ▼
┌─────────────────────┐
│  Node 2             │  Regex (dates, ₹, amounts) +
│  Extraction         │  Groq LLM → structured JSON entities
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Node 3             │  Single Groq call →
│  Risk + Draft       │  risk_flags[] + draft_text
└──────────┬──────────┘
           │
           ▼
   Stored in analysis_results
   Returned via /analyze endpoint


RAG Chat (/chat) — Separate, On-Demand
     │
     ▼
  Embed question → ChromaDB similarity search (filtered by document_id)
     │
     ▼
  Top-k chunks (3–5) → Groq prompt with context → Answer
     │
     ▼
  Stored in chat_messages → Returned to UI
```

> **Design decision:** RAG chat runs as a standalone endpoint, not inside the LangGraph graph. The analysis pipeline is one-shot (document in → full analysis out). Chat is interactive and on-demand. Mixing them would overcomplicate the graph for no benefit.

---

## 🗄️ Database Schema

Intentionally simple — one JSON column for entities and risk flags instead of over-normalized tables.

```sql
-- documents
id            SERIAL PRIMARY KEY
filename      TEXT NOT NULL
upload_date   TIMESTAMP DEFAULT NOW()
language      TEXT                        -- 'hindi' | 'english' | 'hinglish'
raw_text      TEXT
status        TEXT DEFAULT 'pending'      -- 'pending' | 'processed' | 'failed'

-- analysis_results
id                  SERIAL PRIMARY KEY
document_id         INT REFERENCES documents(id)
extracted_entities  JSONB     -- { dates: [], amounts: [], parties: [], obligations: [] }
risk_flags          JSONB     -- [ { clause: "...", reason: "..." }, ... ]
draft_text          TEXT

-- chat_messages
id           SERIAL PRIMARY KEY
document_id  INT REFERENCES documents(id)
role         TEXT    -- 'user' | 'assistant'
content      TEXT
created_at   TIMESTAMP DEFAULT NOW()
```

---

## 📁 Project Structure

```
documind/
├── backend/
│   ├── main.py                     # FastAPI app, route registration
│   ├── api/
│   │   └── routes/
│   │       ├── upload.py           # POST /upload
│   │       ├── analyze.py          # POST /analyze
│   │       └── chat.py             # POST /chat
│   ├── agents/
│   │   ├── pipeline.py             # LangGraph StateGraph definition
│   │   ├── ingestion_node.py       # Node 1: PyMuPDF extraction + language detect
│   │   ├── extraction_node.py      # Node 2: Regex + Groq entity extraction
│   │   └── risk_draft_node.py      # Node 3: Risk flags + draft reply
│   ├── rag/
│   │   ├── chunker.py              # RecursiveCharacterTextSplitter setup
│   │   ├── embedder.py             # all-MiniLM-L6-v2 + ChromaDB ingestion
│   │   └── retriever.py            # answer_question(document_id, question)
│   ├── core/
│   │   ├── config.py               # Env vars, model names
│   │   ├── database.py             # SQLAlchemy engine + session
│   │   ├── models.py               # SQLAlchemy ORM models
│   │   └── llm_client.py           # Groq client via langchain-groq
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.jsx            # Upload page
│   │   │   ├── analyze/page.jsx    # Analysis results page
│   │   │   └── chat/page.jsx       # Chat interface page
│   │   └── components/
│   │       ├── UploadZone.jsx      # Drag-and-drop file upload
│   │       ├── AnalysisCard.jsx    # Entities + risk flags display
│   │       ├── DraftViewer.jsx     # Draft reply display
│   │       └── ChatWindow.jsx      # Message list + input
│   └── package.json
├── demo_docs/                      # Curated test documents (rent agreement, bank notice, govt circular)
├── .env.example
├── .gitignore
└── README.md
```

---

## 🛠️ Tech Stack

| Layer | Technology | Why |
|---|---|---|
| **Backend** | Python 3.10+, FastAPI | Async, fast, typed |
| **AI Orchestration** | LangGraph, LangChain | Stateful agent pipeline |
| **LLM** | Groq (`llama-3.3-70b-versatile`) | Fast inference, free tier |
| **Embeddings** | `sentence-transformers/all-MiniLM-L6-v2` | Local, no API cost |
| **Vector DB** | ChromaDB (PersistentClient) | Local, simple setup |
| **Text Extraction** | PyMuPDF (fitz) | Reliable PDF text extraction |
| **Language Detection** | Devanagari Unicode + `langdetect` | Hindi/Hinglish aware |
| **Chunking** | LangChain `RecursiveCharacterTextSplitter` | Smart boundary-aware splits |
| **Database** | SQLite / PostgreSQL + SQLAlchemy | Simple schema, easy migration |
| **Frontend** | Next.js 14, Tailwind CSS | Fast, file-based routing |

---

## ⚙️ Setup & Installation

### Prerequisites

- Python 3.10+
- Node.js 18+
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
source venv/bin/activate        # Mac/Linux
# venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.txt

# Set up environment
cp ../.env.example .env
# Add your GROQ_API_KEY in .env
```

### 3. Environment Variables

```env
# Required
GROQ_API_KEY=your_groq_api_key_here

# Database (SQLite for local dev)
DATABASE_URL=sqlite:///./documind.db

# ChromaDB
CHROMA_PERSIST_DIR=./chroma_db

# Model config (defaults, can leave as-is)
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
LLM_MODEL=llama-3.3-70b-versatile
CHUNK_SIZE=700
CHUNK_OVERLAP=100
TOP_K_CHUNKS=5
```

### 4. Run the Backend

```bash
cd backend
uvicorn main:app --reload --port 8000
```

- API: `http://localhost:8000`  
- Swagger UI: `http://localhost:8000/docs`

### 5. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

- Frontend: `http://localhost:3000`

---

## 🔌 API Endpoints

### `GET /health`
Health check.
```json
{ "status": "ok" }
```

---

### `POST /upload`
Upload a PDF. Extracts text, detects language, stores in DB, triggers chunking + embedding.

```bash
curl -X POST http://localhost:8000/upload \
  -F "file=@rent_agreement.pdf"
```

```json
{
  "document_id": 1,
  "filename": "rent_agreement.pdf",
  "language_detected": "hindi",
  "status": "processed"
}
```

---

### `POST /analyze`
Run the LangGraph pipeline on an uploaded document. Returns entities, risk flags, and draft reply.

```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"document_id": 1}'
```

```json
{
  "document_id": 1,
  "extracted_entities": {
    "dates": ["15/06/2026", "01/07/2026"],
    "amounts": ["₹12,000", "₹50,000"],
    "parties": ["राहुल पाटीदार", "सुरेश शर्मा"],
    "obligations": ["किराया हर महीने की 5 तारीख को देना होगा"]
  },
  "risk_flags": [
    {
      "clause": "मकान मालिक बिना नोटिस के किरायेदार को बाहर कर सकता है",
      "reason": "यह clause एकतरफा है और किरायेदार के अधिकारों का उल्लंघन करता है"
    }
  ],
  "draft_text": "सेवा में,\nश्री सुरेश शर्मा जी,\n\nमैं इस किराया समझौते की कुछ शर्तों के बारे में..."
}
```

---

### `POST /chat`
Ask a question about an uploaded document (RAG-based).

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"document_id": 1, "question": "इस agreement में notice period क्या है?"}'
```

```json
{
  "answer": "इस agreement के अनुसार notice period 30 दिन का है। Section 4 में लिखा है कि...",
  "sources_used": 3
}
```

---

## 🌐 Multilingual Support

DocuMind uses a two-step language detection strategy:

1. **Devanagari Unicode check** — scans for characters in range `U+0900–U+097F`. If found → classified as `hindi`
2. **`langdetect` fallback** — for pure English vs. romanized Hinglish heuristics

This means it correctly handles:
- Pure Hindi (Devanagari script)
- Pure English
- Mixed Hinglish (Roman script Hindi mixed with English)

The detected language is stored on the document and used to **route LLM prompts** — Hindi documents get Hindi-phrased prompts so the risk flags and draft reply come back in Hindi.

---

## 🎬 Demo Flow

The recommended demo sequence (what to show your professor):

```
1. Upload a rent agreement PDF (Hindi/English)
        ↓
2. See: language detected, document processed

3. Click "Analyze"
        ↓
4. Show: extracted dates, amounts, parties
   Show: risk flags with explanations in Hindi
   Show: auto-generated draft reply letter

5. Go to Chat tab
        ↓
6. Ask: "Notice period kitna hai?"
   Ask: "Security deposit amount kya hai?"
        ↓
7. Show: accurate, document-grounded answers
```

> **Pro tip:** Use the 3 pre-curated docs in `/demo_docs/` — a rent agreement, a government circular, and a bank notice. These are tested and known to work well.

---

## 🧪 Quick Test

```bash
# Test upload
curl -X POST http://localhost:8000/upload -F "file=@demo_docs/rent_agreement.pdf"

# Test analyze (use document_id from above response)
curl -X POST http://localhost:8000/analyze -H "Content-Type: application/json" -d '{"document_id": 1}'

# Test chat
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"document_id": 1, "question": "What is the monthly rent?"}'
```

---

## 🗺️ Phase 1 vs Phase 2

| Area | Phase 1 ✅ (This Repo) | Phase 2 🔄 (Coming) |
|---|---|---|
| Document formats | PDF | + DOCX, images, URLs |
| Language support | Hindi, English, Hinglish | + 8 more Indic languages (indic-bert) |
| Analysis pipeline | LangGraph 3-node graph | Extended multi-agent graph |
| RAG | Single document Q&A | Cross-document search |
| Frontend | Basic Next.js flow | Full dashboard + auth |
| Infra | Local / SQLite | Docker + AWS/GCP deploy |
| Auth | None | JWT-based user sessions |

---

## 📦 Requirements

```
fastapi
uvicorn
sqlalchemy
pymupdf
langchain
langchain-groq
langchain-community
langgraph
chromadb
sentence-transformers
langdetect
python-multipart
pydantic
python-dotenv
```

Install all:
```bash
pip install -r backend/requirements.txt
```

---

## 👨‍💻 Author

**Rahul Patidar**  
MCA, Devi Ahilya Vishwavidyalaya (DAVV), Indore  
Full Stack Developer → AI/GenAI Engineer

[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-0077B5?style=flat&logo=linkedin)](https://linkedin.com/in/your-profile)
[![GitHub](https://img.shields.io/badge/GitHub-Profile-181717?style=flat&logo=github)](https://github.com/your-username)

---

## 📄 License

Developed as MCA Major Project — DAVV Indore, 2026.  
© Rahul Patidar. All rights reserved.

---

<div align="center">

**⭐ Star this repo if you found it useful!**

Made with ❤️ in Indore, India 🇮🇳

</div>
