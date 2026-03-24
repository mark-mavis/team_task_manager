"""
Shared pytest fixtures for the entire test suite.

Design goals demonstrated here:
  - Isolated SQLite database per test session (not the dev database)
  - FastAPI dependency overrides for get_db
  - Reusable factory helpers (make_user, make_task)
  - Session-scoped engine + per-test transaction rollback for speed
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models.user import User, UserRole
from app.models.task import Task, TaskStatus, TaskPriority
from app.services.auth_service import hash_password

# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="session")
def engine():
    """
    Create a single in-memory SQLite engine for the whole test session.
    StaticPool keeps the same connection so all operations share state.
    """
    _engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=_engine)
    yield _engine
    Base.metadata.drop_all(bind=_engine)


@pytest.fixture()
def db(engine) -> Session:
    """
    Per-test database session wrapped in a transaction that rolls back
    at the end of the test, giving each test a clean slate.
    """
    connection = engine.connect()
    transaction = connection.begin()
    TestingSession = sessionmaker(bind=connection, autocommit=False, autoflush=False)
    session = TestingSession()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


# ---------------------------------------------------------------------------
# FastAPI test client
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(db: Session) -> TestClient:
    """
    TestClient with get_db overridden to use the test session.
    This is the key FastAPI dependency-override pattern.
    """
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# User factories
# ---------------------------------------------------------------------------

def make_user(
    db: Session,
    *,
    username: str = "testuser",
    email: str = "test@example.com",
    password: str = "password123",
    role: UserRole = UserRole.member,
    is_active: bool = True,
) -> User:
    """Helper that creates and persists a User, bypassing Pydantic validation."""
    user = User(
        username=username,
        email=email,
        hashed_password=hash_password(password),
        role=role,
        is_active=is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def admin_user(db: Session) -> User:
    return make_user(db, username="admin", email="admin@example.com", role=UserRole.admin)


@pytest.fixture()
def member_user(db: Session) -> User:
    return make_user(db, username="alice", email="alice@example.com", role=UserRole.member)


@pytest.fixture()
def second_member(db: Session) -> User:
    return make_user(db, username="bob", email="bob@example.com", role=UserRole.member)


# ---------------------------------------------------------------------------
# Task factory
# ---------------------------------------------------------------------------

def make_task(
    db: Session,
    *,
    title: str = "Test Task",
    description: str | None = None,
    status: TaskStatus = TaskStatus.todo,
    priority: TaskPriority = TaskPriority.medium,
    created_by: User,
    assignee: User | None = None,
    due_date=None,
) -> Task:
    """Helper that creates and persists a Task."""
    task = Task(
        title=title,
        description=description,
        status=status,
        priority=priority,
        created_by_id=created_by.id,
        assignee_id=assignee.id if assignee else None,
        due_date=due_date,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@pytest.fixture()
def sample_task(db: Session, member_user: User) -> Task:
    return make_task(db, title="Sample Task", created_by=member_user, assignee=member_user)


# ---------------------------------------------------------------------------
# Authenticated client helpers
# ---------------------------------------------------------------------------

def login(client: TestClient, username: str, password: str = "password123") -> None:
    """POST to /login and follow redirect – sets session cookie on the client."""
    response = client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=True,
    )
    assert response.status_code == 200, f"Login failed for {username!r}"


@pytest.fixture()
def admin_client(client: TestClient, admin_user: User) -> TestClient:
    """TestClient already logged in as admin."""
    login(client, admin_user.username)
    return client


@pytest.fixture()
def member_client(client: TestClient, member_user: User) -> TestClient:
    """TestClient already logged in as member (alice)."""
    login(client, member_user.username)
    return client
