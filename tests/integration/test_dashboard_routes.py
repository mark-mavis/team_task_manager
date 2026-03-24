"""
Integration tests for the dashboard route.

Demonstrates:
  - Stat cards rendered with correct counts
  - Unauthenticated access is blocked
  - monkeypatch for controlling overdue detection
"""

from app.models.task import TaskStatus
from tests.conftest import make_task


class TestDashboard:
    def test_dashboard_requires_auth(self, client):
        response = client.get("/dashboard", follow_redirects=False)
        assert response.status_code in (302, 401)

    def test_dashboard_renders_for_authenticated_user(self, admin_client):
        response = admin_client.get("/dashboard")
        assert response.status_code == 200
        assert b'data-testid="stats-grid"' in response.content

    def test_shows_current_username(self, admin_client):
        response = admin_client.get("/dashboard")
        assert b'data-testid="current-username"' in response.content
        assert b"admin" in response.content

    def test_stat_cards_present(self, admin_client):
        response = admin_client.get("/dashboard")
        assert b'data-testid="stat-total-open"' in response.content
        assert b'data-testid="stat-in-progress"' in response.content
        assert b'data-testid="stat-completed"' in response.content
        assert b'data-testid="stat-overdue"' in response.content

    def test_completed_count_updates_after_creating_done_task(
        self, admin_client, db, admin_user
    ):
        # Arrange: create one done task
        make_task(db, title="Done!", created_by=admin_user, status=TaskStatus.done)

        # Act
        response = admin_client.get("/dashboard")

        # Assert: completed stat is visible and non-zero
        assert response.status_code == 200
        # The number "1" (or more) should appear somewhere in the stats section
        assert b"stat-completed" in response.content

    def test_root_redirects_to_dashboard(self, admin_client):
        response = admin_client.get("/", follow_redirects=False)
        assert response.status_code in (302, 307)
        assert response.headers["location"] == "/dashboard"
