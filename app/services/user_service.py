from typing import Optional

from sqlalchemy.orm import Session

from app.models.user import User, UserRole
from app.schemas.user import UserCreate
from app.services.auth_service import hash_password


def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    return db.query(User).filter(User.username == username).first()


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email).first()


def get_all_users(db: Session) -> list[User]:
    return db.query(User).filter(User.is_active == True).order_by(User.username).all()  # noqa: E712


def create_user(db: Session, data: UserCreate) -> User:
    """Create and persist a new user. Raises ValueError on duplicate email/username."""
    if get_user_by_email(db, data.email):
        raise ValueError(f"Email already registered: {data.email}")
    if get_user_by_username(db, data.username):
        raise ValueError(f"Username already taken: {data.username}")

    user = User(
        email=data.email,
        username=data.username,
        hashed_password=hash_password(data.password),
        role=data.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
