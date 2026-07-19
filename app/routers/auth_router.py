"""
Corpus AI - Auth Router
========================
Endpoints for user registration, login, token refresh, and invite management.

FLOW OVERVIEW:
1. POST /register → Create company + admin → Return JWT
2. POST /login    → Validate credentials → Return JWT
3. POST /refresh  → Exchange refresh token → Return new access token
4. POST /invite   → Admin generates invite code
5. POST /join     → Employee joins with invite code → Return JWT
"""

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    require_role,
    verify_password,
)
from app.db import get_db
from app.models import Company, Invite, InviteStatus, User, UserRole, utc_now
from app.schemas import (
    CompanyRegister,
    InviteCreate,
    InviteJoin,
    InviteResponse,
    TokenRefresh,
    TokenResponse,
    UserLogin,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ============================================================
# Helper Functions
# ============================================================

def _build_user_response(user: User) -> UserResponse:
    """Convert a User ORM object to a UserResponse schema.

    WHY A HELPER?
    The company_name field requires accessing the relationship.
    Centralizing this prevents inconsistencies across endpoints.
    """
    return UserResponse(
        id=user.id,
        company_id=user.company_id,
        company_name=user.company.name if user.company else None,
        name=user.name,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login=user.last_login,
    )


def _build_token_response(user: User) -> TokenResponse:
    """Generate JWT tokens and build the response for a user."""
    access_token = create_access_token(
        user_id=user.id,
        company_id=user.company_id,
        role=user.role.value,
    )
    refresh_token = create_refresh_token(
        user_id=user.id,
        company_id=user.company_id,
        role=user.role.value,
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=_build_user_response(user),
    )


def _generate_invite_code() -> str:
    """Generate a cryptographically secure 8-character invite code.

    WHY secrets.token_urlsafe?
    - Cryptographically random (unlike random.choice)
    - URL-safe characters (can be shared in links)
    - 8 chars = ~48 bits of entropy (sufficient for invite codes)
    """
    return secrets.token_urlsafe(6)[:8].upper()


# ============================================================
# Endpoints
# ============================================================

@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new company and admin user",
)
def register(data: CompanyRegister, db: Session = Depends(get_db)):
    """Create a new company (tenant) with its first admin user.

    This is the ENTRY POINT for new tenants. It:
    1. Creates a Company record (the tenant boundary)
    2. Creates a User with role=admin (the company owner)
    3. Returns JWT tokens so the user is immediately logged in

    INTERVIEW NOTE:
    "Registration creates both the tenant and the first admin in a single
    transaction. If either fails, both are rolled back. This prevents
    orphaned companies or users."
    """
    # Check if email already exists
    existing_user = db.query(User).filter(User.email == data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists.",
        )

    # Create company (tenant)
    company = Company(name=data.company_name)
    db.add(company)
    db.flush()  # Get company.id without committing

    # Create admin user
    user = User(
        company_id=company.id,
        name=data.admin_name,
        email=data.email,
        password_hash=hash_password(data.password),
        role=UserRole.ADMIN,
        last_login=utc_now(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.refresh(company)

    return _build_token_response(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login with email and password",
)
def login(data: UserLogin, db: Session = Depends(get_db)):
    """Authenticate a user and return JWT tokens.

    SECURITY NOTES:
    - We use a generic error message ("Invalid email or password")
      to prevent email enumeration attacks.
    - We update last_login for dashboard analytics.
    """
    # Find user by email
    user = db.query(User).filter(User.email == data.email).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated. Contact your admin.",
        )

    # Update last login timestamp
    user.last_login = utc_now()
    db.commit()

    return _build_token_response(user)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh an expired access token",
)
def refresh_token(data: TokenRefresh, db: Session = Depends(get_db)):
    """Exchange a valid refresh token for a new access token.

    WHY REFRESH TOKENS?
    Access tokens expire in 30 minutes. Without refresh tokens, the user
    would have to re-enter their password every 30 minutes. With refresh
    tokens, the frontend silently gets a new access token in the background.

    INTERVIEW NOTE:
    "The refresh token flow is: access token expires → frontend catches
    401 → sends refresh token to /auth/refresh → gets new access token →
    retries the original request. The user never notices."
    """
    payload = decode_token(data.refresh_token)

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type. Provide a refresh token.",
        )

    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or deactivated.",
        )

    return _build_token_response(user)


@router.post(
    "/invite",
    response_model=InviteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate an invite code (admin only)",
)
def create_invite(
    data: InviteCreate,
    current_user: User = Depends(require_role("admin", "super_admin")),
    db: Session = Depends(get_db),
):
    """Generate an invite code for a new employee.

    Only admins and super_admins can create invites. The invite code
    is an 8-character alphanumeric string that expires in 7 days.

    WHY INVITE CODES OVER EMAIL?
    $0 budget — no email service. The admin copies the code and shares
    it via Slack, Teams, or in person. Actually more secure than email
    links because it requires out-of-band communication.
    """
    invite_code = _generate_invite_code()

    # Ensure uniqueness (extremely unlikely collision, but be safe)
    while db.query(Invite).filter(Invite.invite_code == invite_code).first():
        invite_code = _generate_invite_code()

    invite = Invite(
        company_id=current_user.company_id,
        created_by=current_user.id,
        invite_code=invite_code,
        email=data.email,
        role=data.role,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)

    return InviteResponse(
        invite_code=invite.invite_code,
        role=invite.role,
        expires_at=invite.expires_at,
    )


@router.post(
    "/join",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Join a company using an invite code",
)
def join_with_invite(data: InviteJoin, db: Session = Depends(get_db)):
    """Employee joins a company using an invite code.

    FLOW:
    1. Validate invite code (exists, pending, not expired)
    2. Check email not already registered
    3. Create user with the role specified in the invite
    4. Mark invite as accepted
    5. Return JWT tokens

    All in a single transaction — if any step fails, everything rolls back.
    """
    # Find and validate invite
    invite = db.query(Invite).filter(
        Invite.invite_code == data.invite_code.upper()
    ).first()

    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid invite code.",
        )

    if invite.status != InviteStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"This invite code has already been {invite.status.value}.",
        )

    if invite.expires_at < datetime.now(timezone.utc):
        # Mark as expired for record keeping
        invite.status = InviteStatus.EXPIRED
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invite code has expired. Ask your admin for a new one.",
        )

    # If invite is email-specific, validate it matches
    if invite.email and invite.email.lower() != data.email.lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invite code was generated for a different email address.",
        )

    # Check if email already exists
    existing_user = db.query(User).filter(User.email == data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists.",
        )

    # Create user in the same company as the invite
    user = User(
        company_id=invite.company_id,
        name=data.name,
        email=data.email,
        password_hash=hash_password(data.password),
        role=invite.role,
        last_login=utc_now(),
    )
    db.add(user)

    # Mark invite as accepted
    invite.status = InviteStatus.ACCEPTED
    db.commit()
    db.refresh(user)

    return _build_token_response(user)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user info",
)
def get_me(current_user: User = Depends(get_current_user)):
    """Return the currently authenticated user's profile.

    Used by the frontend to display user info in the sidebar.
    """
    return _build_user_response(current_user)
