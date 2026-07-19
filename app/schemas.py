"""
Corpus AI - Pydantic Schemas
==============================
Request/response models for the FastAPI API.

WHY SEPARATE SCHEMAS FROM ORM MODELS?
SQLAlchemy models define database structure. Pydantic schemas define
API contracts. Keeping them separate means:
1. We control exactly what data goes in/out of the API
2. Password hashes never accidentally leak to the frontend
3. We can evolve the API independently from the database

INTERVIEW NOTE:
"We use Pydantic schemas as a serialization boundary. The ORM model
has password_hash, but the API response schema UserResponse doesn't.
This makes it structurally impossible to leak sensitive data — it's
not just a convention, it's enforced by the type system."
"""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models import DocumentStatus, InviteStatus, UserRole


# ============================================================
# Auth Schemas
# ============================================================

class CompanyRegister(BaseModel):
    """Request: Register a new company + admin user."""
    company_name: str = Field(..., min_length=2, max_length=100, examples=["Acme Corp"])
    admin_name: str = Field(..., min_length=2, max_length=100, examples=["Sarah Chen"])
    email: str = Field(..., max_length=255, examples=["sarah@acme.com"])
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        """Basic email format validation.

        WHY NOT EmailStr?
        EmailStr requires the 'email-validator' package which adds a dependency.
        For a portfolio project, basic validation is sufficient. In production,
        you'd use EmailStr or validate on the frontend too.
        """
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email format")
        return v.lower().strip()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Enforce minimum password complexity."""
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class UserLogin(BaseModel):
    """Request: Login with email and password."""
    email: str = Field(..., examples=["sarah@acme.com"])
    password: str = Field(...)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.lower().strip()


class TokenResponse(BaseModel):
    """Response: JWT tokens after login/register."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: "UserResponse"


class TokenRefresh(BaseModel):
    """Request: Refresh an expired access token."""
    refresh_token: str


class InviteCreate(BaseModel):
    """Request: Admin creates an invite code."""
    email: str | None = Field(None, examples=["raj@acme.com"])
    role: UserRole = UserRole.MEMBER


class InviteResponse(BaseModel):
    """Response: Generated invite code."""
    invite_code: str
    role: UserRole
    expires_at: datetime


class InviteJoin(BaseModel):
    """Request: Employee joins using an invite code."""
    invite_code: str = Field(..., min_length=8, max_length=8)
    name: str = Field(..., min_length=2, max_length=100)
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.lower().strip()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


# ============================================================
# User Schemas
# ============================================================

class UserResponse(BaseModel):
    """Response: User data (never includes password_hash)."""
    id: str
    company_id: str
    company_name: str | None = None
    name: str
    email: str
    role: UserRole
    is_active: bool
    created_at: datetime
    last_login: datetime | None = None

    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    """Response: List of users in a company."""
    users: list[UserResponse]
    total: int


# ============================================================
# Document Schemas
# ============================================================

class DocumentResponse(BaseModel):
    """Response: Document metadata."""
    id: str
    company_id: str
    filename: str
    file_type: str
    file_size_bytes: int
    status: DocumentStatus
    chunk_count: int
    error_message: str | None = None
    created_at: datetime
    processed_at: datetime | None = None

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    """Response: List of documents for a company."""
    documents: list[DocumentResponse]
    total: int


# ============================================================
# Chat Schemas
# ============================================================

class ChatQuery(BaseModel):
    """Request: Ask a question.

    session_id is optional — if not provided, a new session is created.
    This allows both "start new conversation" and "continue existing" flows.
    """
    question: str = Field(
        ..., min_length=3, max_length=1000,
        examples=["What is our parental leave policy?"]
    )
    session_id: str | None = Field(
        None, description="Optional: continue an existing chat session"
    )


class Source(BaseModel):
    """A cited source chunk in a chat response."""
    document_name: str
    chunk_id: str
    relevance_score: float
    text_preview: str


class ChatResponse(BaseModel):
    """Response: Answer from the RAG pipeline."""
    answer: str
    sources: list[Source]
    session_id: str
    metadata: dict = Field(
        default_factory=dict,
        examples=[{
            "latency_ms": 2340,
            "tokens_used": 512,
            "cached": False,
            "model": "llama3.1:8b"
        }]
    )


class ChatHistoryMessage(BaseModel):
    """A single message in chat history."""
    id: str
    role: str  # "user" or "assistant"
    content: str
    sources: list[Source] | None = None
    metadata: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatHistoryResponse(BaseModel):
    """Response: Chat history for a session."""
    session_id: str
    title: str | None = None
    messages: list[ChatHistoryMessage]


class ChatSessionListItem(BaseModel):
    """A chat session summary for listing."""
    id: str
    title: str | None = None
    created_at: datetime
    message_count: int = 0

    model_config = {"from_attributes": True}


class ChatSessionListResponse(BaseModel):
    """Response: List of chat sessions."""
    sessions: list[ChatSessionListItem]
    total: int


# ============================================================
# Dashboard Schemas
# ============================================================

class DashboardStats(BaseModel):
    """Response: Company-level statistics."""
    total_documents: int
    total_queries: int
    active_users: int
    total_chunks: int
    avg_latency_ms: float | None = None
    cache_hit_ratio: float | None = None


class PopularQuery(BaseModel):
    """A frequently asked question."""
    question: str
    count: int


class UsageDataPoint(BaseModel):
    """A single data point for usage over time."""
    date: str  # ISO date string (YYYY-MM-DD)
    query_count: int


class DashboardPopularResponse(BaseModel):
    """Response: Top queries for a company."""
    queries: list[PopularQuery]


class DashboardUsageResponse(BaseModel):
    """Response: Usage over time."""
    data: list[UsageDataPoint]
    period_days: int = 30


# ============================================================
# Health Schema
# ============================================================

class HealthResponse(BaseModel):
    """Response: System health check."""
    status: str = "healthy"
    version: str
    database: str = "connected"
    redis: str = "connected"
    ollama: str = "unknown"
    chromadb: str = "connected"


# ============================================================
# Error Schema
# ============================================================

class ErrorDetail(BaseModel):
    """Standardized error response body.

    WHY STRUCTURED ERRORS?
    The frontend can parse error codes programmatically (e.g., show
    a specific message for RATE_LIMIT_EXCEEDED vs AUTH_INVALID_CREDENTIALS).
    Unstructured error strings require brittle string matching.
    """
    code: str
    message: str
    details: dict | None = None


class ErrorResponse(BaseModel):
    """Wrapper for error responses."""
    error: ErrorDetail
