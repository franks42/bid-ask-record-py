"""Base database models and session management with SQLAlchemy 2.0+."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Generator, Type, TypeVar, cast

from sqlalchemy import (
    Column,
    DateTime,
    Engine,
    Integer,
    create_engine,
    event,
    inspect,
    text,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    declarative_base,
    mapped_column,
    sessionmaker,
)
from sqlalchemy.pool import StaticPool
from typing_extensions import Self

from bidaskrecord.config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Type variables for generic type hints
T = TypeVar("T", bound="BaseModel")


# Create SQLAlchemy engine with appropriate configuration
def create_db_engine() -> Engine:
    """Create and configure the SQLAlchemy engine."""
    connect_args = {}
    if settings.DATABASE_URL.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    return create_engine(
        settings.DATABASE_URL,
        connect_args=connect_args,
        poolclass=StaticPool if settings.DATABASE_URL.startswith("sqlite") else None,
        echo=settings.SQL_ECHO,
        future=True,
    )


engine = create_db_engine()

# Session factory with proper typing
SessionFactory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

# Type for database session
db_session_type = Session


def get_db() -> Generator[db_session_type, None, None]:
    """Dependency to get a database session.

    Yields:
        SQLAlchemy session
    """
    db = SessionFactory()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db_context():
    """Get a database session context manager for proper transaction handling."""
    return SessionFactory()


class BaseModel(DeclarativeBase):
    """Base model with common columns and methods using SQLAlchemy 2.0 style.

    This serves as the base class for all SQLAlchemy models in the application.
    """

    # This tells SQLAlchemy not to create a table for this class
    __abstract__ = True

    # Common columns with proper type annotations
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    @classmethod
    @property
    def __tablename__(cls) -> str:
        """Generate __tablename__ automatically from class name.

        Converts CamelCase class names to snake_case table names.
        """
        return "".join(
            ["_" + c.lower() if c.isupper() else c for c in cls.__name__]
        ).lstrip("_")

    def update(self, **kwargs: Any) -> None:
        """Update model attributes.

        Args:
            **kwargs: Attributes to update with their new values
        """
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def to_dict(self) -> dict[str, Any]:
        """Convert model to dictionary.

        Returns:
            Dictionary representation of the model
        """
        result = {}
        for column in self.__table__.columns:
            result[column.name] = getattr(self, column.name)
        return result

    @classmethod
    def get_primary_key_columns(cls) -> list[str]:
        """Get the names of primary key columns.

        Returns:
            List of primary key column names
        """
        return [column.name for column in inspect(cls).primary_key]

    @classmethod
    def get_columns(cls) -> list[str]:
        """Get all column names for the model.

        Returns:
            List of column names
        """
        return [column.name for column in inspect(cls).columns]


def init_db() -> None:
    """Initialize the database by creating all tables.

    This should be called once at application startup.
    """
    logger.info("Initializing database...")
    BaseModel.metadata.create_all(bind=engine)
    logger.info("Database initialization complete")


# Add event listeners for SQLite to enforce foreign key constraints
if settings.DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection: Any, _: Any) -> None:
        """Enable foreign key constraints in SQLite."""
        if dbapi_connection:
            dbapi_connection.execute("PRAGMA foreign_keys=ON")
            dbapi_connection.commit()
