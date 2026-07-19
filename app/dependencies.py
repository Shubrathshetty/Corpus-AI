"""
Corpus AI - FastAPI Dependencies
==================================
Shared dependency injections for API endpoints.

WHY DEPENDENCY INJECTION?
1. Decouples endpoint logic from resource acquisition (e.g. database sessions)
2. Enforces security checks (authentication, role checks) before route runs
3. Makes unit testing easier by allowing mock dependency overrides

INTERVIEW NOTE:
"We use FastAPI dependency injection to enforce tenant isolation.
The get_company_id dependency extracts the company_id directly from the
authenticated user. Since endpoints depend on this, they cannot access
data outside their tenant."
"""

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.models import User, UserRole


def get_current_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Ensure the current user is a company admin or super admin.

    Usage:
        @router.post("/invite")
        def invite(admin: User = Depends(get_current_admin)):
            ...
    """
    if current_user.role not in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can perform this action.",
        )
    return current_user


def get_current_super_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Ensure the current user is a super admin (platform owner)."""
    if current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only platform super administrators can perform this action.",
        )
    return current_user


def get_company_id(
    current_user: User = Depends(get_current_user),
) -> str:
    """Extract and return the tenant's company_id.

    This makes route signatures clean when they only need the ID, not the user object.
    """
    return current_user.company_id
