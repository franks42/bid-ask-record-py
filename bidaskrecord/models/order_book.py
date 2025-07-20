"""Unified order book model with all market data information."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import BaseModel


class OrderBook(BaseModel):
    """Unified order book model containing all order book information.

    This table replaces the fragmented OrderBookSnapshot, OrderBookLevel, and BidAsk tables
    with a single comprehensive table that contains all necessary information.
    """

    __tablename__ = "order_book"

    # Asset reference
    asset_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("asset.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Snapshot/message identification
    snapshot_id: Mapped[int] = mapped_column(
        Integer, nullable=False, doc="Sequence number for this order book snapshot"
    )
    channel_uuid: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, doc="Channel UUID from the exchange"
    )

    # Timestamp
    received_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        doc="Timestamp when this data was received (consistent for all levels in same message)",
    )

    # Order book level details
    side: Mapped[str] = mapped_column(
        String(4), nullable=False, doc="Side: 'bid' or 'ask'"
    )
    level_rank: Mapped[int] = mapped_column(
        Integer, nullable=False, doc="Rank of this level (1=best, 2=second best, etc.)"
    )

    # Price information (base units - microUSD)
    price_amount: Mapped[int] = mapped_column(
        Numeric(36, 0), nullable=False, doc="Price in microUSD (base denomination)"
    )

    # Quantity information (base units - nanoHASH)
    quantity_amount: Mapped[int] = mapped_column(
        Numeric(36, 0),
        nullable=False,
        doc="Quantity at this price level in nanoHASH (base denomination)",
    )
    cumulative_amount: Mapped[Optional[int]] = mapped_column(
        Numeric(36, 0),
        nullable=True,
        doc="Cumulative quantity from best price to this level in nanoHASH (running total)",
    )

    # Cost/notional calculations (base units - microUSD)
    level_cost_amount: Mapped[int] = mapped_column(
        Numeric(36, 0),
        nullable=False,
        doc="Cost to buy/sell the quantity at this level (price × quantity) in microUSD",
    )
    cumulative_cost_amount: Mapped[Optional[int]] = mapped_column(
        Numeric(36, 0),
        nullable=True,
        doc="Cumulative cost from best price to this level in microUSD",
    )

    # Display values (calculated for easy querying)
    price_display: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), nullable=False, doc="Price in display denomination (e.g., USD)"
    )
    quantity_display: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        doc="Quantity in display denomination (e.g., HASH)",
    )
    cumulative_display: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 8), nullable=True, doc="Cumulative quantity in display denomination"
    )
    level_cost_display: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        doc="Cost to buy/sell this level in display price denomination",
    )
    cumulative_cost_display: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 8),
        nullable=True,
        doc="Cumulative cost in display price denomination",
    )

    # Denomination information (for reference)
    price_denom: Mapped[str] = mapped_column(
        String(10), nullable=False, doc="Price denomination (e.g., USD)"
    )
    quantity_denom: Mapped[str] = mapped_column(
        String(10), nullable=False, doc="Quantity denomination (e.g., HASH)"
    )

    # Additional order book metadata
    total_orders: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        doc="Number of orders at this price level (if provided by exchange)",
    )

    # Raw data for auditing
    raw_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True, doc="Raw message data from the exchange"
    )

    # Relationships
    asset: Mapped["Asset"] = relationship("Asset", lazy="selectin")

    # Indexes and constraints
    __table_args__ = (
        # Primary composite index for querying
        Index(
            "idx_order_book_asset_snapshot_side_rank",
            "asset_id",
            "snapshot_id",
            "side",
            "level_rank",
        ),
        # Time-based queries
        Index("idx_order_book_asset_time", "asset_id", "received_at"),
        Index("idx_order_book_received_time", "received_at"),
        # Order book structure queries
        Index("idx_order_book_snapshot_side", "snapshot_id", "side"),
        Index("idx_order_book_side_price", "side", "price_amount"),
        # Ensure valid sides
        CheckConstraint("side IN ('bid', 'ask')", name="chk_side_valid"),
        # Ensure positive amounts
        CheckConstraint("price_amount >= 0", name="chk_price_non_negative"),
        CheckConstraint("quantity_amount >= 0", name="chk_quantity_non_negative"),
        CheckConstraint("level_cost_amount >= 0", name="chk_level_cost_non_negative"),
        CheckConstraint("level_rank > 0", name="chk_level_rank_positive"),
        # Ensure logical ordering for cumulative amounts
        CheckConstraint(
            "cumulative_amount IS NULL OR cumulative_amount >= quantity_amount",
            name="chk_cumulative_amount_logical",
        ),
        CheckConstraint(
            "cumulative_cost_amount IS NULL OR cumulative_cost_amount >= level_cost_amount",
            name="chk_cumulative_cost_logical",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<OrderBook(asset_id={self.asset_id}, snapshot={self.snapshot_id}, "
            f"side='{self.side}', rank={self.level_rank}, "
            f"price={self.price_display}, qty={self.quantity_display})>"
        )

    def to_dict(self, include_raw: bool = False) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        result = {
            "id": self.id,
            "asset_id": self.asset_id,
            "snapshot_id": self.snapshot_id,
            "channel_uuid": self.channel_uuid,
            "received_at": self.received_at.isoformat(),
            "side": self.side,
            "level_rank": self.level_rank,
            "price": {
                "amount": self.price_amount,
                "display": float(self.price_display),
                "denom": self.price_denom,
            },
            "quantity": {
                "amount": self.quantity_amount,
                "display": float(self.quantity_display),
                "cumulative_amount": self.cumulative_amount,
                "cumulative_display": float(self.cumulative_display)
                if self.cumulative_display
                else None,
                "denom": self.quantity_denom,
            },
            "cost": {
                "level_amount": self.level_cost_amount,
                "level_display": float(self.level_cost_display),
                "cumulative_amount": self.cumulative_cost_amount,
                "cumulative_display": float(self.cumulative_cost_display)
                if self.cumulative_cost_display
                else None,
                "denom": self.price_denom,
            },
            "total_orders": self.total_orders,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

        if include_raw:
            result["raw_data"] = self.raw_data

        return result

    @classmethod
    def from_exchange_data(
        cls,
        asset: "Asset",
        snapshot_id: int,
        channel_uuid: str,
        received_at: datetime,
        side: str,
        level_rank: int,
        price: str | float | Decimal,
        quantity: str | float | Decimal,
        cumulative_quantity: Optional[str | float | Decimal] = None,
        total_orders: Optional[int] = None,
        raw_data: Optional[Dict[str, Any]] = None,
    ) -> "OrderBook":
        """Create OrderBook entry from exchange data with all calculations."""

        # Convert to base units
        price_amount = asset.to_base_price(price)
        quantity_amount = asset.to_base_size(quantity)
        cumulative_amount = (
            asset.to_base_size(cumulative_quantity) if cumulative_quantity else None
        )

        # Calculate costs in microUSD (price × quantity in base units)
        level_cost_amount = price_amount * quantity_amount // asset.size_denom_factor
        cumulative_cost_amount = (
            price_amount * cumulative_amount // asset.size_denom_factor
            if cumulative_amount
            else None
        )

        # Calculate display values with proper precision
        price_display = Decimal(str(price)).quantize(
            Decimal("0.001")
        )  # 3 decimal places
        quantity_display = Decimal(str(quantity)).quantize(Decimal("1"))  # Whole tokens
        cumulative_display = (
            Decimal(str(cumulative_quantity)).quantize(Decimal("1"))
            if cumulative_quantity
            else None
        )  # Whole tokens
        level_cost_display = (price_display * quantity_display).quantize(
            Decimal("1")
        )  # Whole USD (no decimals)
        cumulative_cost_display = (
            (price_display * cumulative_display).quantize(Decimal("1"))
            if cumulative_display
            else None
        )  # Whole USD (no decimals)

        return cls(
            asset_id=asset.id,
            snapshot_id=snapshot_id,
            channel_uuid=channel_uuid,
            received_at=received_at,
            side=side,
            level_rank=level_rank,
            price_amount=price_amount,
            quantity_amount=quantity_amount,
            cumulative_amount=cumulative_amount,
            level_cost_amount=level_cost_amount,
            cumulative_cost_amount=cumulative_cost_amount,
            price_display=price_display,
            quantity_display=quantity_display,
            cumulative_display=cumulative_display,
            level_cost_display=level_cost_display,
            cumulative_cost_display=cumulative_cost_display,
            price_denom=asset.display_price_denom,
            quantity_denom=asset.display_size_denom,
            total_orders=total_orders,
            raw_data=raw_data,
        )
