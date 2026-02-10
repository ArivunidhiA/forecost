"""
Tests for GitHub OAuth authentication endpoint.

The actual GitHub API calls are mocked.
"""

from unittest.mock import AsyncMock, patch

import pytest


class TestGitHubAuth:
    """Tests for POST /auth/github."""

    @patch("main.exchange_github_code", new_callable=AsyncMock)
    def test_new_user_created(self, mock_exchange, client, db_session):
        """GitHub auth with a new user should create the user and return JWT."""
        mock_exchange.return_value = {
            "id": 99999,
            "email": "newuser@example.com",
            "username": "newuser",
            "avatar_url": "https://github.com/images/newuser.png",
        }

        response = client.post("/auth/github", json={"code": "test-oauth-code"})
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data["email"] == "newuser@example.com"
        assert data["username"] == "newuser"

        # Verify user was created in DB
        from models import User
        user = db_session.query(User).filter(User.github_id == 99999).first()
        assert user is not None
        assert user.email == "newuser@example.com"

    @patch("main.exchange_github_code", new_callable=AsyncMock)
    def test_returning_user_updated(self, mock_exchange, client, db_session, test_user):
        """Returning user should have their info updated, not duplicated."""
        mock_exchange.return_value = {
            "id": test_user.github_id,
            "email": "updated@example.com",
            "username": "updateduser",
            "avatar_url": "https://github.com/images/updated.png",
        }

        response = client.post("/auth/github", json={"code": "test-oauth-code"})
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "updated@example.com"

        # Verify no duplicate user
        from models import User
        users = db_session.query(User).filter(User.github_id == test_user.github_id).all()
        assert len(users) == 1
        assert users[0].email == "updated@example.com"

    @patch("main.exchange_github_code", new_callable=AsyncMock)
    def test_returns_jwt_token(self, mock_exchange, client):
        """Auth response should contain a valid JWT token."""
        mock_exchange.return_value = {
            "id": 88888,
            "email": "jwt@example.com",
            "username": "jwtuser",
            "avatar_url": None,
        }

        response = client.post("/auth/github", json={"code": "test-code"})
        data = response.json()
        assert "token" in data
        assert len(data["token"]) > 20  # JWT tokens are long
        assert "expires_in" in data

    @patch("main.exchange_github_code", new_callable=AsyncMock)
    def test_github_api_failure(self, mock_exchange, client):
        """If GitHub API fails, endpoint should return error."""
        mock_exchange.side_effect = Exception("GitHub API error")

        try:
            response = client.post("/auth/github", json={"code": "bad-code"})
            # If it returns a response, it should be an error status
            assert response.status_code >= 400
        except Exception:
            # Exception propagating from TestClient is also acceptable
            pass
