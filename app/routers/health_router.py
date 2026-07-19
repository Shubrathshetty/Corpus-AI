"""
Corpus AI - Health Check Router
=================================
System health and readiness endpoints.

WHY HEALTH CHECKS?
1. Docker/K8s uses them to know when to restart a container
2. Load balancers use them to route traffic to healthy instances
3. You can quickly verify all services are connected

INTERVIEW NOTE:
"Our health endpoint checks all downstream dependencies (DB, Redis,
ChromaDB, Ollama). If any are down, the response says which one.
This is critical for debugging production issues — you immediately
know which service is the problem."
"""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.schemas import HealthResponse

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="System health check",
)
def health_check(db: Session = Depends(get_db)):
    """Check connectivity to all downstream services.

    Returns status of each dependency:
    - database: Postgres/SQLite connection
    - redis: Cache + queue connection
    - chromadb: Vector database connection
    - ollama: LLM service availability
    """
    result = HealthResponse(
        status="healthy",
        version=settings.APP_VERSION,
    )

    # Check database
    try:
        db.execute(text("SELECT 1"))
        result.database = "connected"
    except Exception:
        result.database = "disconnected"
        result.status = "degraded"

    # Check Redis
    try:
        import redis as redis_lib
        r = redis_lib.from_url(settings.REDIS_URL, socket_timeout=2)
        r.ping()
        result.redis = "connected"
    except Exception:
        result.redis = "disconnected"
        result.status = "degraded"

    # Check ChromaDB
    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(settings.chroma_path))
        client.heartbeat()
        result.chromadb = "connected"
    except Exception:
        result.chromadb = "disconnected"
        result.status = "degraded"

    # Check Ollama
    try:
        import requests
        resp = requests.get(f"{settings.OLLAMA_BASE_URL}/api/tags", timeout=2)
        if resp.status_code == 200:
            result.ollama = "connected"
        else:
            result.ollama = "disconnected"
            result.status = "degraded"
    except Exception:
        result.ollama = "disconnected"
        result.status = "degraded"

    return result
