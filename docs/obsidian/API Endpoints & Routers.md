# 🌐 API Endpoints & Routers

#api #fastapi #routes #backend
Parent: [[00 - Corpus AI Map of Content (MOC)]]

All API routes are prefixed under `/api/v1` and documented automatically with Swagger UI at `/api/v1/docs`.

---

## 📡 Route Catalog

### 1. Authentication (`/api/v1/auth`) — `app/routers/auth_router.py`
| Method | Endpoint | Description | Access |
| :--- | :--- | :--- | :--- |
| `POST` | `/auth/register` | Register new company and first admin user | Public |
| `POST` | `/auth/login` | Authenticate with email/password; returns JWT pair | Public |
| `POST` | `/auth/refresh` | Exchange refresh token for new access token | Public |
| `POST` | `/auth/invite` | Generate an 8-character company invite code | Admin only |
| `POST` | `/auth/join` | Join existing company using invite code | Public |
| `GET` | `/auth/me` | Fetch currently authenticated user profile | Authenticated |
| `GET` | `/auth/users` | List all users in company | Admin only |

### 2. Documents (`/api/v1/documents`) — `app/routers/document_router.py`
| Method | Endpoint | Description | Access |
| :--- | :--- | :--- | :--- |
| `POST` | `/documents/upload` | Upload PDF/DOCX/TXT file for background chunking | Admin only |
| `GET` | `/documents` | List all indexed documents in the company | Authenticated |
| `GET` | `/documents/{id}/status` | Check processing status (`pending`, `ready`, `failed`) | Authenticated |
| `DELETE` | `/documents/{id}` | Delete document and remove vectors from ChromaDB | Admin only |

### 3. Chat & Q&A (`/api/v1/chat`) — `app/routers/chat_router.py`
| Method | Endpoint | Description | Access |
| :--- | :--- | :--- | :--- |
| `POST` | `/chat` | Query RAG assistant; returns cited answer | Authenticated |
| `GET` | `/chat/history` | Retrieve user chat session history | Authenticated |
| `POST` | `/chat/sessions` | Create a new conversation session | Authenticated |

### 4. Dashboard & Analytics (`/api/v1/dashboard`) — `app/routers/dashboard_router.py`
| Method | Endpoint | Description | Access |
| :--- | :--- | :--- | :--- |
| `GET` | `/dashboard/stats` | Aggregated usage, total queries, storage, docs count | Admin only |
| `GET` | `/dashboard/popular-queries` | Most frequent questions asked by team | Admin only |

### 5. Health (`/api/v1/health`) — `app/routers/health_router.py`
| Method | Endpoint | Description | Access |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | Health check for DB, Redis, and vector store | Public |
