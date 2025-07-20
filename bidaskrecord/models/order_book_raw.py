"""Raw order book data storage for duplicate detection."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import BaseModel


class OrderBookRaw(BaseModel):
    """Raw order book data for duplicate detection and auditing.

    This table stores the complete raw JSON message from the exchange
    for each unique order book snapshot, enabling efficient duplicate
    detection without storing redundant data in the main order_book table.
    """

    __tablename__ = "order_book_raw"

    # Asset reference
    asset_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("asset.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Timestamp when this raw data was received
    received_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        doc="Timestamp when this order book data was received",
    )

    # Complete raw JSON message from exchange
    raw_data: Mapped[Dict[str, Any]] = mapped_column(
        JSON, nullable=False, doc="Complete raw message data from the exchange"
    )

    # Relationships
    asset: Mapped["Asset"] = relationship("Asset", lazy="selectin")

    # Indexes for efficient queries
    __table_args__ = (
        # Query by asset and time
        Index("idx_order_book_raw_asset_time", "asset_id", "received_at"),
        # Most recent query
        Index("idx_order_book_raw_asset_recent", "asset_id", "received_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<OrderBookRaw(asset_id={self.asset_id}, "
            f"received_at={self.received_at})>"
        )

    @classmethod
    def is_duplicate(cls, db, asset_id: int, current_data: Dict[str, Any]) -> bool:
        """
        Check if the current order book data is identical to the most recent one.

        Args:
            db: Database session
            asset_id: Asset ID
            current_data: Raw JSON data from exchange

        Returns:
            True if this order book is identical to the last one, False otherwise
        """
        # Get the most recent raw data for this asset
        last_raw = (
            db.query(cls.raw_data)
            .filter(cls.asset_id == asset_id)
            .order_by(cls.received_at.desc())
            .first()
        )

        if not last_raw:
            # No previous data, this is not a duplicate
            return False

        last_data = last_raw[0]

        # Compare the bids and asks arrays directly
        current_bids = current_data.get("bids", [])
        current_asks = current_data.get("asks", [])
        last_bids = last_data.get("bids", [])
        last_asks = last_data.get("asks", [])

        # Simple comparison: if bids and asks are identical, it's a duplicate
        return current_bids == last_bids and current_asks == last_asks

    @classmethod
    def create_if_changed(
        cls, db, asset_id: int, received_at: datetime, raw_data: Dict[str, Any]
    ) -> tuple[bool, "OrderBookRaw | None"]:
        """
        Create a new raw order book entry only if the data has changed.

        Args:
            db: Database session
            asset_id: Asset ID
            received_at: Timestamp when data was received
            raw_data: Raw JSON data from exchange

        Returns:
            Tuple of (is_new_data, raw_entry_or_none)
        """
        if cls.is_duplicate(db, asset_id, raw_data):
            return False, None

        # Data has changed, create new entry
        new_entry = cls(
            asset_id=asset_id,
            received_at=received_at,
            raw_data=raw_data.copy(),
        )
        db.add(new_entry)
        return True, new_entry
