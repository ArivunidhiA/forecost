"""
Authentication module for JWT token generation and validation.

Handles GitHub OAuth flow and JWT-based session management.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from config import get_settings
from database import get_db
from models import User

logger = logging.getLogger(__name__)

# Security scheme for JWT bearer tokens
security = HTTPBearer()


def create_access_token(user_id: str) -> tuple[str, int]:
    """
    Create a JWT access token for a user.

    Args:
        user_id: User's unique identifier.

    Returns:
        tuple: (token_string, expiry_seconds)

    Example:
        >>> token, expires_in = create_access_token("user-123")
    """
    settings = get_settings()
    expires_delta = timedelta(hours=settings.jwt_expiry_hours)
    expire = datetime.now(timezone.utc) + expires_delta

    payload = {
        "sub": user_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }

    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    expires_in = int(expires_delta.total_seconds())

    return token, expires_in


def verify_access_token(token: str) -> Optional[str]:
    """
    Verify and decode a JWT access token.

    Args:
        token: JWT token string.

    Returns:
        Optional[str]: User ID if valid, None otherwise.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        user_id: str = payload.get("sub")
        token_type: str = payload.get("type")

        if user_id is None or token_type != "access":
            return None

        return user_id
    except JWTError:
        return None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """
    FastAPI dependency to get the current authenticated user.

    Args:
        credentials: Bearer token from Authorization header.
        db: Database session.

    Returns:
        User: Authenticated user object.

    Raises:
        HTTPException: 401 if token is invalid or user not found.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    user_id = verify_access_token(credentials.credentials)
    if user_id is None:
        raise credentials_exception

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )

    return user


async def exchange_github_code(code: str) -> dict:
    """
    Exchange GitHub OAuth code for access token and user info.

    Args:
        code: Authorization code from GitHub OAuth callback.

    Returns:
        dict: GitHub user info including id, email, username, avatar_url.

    Raises:
        HTTPException: If exchange fails due to network, parsing, or key errors.
    """
    settings = get_settings()

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Exchange code for access token
            token_response = await client.post(
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                data={
                    "client_id": settings.github_client_id,
                    "client_secret": settings.github_client_secret,
                    "code": code,
                },
            )

            if token_response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to exchange GitHub code",
                )

            token_data = token_response.json()
            access_token = token_data.get("access_token")

            if not access_token:
                error = token_data.get("error_description", "Unknown error")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"GitHub OAuth error: {error}",
                )

            # Get user info
            user_response = await client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github.v3+json",
                },
            )

            if user_response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to get GitHub user info",
                )

            user_data = user_response.json()

            # Get user email (might be private)
            email = user_data.get("email")
            if not email:
                email_response = await client.get(
                    "https://api.github.com/user/emails",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/vnd.github.v3+json",
                    },
                )
                if email_response.status_code == 200:
                    emails = email_response.json()
                    primary = next((e for e in emails if e.get("primary")), None)
                    email = primary["email"] if primary else emails[0]["email"] if emails else None

            return {
                "id": user_data["id"],
                "email": email or f"{user_data['login']}@github.local",
                "username": user_data.get("login"),
                "avatar_url": user_data.get("avatar_url"),
            }

    except HTTPException:
        raise  # Re-raise FastAPI HTTP exceptions as-is
    except httpx.HTTPError as e:
        logger.error(f"GitHub OAuth network error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to communicate with GitHub. Please try again.",
        )
    except (KeyError, TypeError) as e:
        logger.error(f"GitHub OAuth response parsing error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unexpected response from GitHub. Please try again.",
        )
    except Exception as e:
        logger.error(f"GitHub OAuth unexpected error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication failed due to an internal error.",
        )
