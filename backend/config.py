"""
Configuration management for LLMLab backend.

Loads settings from environment variables with validation.
"""

import base64
from functools import lru_cache
from typing import List, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str

    # Security
    jwt_secret: str
    encryption_key: str
    jwt_expiry_hours: int = 24

    # GitHub OAuth
    github_client_id: str
    github_client_secret: str
    github_redirect_uri: str = "http://localhost:8000/auth/github/callback"

    # CORS
    cors_origins: str = "http://localhost:3000"

    # Rate Limiting
    rate_limit_per_minute: int = 100

    # Cache
    redis_url: Optional[str] = None

    # Environment
    environment: str = "development"

    @field_validator('jwt_secret')
    @classmethod
    def jwt_secret_min_length(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError('jwt_secret must be at least 32 characters long')
        return v

    @field_validator('encryption_key')
    @classmethod
    def encryption_key_valid_base64(cls, v: str) -> str:
        try:
            decoded = base64.urlsafe_b64decode(v)
            if len(decoded) != 32:
                raise ValueError
        except Exception:
            raise ValueError(
                'encryption_key must be a valid 44-character base64-encoded Fernet key'
            )
        return v

    @field_validator('environment')
    @classmethod
    def environment_must_be_valid(cls, v: str) -> str:
        allowed = {'development', 'test', 'production'}
        if v.lower() not in allowed:
            raise ValueError(f'environment must be one of: {", ".join(sorted(allowed))}')
        return v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins.split(",")]

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment.lower() == "production"


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Returns:
        Settings: Application settings singleton.
    """
    return Settings()
