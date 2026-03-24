"""
Unit tests for app/services/auth_service.py

Demonstrates:
  - Pure unit tests with no HTTP layer
  - pytest parametrize for multiple bad-credential cases
  - monkeypatch to simulate password-verify behavior
"""

import pytest

from app.services.auth_service import authenticate_user, hash_password, verify_password
from tests.conftest import make_user


# ---------------------------------------------------------------------------
# hash_password / verify_password (pure functions, no DB needed)
# ---------------------------------------------------------------------------

class TestHashPassword:
    def test_returns_different_string_than_input(self):
        # Arrange / Act
        hashed = hash_password("mysecret")
        # Assert
        assert hashed != "mysecret"

    def test_hash_is_not_empty(self):
        assert hash_password("x") != ""

    def test_same_password_produces_different_hashes(self):
        """bcrypt salts each hash, so two calls must differ."""
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2


class TestVerifyPassword:
    def test_correct_password_returns_true(self):
        hashed = hash_password("correct-horse")
        assert verify_password("correct-horse", hashed) is True

    def test_wrong_password_returns_false(self):
        hashed = hash_password("correct-horse")
        assert verify_password("wrong-horse", hashed) is False

    def test_empty_password_does_not_match_non_empty_hash(self):
        hashed = hash_password("notempty")
        assert verify_password("", hashed) is False


# ---------------------------------------------------------------------------
# authenticate_user (requires DB session)
# ---------------------------------------------------------------------------

class TestAuthenticateUser:
    def test_valid_credentials_return_user(self, db):
        # Arrange
        user = make_user(db, username="validuser", password="hunter2")
        # Act
        result = authenticate_user(db, "validuser", "hunter2")
        # Assert
        assert result is not None
        assert result.id == user.id

    def test_wrong_password_returns_none(self, db):
        make_user(db, username="validuser2", password="correct")
        result = authenticate_user(db, "validuser2", "wrong")
        assert result is None

    def test_nonexistent_user_returns_none(self, db):
        result = authenticate_user(db, "ghost", "anything")
        assert result is None

    def test_inactive_user_returns_none(self, db):
        make_user(db, username="inactive", password="pw", is_active=False)
        result = authenticate_user(db, "inactive", "pw")
        assert result is None

    @pytest.mark.parametrize("bad_password", ["", " ", "HUNTER2", "hunter2 "])
    def test_bad_passwords_all_return_none(self, db, bad_password):
        """Parametrized: many bad passwords should all fail."""
        make_user(db, username="p_user", email="pu@example.com", password="hunter2")
        result = authenticate_user(db, "p_user", bad_password)
        assert result is None

    def test_monkeypatch_verify_password(self, db, monkeypatch):
        """
        Demonstrates monkeypatching an internal dependency.
        We force verify_password to always return True to prove authenticate_user
        relies on it (and isn't doing its own verification).
        """
        make_user(db, username="mpuser", email="mp@example.com", password="real_pw")

        monkeypatch.setattr(
            "app.services.auth_service.verify_password",
            lambda plain, hashed: True,
        )

        # Even a totally wrong password now "works"
        result = authenticate_user(db, "mpuser", "totally_wrong")
        assert result is not None
        assert result.username == "mpuser"
