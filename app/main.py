"""
Corpus AI - FastAPI Application Entry Point
=============================================
Initializes the FastAPI app, configures middleware, and mounts all routers.

DESIGN DECISIONS:
1. API versioning via prefix (/api/v1) — allows future breaking changes
2. CORS middleware — Streamlit runs on a different port (8501 vs 8000)
3. Startup event initializes the database (create_all)
4. Structured error handling for consistent API responses

INTERVIEW NOTE:
"The app is stateless — all state lives in the database, Redis, or
ChromaDB. This means you can run multiple FastAPI instances behind
a load balancer without sticky sessions. Scaling horizontally is
just adding more instances."
"""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.db import init_db

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("corpus_ai")


# ---- Application Lifespan ----
# WHY lifespan OVER @app.on_event?
# @app.on_event("startup") is deprecated in newer FastAPI versions.
# The lifespan context manager is the recommended approach — it handles
# both startup and shutdown cleanly in one place.
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown logic."""
    # ---- Startup ----
    logger.info("🚀 Starting Corpus AI v%s", settings.APP_VERSION)
    logger.info("📂 Database: %s", "SQLite (dev)" if settings.is_sqlite else "PostgreSQL")
    logger.info("📂 Uploads: %s", settings.upload_path)
    logger.info("📂 ChromaDB: %s", settings.chroma_path)

    # Create database tables
    init_db()
    logger.info("✅ Database tables initialized")

    yield  # Application is running

    # ---- Shutdown ----
    logger.info("🛑 Shutting down Corpus AI")


# ---- Create FastAPI App ----
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Multi-tenant AI assistant for enterprise document Q&A. "
        "Upload documents, ask questions in natural language, "
        "get cited answers from your company's internal data."
    ),
    lifespan=lifespan,
    docs_url=f"{settings.API_V1_PREFIX}/docs",      # Swagger UI
    redoc_url=f"{settings.API_V1_PREFIX}/redoc",     # ReDoc
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
)


# ---- CORS Middleware ----
# WHY CORS?
# Streamlit (port 8501) makes API calls to FastAPI (port 8000).
# Without CORS, the browser blocks these cross-origin requests.
# In production, restrict origins to your actual domain.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- Request Logging Middleware ----
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every API request with method, path, status, and latency.

    WHY MIDDLEWARE (not per-endpoint logging)?
    Middleware captures ALL requests including 404s and errors.
    Per-endpoint logging would miss routes that don't exist or
    requests that fail in middleware (auth, rate limiting).

    INTERVIEW NOTE:
    "We log latency at the middleware level so every request is
    captured, including ones that fail in auth or validation.
    This gives us a complete picture for debugging and monitoring."
    """
    start_time = time.time()

    # Process the request
    response = await call_next(request)

    # Calculate latency
    latency_ms = round((time.time() - start_time) * 1000, 2)

    # Log the request
    logger.info(
        "%s %s → %d (%sms)",
        request.method,
        request.url.path,
        response.status_code,
        latency_ms,
    )

    # Add latency header (useful for debugging)
    response.headers["X-Response-Time-Ms"] = str(latency_ms)

    return response


# ---- Global Exception Handler ----
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch all unhandled exceptions and return structured error response.

    WHY STRUCTURED ERRORS?
    Without this, unhandled exceptions return a generic 500 with an HTML
    error page. The frontend expects JSON — this ensures every error
    (even unexpected ones) returns a parseable JSON body.
    """
    logger.error(
        "Unhandled exception on %s %s: %s",
        request.method,
        request.url.path,
        str(exc),
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred. Please try again later.",
                "details": None,
            }
        },
    )


# ---- Register Routers ----
# Import routers here (not at top) to avoid circular imports
from app.routers import auth_router, health_router, document_router, chat_router, dashboard_router  # noqa: E402

# Auth routes: /api/v1/auth/*
app.include_router(auth_router.router, prefix=settings.API_V1_PREFIX)

# Health check: /api/v1/health
app.include_router(health_router.router, prefix=settings.API_V1_PREFIX)

# Documents: /api/v1/documents/*
app.include_router(document_router.router, prefix=settings.API_V1_PREFIX)

# Chat: /api/v1/chat/*
app.include_router(chat_router.router, prefix=settings.API_V1_PREFIX)

# Dashboard: /api/v1/dashboard/*
app.include_router(dashboard_router.router, prefix=settings.API_V1_PREFIX)



# ---- Root Endpoint ----
@app.get("/", include_in_schema=False)
def root():
    """Root endpoint — redirects to API docs."""
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": f"{settings.API_V1_PREFIX}/docs",
        "health": f"{settings.API_V1_PREFIX}/health",
    }
