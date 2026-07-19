"""
Corpus AI - Application Configuration
======================================
Centralized settings using Pydantic BaseSettings.

WHY pydantic-settings?
- Type validation on startup (fail fast if env vars are wrong)
- Auto-loads from .env file
- IDE autocomplete on settings.XXX
- No scattered os.getenv() calls across the codebase

INTERVIEW NOTE:
"We use pydantic-settings because it validates all configuration at
startup. If DATABASE_URL is missing, the app crashes immediately with
a clear error — not 10 minutes later when the first DB query runs."
"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    All configuration for Corpus AI.
    Values are loaded from environment variables or .env file.
    """

    # ---- App Metadata ----
    APP_NAME: str = "Corpus AI"
    APP_VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"

    # ---- Database ----
    # SQLite for local dev, Postgres for production
    DATABASE_URL: str = "sqlite:///./data/corpus_ai.db"

    # ---- Redis ----
    REDIS_URL: str = "redis://localhost:6379/0"

    # ---- LLM (Ollama) ----
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.1:8b"

    # ---- Embeddings ----
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"

    # ---- ChromaDB ----
    CHROMA_PERSIST_DIR: str = "./data/chroma"

    # ---- JWT Authentication ----
    JWT_SECRET_KEY: str = "CHANGE-ME-generate-a-real-secret-key"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ---- File Storage ----
    UPLOAD_DIR: str = "./data/uploads"

    # ---- Rate Limiting ----
    RATE_LIMIT_PER_HOUR: int = 20

    # ---- Logging ----
    LOG_LEVEL: str = "INFO"

    # ---- Pydantic Settings Config ----
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",  # Ignore unexpected env vars
    )

    @property
    def is_sqlite(self) -> bool:
        """Check if we're using SQLite (local dev) vs Postgres (production).

        WHY THIS MATTERS:
        SQLite doesn't support some Postgres features (ARRAY, async, etc.).
        This flag lets us branch behavior where needed.
        """
        return self.DATABASE_URL.startswith("sqlite")

    @property
    def upload_path(self) -> Path:
        """Resolved upload directory path. Creates it if needed."""
        path = Path(self.UPLOAD_DIR)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def chroma_path(self) -> Path:
        """Resolved ChromaDB persistence path. Creates it if needed."""
        path = Path(self.CHROMA_PERSIST_DIR)
        path.mkdir(parents=True, exist_ok=True)
        return path


# Singleton settings instance — import this everywhere
# Usage: from app.config import settings
settings = Settings()
