"""Database initialization and session management."""

from typing import Generator

from sqlalchemy.orm import Session

from .models.base import Session
from .models.base import get_db as _get_db
from .models.base import init_db

# Re-export for convenience
__all__ = ["Session", "init_db", "get_db"]


def get_db() -> Generator[Session, None, None]:
    """
    Get a database session.

    Yields:
        Session: A database session.

    Example:
        >>> with get_db() as db:
        ...     # Use the database session
        ...     result = db.query(MyModel).all()
    """
    db = next(_get_db())
    try:
        yield db
    finally:
        db.close()
