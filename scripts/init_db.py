"""Initialize a fresh database with all tables."""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine

from bidaskrecord.models.base import BaseModel, create_db_engine
from bidaskrecord.models.market_data import Asset, BidAsk, DenomReference, Trade


def init_db():
    """Initialize the database by creating all tables."""
    # Remove existing database if it exists
    db_path = "market_data.db"
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"Removed existing database at {db_path}")

    # Create engine and tables
    engine = create_db_engine()
    BaseModel.metadata.create_all(bind=engine)
    print(f"Created new database at {db_path}")
    print("Tables created:")
    for table in BaseModel.metadata.tables:
        print(f"- {table}")


if __name__ == "__main__":
    init_db()
