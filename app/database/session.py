from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.database.base import Base


def _build_sqlalchemy_url(database_url: str) -> str:
    """Normalize the configured PostgreSQL URL for the installed psycopg driver."""
    normalized_url = database_url.strip()
    if normalized_url.startswith("postgresql://"):
        return normalized_url.replace("postgresql://", "postgresql+psycopg://", 1)
    if normalized_url.startswith("postgres://"):
        return normalized_url.replace("postgres://", "postgresql+psycopg://", 1)
    return normalized_url


# Create a reusable SQLAlchemy engine bound to the configured PostgreSQL URL.
database_url = _build_sqlalchemy_url(settings.database_url)
engine = create_engine(database_url, pool_pre_ping=True)

# Create a session factory used by FastAPI dependencies and service layers.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Yield a database session for request-scoped use in FastAPI dependencies."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


__all__ = ["Base", "SessionLocal", "engine", "get_db"]
