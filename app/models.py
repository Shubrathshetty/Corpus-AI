"""
Corpus AI - SQLAlchemy Models
==============================
All database tables defined as SQLAlchemy ORM models.

MULTI-TENANCY STRATEGY:
Every table that holds tenant data includes a `company_id` column.
Every query MUST filter by company_id to ensure data isolation.

WHY company_id ON EVERY TABLE (not just via JOINs)?
Direct filtering is faster than JOINing through User → Company.
It also makes the isolation explicit and harder to accidentally skip.

INTERVIEW NOTE:
"We chose row-level isolation with company_id over database-per-tenant
because at 50 users, separate databases are overkill. This approach is
used by most SaaS startups (Slack, Notion) and allows migration to
schema-per-tenant later without changing application code."
"""

import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


# ============================================================
# Enums
# ============================================================

class UserRole(str, PyEnum):
    """User roles for RBAC (Role-Based Access Control).

    WHY str + Enum?
    Inheriting from str makes the enum JSON-serializable automatically.
    Pydantic and FastAPI handle str enums natively — no custom serializer needed.
    """
    SUPER_ADMIN = "super_admin"  # Platform operator (you, the developer)
    ADMIN = "admin"              # Company admin who manages their tenant
    MEMBER = "member"            # Regular employee who can only chat


class DocumentStatus(str, PyEnum):
    """Tracks document through the async processing pipeline.

    Flow: UPLOADING → PROCESSING → READY (or FAILED)

    WHY A STATE MACHINE?
    Document processing is async (Celery). The frontend polls this status
    to show progress. Without explicit states, the UI wouldn't know if a
    document is still being processed or if it silently failed.
    """
    UPLOADING = "uploading"    # File received, saved to disk
    PROCESSING = "processing"  # Celery worker is chunking + embedding
    READY = "ready"            # Chunks embedded and stored in ChromaDB
    FAILED = "failed"          # Something went wrong (see error_message)


class InviteStatus(str, PyEnum):
    """Invite code lifecycle."""
    PENDING = "pending"    # Code generated, not yet used
    ACCEPTED = "accepted"  # Employee joined using this code
    EXPIRED = "expired"    # Code past expiry date


# ============================================================
# Helper
# ============================================================

def generate_uuid() -> str:
    """Generate a new UUID as a string.

    WHY STRING, NOT UUID TYPE?
    SQLite doesn't have a native UUID type. Using String(36) works
    identically across SQLite (dev) and Postgres (production).
    """
    return str(uuid.uuid4())


def utc_now() -> datetime:
    """Current UTC timestamp. Always timezone-aware."""
    return datetime.now(timezone.utc)


# ============================================================
# Models
# ============================================================

class Company(Base):
    """A tenant (company) in the multi-tenant system.

    This is the ROOT of the multi-tenancy model. Every other entity
    belongs to exactly one Company.

    INTERVIEW NOTE:
    "Company is the tenant boundary. We use a single shared database
    with company_id filtering (row-level isolation) rather than
    separate databases per tenant. This is simpler to manage and
    sufficient for our scale."
    """
    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=utc_now, nullable=True
    )

    # Relationships — cascade delete ensures clean tenant removal
    users = relationship("User", back_populates="company", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="company", cascade="all, delete-orphan")
    invites = relationship("Invite", back_populates="company", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_companies_name", "name"),
    )

    def __repr__(self) -> str:
        return f"<Company(id={self.id}, name={self.name})>"


class User(Base):
    """An authenticated user belonging to a company.

    SECURITY NOTES:
    - password_hash stores bcrypt hash, NEVER plaintext
    - email is globally unique (not per-company) to prevent confusion
    - role field implements RBAC (see UserRole enum)

    INTERVIEW NOTE:
    "Every user has a company_id. Every API endpoint extracts this from
    the JWT token and uses it to filter all database queries. This makes
    cross-tenant data leaks structurally impossible — you'd have to
    deliberately bypass the dependency injection to access another
    tenant's data."
    """
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    company_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("companies.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SQLEnum(UserRole), nullable=False, default=UserRole.MEMBER
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    last_login: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    company = relationship("Company", back_populates="users")
    documents = relationship("Document", back_populates="uploaded_by_user")
    chat_sessions = relationship("ChatSession", back_populates="user")

    __table_args__ = (
        Index("ix_users_company_email", "company_id", "email"),
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email}, role={self.role})>"


