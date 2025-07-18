"""Base database models and session management."""

from datetime import datetime
from typing import Any, TypeVar

from sqlalchemy import create_engine, Column, Integer, DateTime, String, Float, ForeignKey, event
from sqlalchemy.ext.declarative import declarative_base, declared_attr
from sqlalchemy.orm import sessionmaker, scoped_session, Session as SessionType
from sqlalchemy.pool import StaticPool

from bidaskrecord.config.settings import get_settings

settings = get_settings()

# Create SQLAlchemy engine
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
    poolclass=StaticPool if settings.database_url.startswith("sqlite") else None,
    echo=settings.sql_echo,
)

# Create session factory
SessionFactory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Session = scoped_session(SessionFactory)

# Base class for all models
Base = declarative_base()

# Type variable for model classes
ModelType = TypeVar("ModelType", bound=Base)

def get_db() -> SessionType:
    """Get a database session."""
    db = Session()
    try:
        yield db
    finally:
        db.close()

class BaseModel(Base):
    """Base model with common columns and methods."""
    __abstract__ = True

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    @declared_attr
    def __tablename__(cls) -> str:
        ""
        Generate __tablename__ automatically.
        Convert CamelCase class name to snake_case table name.
        """
        return "".join(["_" + i.lower() if i.isupper() else i for i in cls.__name__]).lstrip("_")

    def update(self, **kwargs: Any) -> None:
        """Update model attributes."""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def to_dict(self) -> dict[str, Any]:
        """Convert model to dictionary."""
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

def init_db() -> None:
    ""
    Initialize the database by creating all tables.
    This should be called once at application startup.
    """
    Base.metadata.create_all(bind=engine)

# Add event listeners for SQLite to enforce foreign key constraints
if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection: Any, _: Any) -> None:
        """Enable foreign key constraints in SQLite."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
