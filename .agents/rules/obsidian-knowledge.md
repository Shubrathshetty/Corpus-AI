---
description: Always consult the Obsidian Knowledge Graph before scanning files
globs: *
---

# Corpus AI Knowledge Index Protocol

When the user asks questions, requests features, or seeks bug fixes for Corpus AI:

1. **NEVER traverse or scan the entire repository repeatedly.**
2. **First consult `docs/obsidian/00 - Corpus AI Map of Content (MOC).md`** and its linked notes in `docs/obsidian/`:
   - `Architecture & System Overview.md`: High-level data flow, tenant isolation.
   - `Docker & Deployment Services.md`: Container setup (`corpus_api`, `corpus_frontend`, `corpus_worker`, `corpus_redis`).
   - `Auth & Multi-Tenancy.md`: JWT auth, roles, and company separation.
   - `RAG Pipeline & ChromaDB.md`: Ingestion, Celery tasks, embedding models, vector search.
   - `API Endpoints & Routers.md`: Fast lookup of endpoint definitions, request/response models.
   - `Frontend & Streamlit UI.md`: Streamlit pages, role-based navigation, API client.
3. Only inspect specific target files when an edit or targeted debugging is directly required.