class Invite(Base):
    """Invite code for onboarding employees to a company.

    WHY INVITE CODES INSTEAD OF EMAIL INVITATIONS?
    Email delivery requires an SMTP service or third-party API (SendGrid, etc.)
    — that costs money. Invite codes are free: admin generates a code, shares
    it on Slack or in person. The employee enters the code to join.

    INTERVIEW NOTE:
    "We chose invite codes over email invites to stay within our $0 budget.
    The admin generates an 8-character code and shares it out-of-band.
    This is actually more secure than email links because it requires the
    employee to also know the company context."
    """
    __tablename__ = "invites"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    company_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("companies.id"), nullable=False, index=True
    )
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    invite_code: Mapped[str] = mapped_column(
        String(8), unique=True, nullable=False, index=True
    )
    email: Mapped[str | None] = mapped_column(
        String(255), nullable=True  # Optional: pre-assign to specific email
    )
    role: Mapped[UserRole] = mapped_column(
        SQLEnum(UserRole), nullable=False, default=UserRole.MEMBER
    )
    status: Mapped[InviteStatus] = mapped_column(
        SQLEnum(InviteStatus), default=InviteStatus.PENDING, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    # Relationships
    company = relationship("Company", back_populates="invites")
    creator = relationship("User", foreign_keys=[created_by])

    def __repr__(self) -> str:
        return f"<Invite(code={self.invite_code}, status={self.status})>"


class Document(Base):
    """Metadata for an uploaded document.

    The actual file is stored on disk (see storage_path).
    The text chunks are in document_chunks table + ChromaDB.

    WHY SEPARATE FILE STORAGE FROM METADATA?
    Files are large binary blobs. Storing them in Postgres bloats the DB,
    slows backups, and wastes expensive cloud DB storage. Instead we store
    files on disk/object storage and keep only metadata in Postgres.

    STATUS FLOW:
      uploading → processing → ready
                              → failed (with error_message)
    """
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    company_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("companies.id"), nullable=False, index=True
    )
    uploaded_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(10), nullable=False)  # pdf, docx, txt
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        SQLEnum(DocumentStatus), default=DocumentStatus.UPLOADING, nullable=False
    )
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    company = relationship("Company", back_populates="documents")
    uploaded_by_user = relationship("User", back_populates="documents")
    chunks = relationship(
        "DocumentChunk", back_populates="document", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_documents_company_status", "company_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<Document(id={self.id}, filename={self.filename}, status={self.status})>"


class DocumentChunk(Base):
    """Individual text chunk from a processed document.

    Each chunk has a corresponding embedding vector in ChromaDB.
    We store the text here in Postgres so we can display it in
    citations without querying the vector database.

    WHY STORE TEXT IN BOTH POSTGRES AND CHROMADB?
    ChromaDB is optimized for similarity search, not text retrieval.
    When we show citations, we need the chunk text — fetching it from
    Postgres (indexed, fast) is simpler than from ChromaDB.
    The chroma_id links the two for deletion/updates.
    """
    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    chroma_id: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True
    )

    # Relationships
    document = relationship("Document", back_populates="chunks")

    __table_args__ = (
        Index("ix_chunks_document_index", "document_id", "chunk_index"),
        UniqueConstraint("document_id", "chunk_index", name="uq_chunk_order"),
    )

    def __repr__(self) -> str:
        return f"<DocumentChunk(doc={self.document_id}, index={self.chunk_index})>"


class ChatSession(Base):
    """Groups related chat messages into a conversation.

    WHY SESSIONS?
    Users may have multiple conversation threads (one about HR policies,
    another about engineering processes). Sessions let us:
    1. Show conversation history per thread
    2. Maintain context within a session (last 5 turns)
    3. Auto-generate titles for quick identification
    """
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    company_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("companies.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(
        String(200), nullable=True  # Auto-generated from first question
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=utc_now, nullable=True
    )

    # Relationships
    company = relationship("Company")
    user = relationship("User", back_populates="chat_sessions")
    messages = relationship(
        "ChatMessage", back_populates="session", cascade="all, delete-orphan",
        order_by="ChatMessage.created_at"
    )

    def __repr__(self) -> str:
        return f"<ChatSession(id={self.id}, title={self.title})>"


class ChatMessage(Base):
    """Individual message in a chat session.

    Stores both user questions and AI answers.

    WHY JSON FOR SOURCES AND METADATA?
    Sources (cited document chunks) and metadata (latency, tokens)
    are always read/written together with the message, never queried
    independently. Using JSON avoids a separate join table and keeps
    the schema simple.

    INTERVIEW NOTE:
    "This is a pragmatic denormalization. If we needed to query
    'which documents are cited most often', we'd normalize sources
    into a separate table. But for V1, JSON is sufficient and simpler."
    """
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(
        String(10), nullable=False  # "user" or "assistant"
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sources: Mapped[dict | None] = mapped_column(
        JSON, nullable=True  # [{document_name, chunk_id, score, preview}]
    )
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata", JSON, nullable=True  # {latency_ms, tokens_used, cached, model}
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    # Relationships
    session = relationship("ChatSession", back_populates="messages")

    def __repr__(self) -> str:
        return f"<ChatMessage(role={self.role}, session={self.session_id})>"


class QueryLog(Base):
    """Analytics log for every query processed.

    Separate from ChatMessage to avoid bloating the chat table
    with analytics data.

    WHY A SEPARATE LOG TABLE?
    1. Chat messages are user-facing; query logs are operator-facing
    2. Log queries can be aggressive (aggregations, time ranges)
       without impacting chat performance
    3. Follows CQRS pattern: separate write model (logs) from
       read model (dashboard aggregations)

    INTERVIEW NOTE:
    "QueryLog is append-only — we never update or delete rows.
    This makes it perfect for analytics: we can run aggregation
    queries for the dashboard without worrying about data mutations.
    It's a lightweight CQRS pattern."
    """
    __tablename__ = "query_logs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    company_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("companies.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    top_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )

    # Relationships
    company = relationship("Company")
    user = relationship("User")

    __table_args__ = (
        Index("ix_query_logs_company_created", "company_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<QueryLog(question={self.question[:30]}..., latency={self.latency_ms}ms)>"
