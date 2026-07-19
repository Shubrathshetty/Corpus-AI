"""
Corpus AI - Authentication Module
===================================
JWT token management and password hashing.

SECURITY DESIGN:
- Passwords: bcrypt hashing (adaptive, salt included, industry standard)
- Tokens: JWT with HS256 (shared secret, sufficient for single-service arch)
- Access token: Short-lived (30 min) — limits damage window if stolen
- Refresh token: Long-lived (7 days) — used only to get new access tokens

WHY JWT OVER SESSION COOKIES?
1. Stateless: No server-side session store needed
2. Contains claims (user_id, company_id, role) — avoids DB lookup on every request
3. Works seamlessly with Streamlit (sends token in Authorization header)
4. Standard for API-first architectures

INTERVIEW NOTE:
"We use short-lived access tokens (30 min) with long-lived refresh tokens
(7 days). If an access token is stolen, the attacker has a 30-minute window.
The refresh token is only sent to /auth/refresh, reducing its exposure surface.
This is the OAuth2 pattern used by Google, GitHub, and most modern APIs."
"""

from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import User

# ---- Password Hashing ----
# WHY bcrypt?
# - Adaptive: cost factor can be increased as hardware gets faster
# - Salt is built-in: no separate salt storage needed
# - Industry standard: used by Django, Rails, Spring Boot
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ---- JWT Bearer Scheme ----
# This tells FastAPI to look for "Authorization: Bearer <token>" header
security = HTTPBearer()


# ============================================================
# Password Functions
# ============================================================

def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt.

    The returned hash includes the algorithm, cost factor, salt,
    and hash — all in one string. Example:
    $2b$12$LJ3m4ys4Gk8rWJGxN/Y4sO...
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash.

    WHY NOT compare hashes directly?
    bcrypt uses a random salt per hash, so the same password produces
    different hashes each time. passlib handles the salt extraction
    and comparison internally.
    """
    return pwd_context.verify(plain_password, hashed_password)


# ============================================================
# JWT Token Functions
# ============================================================

def create_access_token(
    user_id: str,
    company_id: str,
    role: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a short-lived JWT access token.

    The token contains:
    - sub: user ID (standard JWT claim)
    - company_id: for tenant isolation
    - role: for RBAC
    - type: "access" (to distinguish from refresh tokens)
    - exp: expiration time

    WHY PUT company_id AND role IN THE TOKEN?
    Avoids a database lookup on every API request. The middleware
    can extract these from the token and inject them as dependencies.
    """
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {
        "sub": user_id,
        "company_id": company_id,
        "role": role,
        "type": "access",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(
    user_id: str,
    company_id: str,
    role: str,
) -> str:
    """Create a long-lived JWT refresh token.

    Refresh tokens have minimal claims — they're only used to
    obtain new access tokens, not for API authorization.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    payload = {
        "sub": user_id,
        "company_id": company_id,
        "role": role,
        "type": "refresh",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token.

    Raises HTTPException if:
    - Token is malformed
    - Token has expired
    - Token signature is invalid

    Returns the decoded payload dict.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ============================================================
# FastAPI Dependencies
# ============================================================

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI dependency: Extract and validate the current user from JWT.

    This is injected into every protected endpoint:
        @router.get("/documents/")
        def list_docs(user: User = Depends(get_current_user)):
            # user.company_id is guaranteed to be set
            ...

    SECURITY FLOW:
    1. Extract Bearer token from Authorization header
    2. Decode JWT and validate signature + expiration
    3. Verify it's an access token (not refresh)
    4. Load user from database (ensures user still exists and is active)
    5. Return User object with company_id for tenant isolation

    WHY LOAD FROM DB (not just use token claims)?
    The token might be valid but the user could be:
    - Deactivated by an admin
    - Deleted
    - Role changed (token has stale role)
    The DB check ensures we have the latest state.
    """
    token = credentials.credentials
    payload = decode_token(token)

    # Verify this is an access token, not a refresh token
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type. Use an access token.",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing user ID.",
        )

    # Load user from database
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated.",
        )

    return user


def require_role(*allowed_roles: str):
    """FastAPI dependency factory: Restrict endpoint to specific roles.

    Usage:
        @router.post("/invite", dependencies=[Depends(require_role("admin", "super_admin"))])
        def create_invite(...):
            ...

    INTERVIEW NOTE:
    "This is a dependency factory pattern. It returns a new dependency
    function that checks if the user's role is in the allowed list.
    It's composable — you can mix and match roles per endpoint."
    """
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role.value not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires one of these roles: {', '.join(allowed_roles)}",
            )
        return current_user
    return role_checker
