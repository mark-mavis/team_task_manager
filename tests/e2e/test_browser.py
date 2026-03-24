"""
End-to-end browser tests using Playwright for Python.

These tests:
  - Spin up the real FastAPI app on a local port via pytest-anyio + uvicorn
  - Drive a real Chromium browser through user flows
  - Verify the full stack: routing → templates → CSS → interactivity

Prerequisites:
  python -m playwright install chromium

Run with:
  python -m pytest tests/e2e/ -v
"""

import threading
import time

import pytest
import uvicorn
from playwright.sync_api import Page, expect

from app.main import app as fastapi_app
from app.db import Base, get_db, engine as app_engine
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from tests.conftest import make_user, make_task
from app.models.user import UserRole

# ---------------------------------------------------------------------------
# Spin up a live server for Playwright
# ---------------------------------------------------------------------------

E2E_DB_URL = "sqlite:///./e2e_test.db"
E2E_PORT = 8787


@pytest.fixture(scope="module")
def e2e_db_engine():
    """Separate SQLite file DB for E2E tests (Playwright can't share in-memory DB)."""
    _engine = create_engine(E2E_DB_URL, connect_args={"check_same_thread": False})
    Base.metadata.drop_all(bind=_engine)
    Base.metadata.create_all(bind=_engine)
    yield _engine
    Base.metadata.drop_all(bind=_engine)


@pytest.fixture(scope="module")
def e2e_session(e2e_db_engine):
    E2ESession = sessionmaker(bind=e2e_db_engine)
    session = E2ESession()
    yield session
    session.close()


@pytest.fixture(scope="module")
def live_server(e2e_db_engine, e2e_session):
    """
    Start the FastAPI app in a background thread.
    Override get_db to use the e2e database.
    """
    E2ESession = sessionmaker(bind=e2e_db_engine)

    def override_get_db():
        db = E2ESession()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_db] = override_get_db

    config = uvicorn.Config(fastapi_app, host="127.0.0.1", port=E2E_PORT, log_level="error")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait for server to be ready
    for _ in range(20):
        time.sleep(0.3)
        if server.started:
            break

    yield f"http://127.0.0.1:{E2E_PORT}"

    server.should_exit = True
    fastapi_app.dependency_overrides.clear()


@pytest.fixture(scope="module")
def seeded_users(e2e_session):
    """Seed demo users once for the whole E2E module."""
    admin = make_user(
        e2e_session, username="admin", email="admin@e2e.com", role=UserRole.admin
    )
    member = make_user(
        e2e_session, username="alice", email="alice@e2e.com", role=UserRole.member
    )
    return {"admin": admin, "alice": member}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def do_login(page: Page, base_url: str, username: str, password: str = "password123") -> None:
    page.goto(f"{base_url}/login")
    page.get_by_test_id("input-username").fill(username)
    page.get_by_test_id("input-password").fill(password)
    page.get_by_test_id("btn-login").click()
    page.wait_for_url(f"{base_url}/dashboard")


# ---------------------------------------------------------------------------
# Login / logout flow
# ---------------------------------------------------------------------------

class TestLoginFlow:
    def test_login_page_has_form(self, live_server, page: Page):
        page.goto(f"{live_server}/login")
        expect(page.get_by_test_id("login-form")).to_be_visible()
        expect(page.get_by_test_id("input-username")).to_be_visible()
        expect(page.get_by_test_id("input-password")).to_be_visible()

    def test_valid_login_reaches_dashboard(self, live_server, seeded_users, page: Page):
        do_login(page, live_server, "admin")
        expect(page).to_have_url(f"{live_server}/dashboard")

    def test_invalid_login_shows_error(self, live_server, seeded_users, page: Page):
        page.goto(f"{live_server}/login")
        page.get_by_test_id("input-username").fill("admin")
        page.get_by_test_id("input-password").fill("wrongpassword")
        page.get_by_test_id("btn-login").click()
        expect(page.get_by_test_id("login-error")).to_be_visible()

    def test_logout_returns_to_login(self, live_server, seeded_users, page: Page):
        do_login(page, live_server, "admin")
        page.get_by_test_id("logout-btn").click()
        expect(page).to_have_url(f"{live_server}/login")


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class TestDashboardE2E:
    def test_stat_cards_visible(self, live_server, seeded_users, page: Page):
        do_login(page, live_server, "admin")
        expect(page.get_by_test_id("stats-grid")).to_be_visible()
        expect(page.get_by_test_id("stat-total-open")).to_be_visible()
        expect(page.get_by_test_id("stat-completed")).to_be_visible()
        expect(page.get_by_test_id("stat-overdue")).to_be_visible()

    def test_username_shown_in_header(self, live_server, seeded_users, page: Page):
        do_login(page, live_server, "alice")
        expect(page.get_by_test_id("current-username")).to_have_text("alice")


# ---------------------------------------------------------------------------
# Task CRUD flow
# ---------------------------------------------------------------------------

class TestTaskCRUDE2E:
    def test_create_task_full_flow(self, live_server, seeded_users, page: Page):
        do_login(page, live_server, "admin")
        page.get_by_test_id("btn-new-task").first.click()

        # Fill in the form
        page.get_by_test_id("input-title").fill("E2E Browser Task")
        page.get_by_test_id("select-priority").select_option("high")
        page.get_by_test_id("btn-submit-task").click()

        # Should redirect to task list and show the new task
        expect(page).to_have_url(f"{live_server}/tasks")
        expect(page.get_by_text("E2E Browser Task")).to_be_visible()

    def test_task_detail_accessible(self, live_server, seeded_users, e2e_session, page: Page):
        admin = seeded_users["admin"]
        task = make_task(e2e_session, title="Detail E2E Task", created_by=admin)

        do_login(page, live_server, "admin")
        page.goto(f"{live_server}/tasks/{task.id}")
        expect(page.get_by_test_id("task-detail-title")).to_have_text("Detail E2E Task")

    def test_filter_by_status(self, live_server, seeded_users, e2e_session, page: Page):
        from app.models.task import TaskStatus
        admin = seeded_users["admin"]
        make_task(e2e_session, title="Filtered Todo", created_by=admin, status=TaskStatus.todo)
        make_task(e2e_session, title="Filtered Done", created_by=admin, status=TaskStatus.done)

        do_login(page, live_server, "admin")
        page.goto(f"{live_server}/tasks?status_filter=todo")
        expect(page.get_by_text("Filtered Todo")).to_be_visible()
        expect(page.get_by_text("Filtered Done")).not_to_be_visible()

    def test_admin_delete_button_visible(self, live_server, seeded_users, e2e_session, page: Page):
        admin = seeded_users["admin"]
        task = make_task(e2e_session, title="Delete Button Task", created_by=admin)

        do_login(page, live_server, "admin")
        page.goto(f"{live_server}/tasks/{task.id}")
        expect(page.get_by_test_id("btn-delete-task")).to_be_visible()

    def test_member_has_no_delete_button(self, live_server, seeded_users, e2e_session, page: Page):
        admin = seeded_users["admin"]
        alice = seeded_users["alice"]
        task = make_task(e2e_session, title="No Delete Task", created_by=admin, assignee=alice)

        do_login(page, live_server, "alice")
        page.goto(f"{live_server}/tasks/{task.id}")
        expect(page.get_by_test_id("btn-delete-task")).not_to_be_visible()
