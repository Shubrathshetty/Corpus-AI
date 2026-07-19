"""
Corpus AI - Database Setup
===========================
SQLAlchemy engine, session factory, and Base model.

WHY SYNCHRONOUS SQLAlchemy (not async)?
- Simpler code, easier to debug
- At 50 users, sync with FastAPI's threadpool is more than sufficient
- SQLite (our dev DB) has limited async support
- Async is a premature optimization at this scale

INTERVIEW NOTE:
"We chose sync SQLAlchemy because our V1 target is 50 users. FastAPI
runs sync dependencies in a threadpool, so we still get concurrency.
For V2 at 10k users, we'd switch to async SQLAlchemy + asyncpg —
the ORM models stay identical, only the engine/session setup changes."

SCALING PATH:
  V1: Sync SQLAlchemy + SQLite       (50 users)
  V2: Async SQLAlchemy + asyncpg     (10k users)
  V3: Read replicas + connection pool (100k users)
"""

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


# ---- Engine Setup ----
# connect_args for SQLite: check_same_thread=False allows FastAPI's
# threadpool to use the connection across threads (safe for our use case)
engine_kwargs = {}
if settings.is_sqlite:
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.LOG_LEVEL == "DEBUG",  # Log SQL queries in debug mode
    pool_pre_ping=True,                  # Verify connections before use
    **engine_kwargs,
)


# Enable WAL mode for SQLite — dramatically improves concurrent read performance
# WHY: Default SQLite locks the entire database on writes. WAL mode allows
# concurrent readers even during writes. Essential for a web app.
if settings.is_sqlite:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")  # SQLite doesn't enforce FKs by default!
        cursor.close()


# ---- Session Factory ----
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,  # Prevent lazy-load issues after commit
)


# ---- Base Model ----
class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models.

    All models inherit from this. It provides:
    - Automatic table name generation
    - Shared metadata for create_all() / migrations
    """
    pass


# ---- Dependency Injection ----
def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that provides a database session per request.

    Usage in a route:
        @router.get("/items")
        def list_items(db: Session = Depends(get_db)):
            return db.query(Item).all()

    WHY A GENERATOR?
    The `finally` block guarantees the session is closed even if the
    request handler raises an exception. This prevents connection leaks.

    INTERVIEW NOTE:
    "We use dependency injection for database sessions because it
    ensures proper lifecycle management — one session per request,
    automatic cleanup, and easy to mock in tests."
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all database tables.

    Called on application startup. Uses Base.metadata.create_all()
    which is idempotent — safe to call multiple times.

    NOTE: For production, replace with Alembic migrations.
    """
    Base.metadata.create_all(bind=engine)
