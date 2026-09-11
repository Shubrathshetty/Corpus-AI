# Corpus AI - Enterprise Document Q&A 🧠

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.37+-FF4B4B.svg?logo=streamlit&logoColor=white)](https://streamlit.io)
[![ChromaDB](https://img.shields.io/badge/VectorDB-ChromaDB-blue.svg)](https://www.trychroma.com/)
[![Docker](https://img.shields.io/badge/Docker-Enabled-2496ED.svg?logo=docker&logoColor=white)](https://www.docker.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Corpus AI** is an enterprise-grade, multi-tenant Retrieval-Augmented Generation (RAG) platform designed for organization-wide document intelligence. It enables team members to upload internal documents securely, perform semantic search, ask questions in natural language, and receive precise, cited answers grounded in their organization's internal data.

---

## 🌟 Key Features

- **Multi-Tenant Data Isolation**: Strict tenant scoping (`company_id`) at both the application and database layer guarantees that Company A can never access Company B's data or vector embeddings.
- **Asynchronous RAG Pipeline**: Uploaded documents (PDF, DOCX, TXT, MD) are processed asynchronously using Celery workers, chunked with semantic overlap, and vectorized using `sentence-transformers`.
- **Verifiable Answers with Source Citations**: Every generated LLM answer includes precise citations (source filename, chunk ID, relevance score, and text previews) to prevent hallucination.
- **Enterprise Controls & RBAC**: Role-Based Access Control (`admin` vs `member`), workspace invitations, rate limiting (20 queries/hour/user), and an analytics dashboard with token/latency telemetry.
- **Query Caching & Rate Limiting**: Redis-backed semantic query caching for sub-10ms response times on frequent queries and token-bucket rate limiting to protect LLM infrastructure.
- **Production-Ready & Cloud Deployable**: Pre-configured Docker Compose cluster and Render Blueprint (`render.yaml`) for zero-friction local or cloud deployment.

---

## 🏗️ System Architecture

Corpus AI employs a decoupled, horizontally scalable architecture designed for enterprise workloads:

```mermaid
graph TD
    Client[User / Browser] -->|HTTP / Web| UI["Frontend UI (Streamlit)"]
    UI -->|REST API with JWT| API["Backend API (FastAPI)"]
    
    subgraph Stateless Backend
        API
    end
    
    API -->|Read/Write Metadata & Users| DB[("PostgreSQL / Supabase (or SQLite dev)")]
    API -->|Publish Ingestion Tasks| RedisQueue[("Redis Message Broker & Cache")]
    API -->|Semantic Search| Chroma[("ChromaDB Vector Store")]
    API -->|LLM Inference (Context + Query)| Ollama["LLM (Ollama: Llama-3.1-8B)"]
    
    subgraph Background Processing
        Worker["Celery Worker"]
    end
    
    RedisQueue -->|Consume Ingestion Tasks| Worker
    Worker -->|Read Document File| Storage["Document Storage (Local / Cloud)"]
    Worker -->|Generate Vector Embeddings| LocalEmbed["SentenceTransformers (all-MiniLM-L6-v2)"]
    Worker -->|Upsert Chunks & Embeddings| Chroma
    Worker -->|Update Status (READY / FAILED)| DB
```

### Architecture Design Decisions

1. **Stateless API Layer (FastAPI)**: By keeping the API layer stateless, multiple FastAPI instances can be horizontally scaled behind a load balancer without sticky sessions.
2. **Asynchronous Processing (Celery + Redis)**: Parsing large multi-page PDFs and generating dense vector embeddings are CPU-intensive operations. Offloading ingestion to background workers keeps API endpoints highly responsive and avoids client-side HTTP timeouts.
3. **Caching & Rate Limiting (Redis)**: Redis acts as a high-performance in-memory cache for recent query responses and sliding-window rate limiting (20 queries/hour/user), with automatic graceful degradation if Redis is offline.
4. **Dedicated Vector Database (ChromaDB)**: Chunks and dense vector embeddings are indexed using HNSW for fast cosine-similarity searches across thousands of documents.
5. **Relational Database (SQLAlchemy + PostgreSQL / SQLite)**: User accounts, organizations, document lifecycle metadata, chat threads, and query audit logs are stored in a structured relational database with foreign-key cascades.

---

## 🚀 Tech Stack

| Layer | Technologies |
|---|---|
| **Backend API** | Python 3.11+, FastAPI, Pydantic v2, Pydantic-Settings, Uvicorn |
| **Frontend UI** | Streamlit (Dynamic `st.navigation` & Multi-page routing), Plotly |
| **Database & ORM** | PostgreSQL / Supabase, SQLite (dev), SQLAlchemy 2.0 |
| **Vector Database** | ChromaDB (HNSW cosine similarity) |
| **Embeddings & LLM** | `sentence-transformers/all-MiniLM-L6-v2`, Ollama (Llama-3.1-8B) |
| **Task Queue & Cache** | Celery, Redis |
| **Authentication** | JWT (HS256 via `python-jose`), Bcrypt (`passlib`) |
| **Deployment** | Docker, Docker Compose, Render.com |

---

## 💻 Quick Start & Local Development

### Prerequisites
- Python 3.10, 3.11, or 3.12
- [Docker & Docker Compose](https://www.docker.com/) (recommended) **OR** local Redis + Ollama

---

### Option A: Running with Docker Compose (Recommended)

Run the full multi-container stack with one command:

```bash
# 1. Clone the repository
git clone https://github.com/Shubrathshetty/Corpus-AI.git
cd Corpus-AI

# 2. Copy environment file
cp .env.example .env

# 3. Start all services (API, Worker, Frontend, Redis)
docker-compose up --build
```

Services will be accessible at:
- **Streamlit Frontend**: [http://localhost:8501](http://localhost:8501)
- **FastAPI Backend**: [http://localhost:8000](http://localhost:8000)
- **Interactive Swagger Docs**: [http://localhost:8000/api/v1/docs](http://localhost:8000/api/v1/docs)

---

### Option B: Running Locally (Manual Setup)

#### 1. Setup Virtual Environment
```bash
python -m venv venv
# On Linux/macOS:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

pip install -r requirements.txt
```

#### 2. Configure Environment Variables
```bash
cp .env.example .env
# Edit .env to set your JWT_SECRET_KEY and preferred database URL
```

#### 3. Start Dependent Services

Open separate terminal windows:

**Terminal 1: Ollama (LLM Engine)**
```bash
ollama run llama3.1
```

**Terminal 2: Redis**
```bash
redis-server
```

**Terminal 3: Celery Background Worker**
```bash
celery -A app.worker.celery_app worker --loglevel=info
```

**Terminal 4: FastAPI Server**
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 5: Streamlit Frontend**
```bash
streamlit run frontend/app.py
```

---

## ☁️ Cloud Deployment (Render.com)

Corpus AI includes a native Render Blueprint (`render.yaml`) for deploying the stateless backend and Streamlit frontend:

1. Push your code to GitHub.
2. In [Render Dashboard](https://dashboard.render.com/), click **New > Blueprint**.
3. Connect your repository. Render automatically reads `render.yaml` and provisions:
   - **`corpus-ai-api`**: FastAPI Web Service with automatic port binding.
   - **`corpus-ai-frontend`**: Streamlit Web Service connected to the API.
4. Add your production environment variables (e.g. Supabase `DATABASE_URL`, `JWT_SECRET_KEY`).

For comprehensive instructions, see the [Render Deployment Guide](file:///d:/Projects/Corpus-AI/docs/RENDER_DEPLOYMENT.md).

---

## 📡 API Endpoints Overview

| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `GET` | `/api/v1/health` | System health check (DB, Redis, ChromaDB) | No |
| `POST` | `/api/v1/auth/register` | Register new organization & admin | No |
| `POST` | `/api/v1/auth/login` | Authenticate user & issue JWT tokens | No |
| `POST` | `/api/v1/auth/refresh` | Exchange refresh token for new access token | Yes |
| `GET` | `/api/v1/auth/me` | Retrieve current authenticated user profile | Yes |
| `POST` | `/api/v1/auth/invite` | Generate invitation token for new members | Admin |
| `POST` | `/api/v1/documents/upload` | Upload document (.pdf, .docx, .txt, .md) | Admin |
| `GET` | `/api/v1/documents/` | List company documents and ingestion status | Yes |
| `DELETE`| `/api/v1/documents/{doc_id}` | Remove document, file, and vector embeddings | Admin |
| `POST` | `/api/v1/chat/query` | Ask natural language question with RAG | Yes |
| `GET` | `/api/v1/chat/sessions` | List previous chat threads | Yes |
| `GET` | `/api/v1/chat/history` | Retrieve full message thread with citations | Yes |
| `GET` | `/api/v1/dashboard/stats` | Organization metrics, queries, and storage | Admin |

Interactive OpenAPI documentation is available at `/api/v1/docs`.

---

## 📁 Project Structure

```
Corpus-AI/
├── app/                        # FastAPI Backend Application Core
│   ├── __init__.py
│   ├── main.py                 # FastAPI initialization, middleware & router mounting
│   ├── config.py               # Pydantic BaseSettings centralized configuration
│   ├── db.py                   # SQLAlchemy engine, session maker & WAL mode
│   ├── models.py               # ORM Models (User, Company, Document, Chunk, Chat)
│   ├── schemas.py              # Pydantic v2 validation schemas
│   ├── auth.py                 # JWT token management, password hashing & RBAC
│   ├── dependencies.py         # Shared dependencies (get_db, require_role)
│   ├── worker.py               # Celery worker tasks for document processing
│   ├── routers/                # API route controllers
│   │   ├── auth_router.py
│   │   ├── chat_router.py
│   │   ├── dashboard_router.py
│   │   ├── document_router.py
│   │   └── health_router.py
│   └── services/               # Business logic services
│       ├── __init__.py
│       ├── document_processor.py
│       ├── embedding_service.py
│       └── vector_store.py
├── frontend/                   # Streamlit Multi-Page Web Interface
│   ├── app.py                  # Main entrance & dynamic role-based router
│   ├── components/             # Reusable UI components (Sidebar, Auth state)
│   ├── pages/                  # Streamlit pages (Chat, Documents, Dashboard, Settings, Login)
│   └── utils/                  # API client wrapper with auto-refresh interceptor
├── docs/                       # Comprehensive project documentation
│   ├── PRD.md                  # Product Requirement Document
│   ├── TRD.md                  # Technical Architecture Document
│   ├── RENDER_DEPLOYMENT.md    # Render.com deployment guide
│   └── RESUME_BULLETS.md       # High-impact resume bullet points & interview guide
├── Dockerfile                  # Production container for FastAPI & Celery
├── frontend.Dockerfile         # Production container for Streamlit UI
├── docker-compose.yml          # Local multi-service composition
├── render.yaml                 # Render Blueprint Infrastructure-as-Code
├── requirements.txt            # Python dependencies
├── PROJECT_TASKS.md            # Development progress tracker
└── README.md                   # Project overview & documentation
```

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
