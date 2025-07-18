"""Market data models for bid/ask data."""

from typing import Optional
from decimal import Decimal
from sqlalchemy import Column, String, Numeric, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .base import BaseModel, Base

class Asset(BaseModel):
    """Asset model representing a tradable asset."""
    
    symbol = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=True)
    
    # Relationships
    bid_ask_data = relationship("BidAskData", back_populates="asset", cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return f"<Asset(symbol='{self.symbol}', name='{self.name}')>"

class BidAskData(BaseModel):
    """Bid/Ask data model for storing market data."""
    
    asset_id = Column(Integer, ForeignKey('asset.id', ondelete='CASCADE'), nullable=False, index=True)
    exchange_timestamp = Column(Numeric(20, 6), nullable=False)
    bid_price = Column(Numeric(36, 18), nullable=False)
    ask_price = Column(Numeric(36, 18), nullable=False)
    bid_size = Column(Numeric(36, 18), nullable=False)
    ask_size = Column(Numeric(36, 18), nullable=False)
    
    # Store the raw message for debugging and future processing
    raw_data = Column(JSONB, nullable=True)
    
    # Relationships
    asset = relationship("Asset", back_populates="bid_ask_data")
    
    # Indexes
    __table_args__ = (
        Index('idx_bid_ask_data_asset_timestamp', 'asset_id', 'exchange_timestamp'),
        Index('idx_bid_ask_data_timestamp', 'exchange_timestamp'),
    )
    
    def __repr__(self) -> str:
        return (
            f"<BidAskData(asset_id={self.asset_id}, "
            f"timestamp={self.exchange_timestamp}, "
            f"bid={self.bid_price}, ask={self.ask_price})>"
        )
    
    @property
    def spread(self) -> Optional[Decimal]:
        """Calculate the spread between ask and bid prices."""
        if self.ask_price is not None and self.bid_price is not None:
            return Decimal(str(self.ask_price)) - Decimal(str(self.bid_price))
        return None
    
    @property
    def mid_price(self) -> Optional[Decimal]:
        """Calculate the mid price between ask and bid."""
        if self.ask_price is not None and self.bid_price is not None:
            return (Decimal(str(self.ask_price)) + Decimal(str(self.bid_price))) / 2
        return None
