from typing import Optional

from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.models.user import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    """Return a bcrypt hash of the given password."""
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Return True if plain_password matches the stored hash."""
    return pwd_context.verify(plain_password, hashed_password)


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    """
    Look up a user by username and verify their password.
    Returns the User on success, None on failure.
    """
    user = db.query(User).filter(User.username == username, User.is_active == True).first()  # noqa: E712
    if user is None:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user
