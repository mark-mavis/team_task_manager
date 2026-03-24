from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.user import User, UserRole
from app.services.user_service import get_user_by_id


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """
    FastAPI dependency: reads user_id from the session and returns the User.
    Raises 401 if the session is missing or user does not exist.
    """
    user_id: Optional[int] = request.session.get("user_id")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    user = get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    return user


def get_current_user_optional(
    request: Request, db: Session = Depends(get_db)
) -> Optional[User]:
    """Like get_current_user but returns None instead of raising for unauthenticated routes."""
    user_id: Optional[int] = request.session.get("user_id")
    if user_id is None:
        return None
    return get_user_by_id(db, user_id)


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Dependency that enforces the current user has the admin role."""
    if current_user.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user
