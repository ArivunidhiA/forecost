"""
Database connection and session management.

Uses SQLAlchemy with PostgreSQL in production and SQLite for tests.
Alembic manages schema migrations for non-test environments.
"""

import logging
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker, declarative_base

from config import get_settings

logger = logging.getLogger(__name__)

# Create base class for models
Base = declarative_base()


def get_engine():
    """
    Create database engine with connection pooling.

    Returns:
        Engine: SQLAlchemy engine instance.
    """
    settings = get_settings()
    url = settings.database_url

    # SQLite doesn't support pool_size/max_overflow/pool_timeout
    if url.startswith("sqlite"):
        return create_engine(
            url,
            connect_args={"check_same_thread": False},
            echo=not settings.is_production,
        )

    return create_engine(
        url,
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,
        echo=not settings.is_production,
    )


# Create engine and session factory
engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """
    Initialize database schema.

    In test environments, uses create_all() for speed.
    In production/development, runs Alembic migrations.
    """
    settings = get_settings()

    if settings.environment == "test":
        # Tests use SQLite in-memory — just create tables directly
        Base.metadata.create_all(bind=engine)
        return

    try:
        from alembic import command
        from alembic.config import Config

        import os

        alembic_cfg = Config(os.path.join(os.path.dirname(__file__), "alembic.ini"))
        alembic_cfg.set_main_option(
            "script_location", os.path.join(os.path.dirname(__file__), "migrations")
        )
        alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)

        command.upgrade(alembic_cfg, "head")
        logger.info("Database migrations applied successfully")
    except Exception as e:
        logger.warning(f"Alembic migration failed, falling back to create_all: {e}")
        Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """
    Get database session dependency.

    Yields:
        Session: Database session that auto-closes.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
