"""
Integration tests for authentication routes (/login, /logout).

Demonstrates:
  - Full HTTP round-trip via FastAPI TestClient
  - Session cookie is set / cleared
  - Redirect behaviour after login/logout
  - Parametrized bad-credential cases
"""

import pytest

from tests.conftest import make_user


class TestLoginPage:
    def test_get_returns_login_form(self, client):
        # Arrange / Act
        response = client.get("/login", follow_redirects=False)
        # Assert
        assert response.status_code == 200
        assert b"Sign in" in response.content

    def test_already_authenticated_redirects_to_dashboard(self, client, member_user):
        # Log in first
        client.post("/login", data={"username": "alice", "password": "password123"})
        # Visiting /login again should redirect
        response = client.get("/login", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/dashboard"


class TestLoginSubmit:
    def test_valid_login_redirects_to_dashboard(self, client, member_user):
        response = client.post(
            "/login",
            data={"username": "alice", "password": "password123"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/dashboard"

    def test_valid_login_sets_session(self, client, member_user):
        client.post(
            "/login",
            data={"username": "alice", "password": "password123"},
            follow_redirects=True,
        )
        # After login the dashboard should be reachable without re-login
        response = client.get("/dashboard")
        assert response.status_code == 200

    def test_wrong_password_returns_401(self, client, member_user):
        response = client.post(
            "/login",
            data={"username": "alice", "password": "wrong"},
            follow_redirects=False,
        )
        assert response.status_code == 401
        assert b"Invalid username or password" in response.content

    def test_error_message_shown_in_html(self, client, member_user):
        response = client.post(
            "/login",
            data={"username": "alice", "password": "bad"},
            follow_redirects=False,
        )
        assert b'data-testid="login-error"' in response.content

    @pytest.mark.parametrize("username,password", [
        ("alice", ""),
        ("", "password123"),
        ("ghost", "password123"),
        ("alice", "PASSWORD123"),    # case-sensitive
        ("alice", "password123 "),   # trailing space
    ])
    def test_bad_credentials_fail(self, client, member_user, username, password):
        response = client.post(
            "/login",
            data={"username": username, "password": password},
            follow_redirects=False,
        )
        assert response.status_code in (401, 422)


class TestLogout:
    def test_logout_clears_session(self, client, member_user):
        # Arrange: log in
        client.post(
            "/login",
            data={"username": "alice", "password": "password123"},
            follow_redirects=True,
        )
        # Act: log out
        client.post("/logout", follow_redirects=True)
        # Assert: protected route now redirects to login
        response = client.get("/dashboard", follow_redirects=False)
        assert response.status_code in (302, 401)

    def test_logout_redirects_to_login(self, client, member_user):
        client.post("/login", data={"username": "alice", "password": "password123"})
        response = client.post("/logout", follow_redirects=False)
        assert response.status_code == 302
        assert "/login" in response.headers["location"]


class TestProtectedRoutes:
    @pytest.mark.parametrize("path", ["/dashboard", "/tasks", "/tasks/new"])
    def test_unauthenticated_access_is_rejected(self, client, path):
        """Any protected page should reject unauthenticated requests."""
        response = client.get(path, follow_redirects=False)
        assert response.status_code in (302, 401)
