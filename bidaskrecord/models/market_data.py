"""Market data models for bid/ask and trade data with denom support."""

from __future__ import annotations

from datetime import datetime
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, DecimalException
from typing import Any, Dict, List, Optional, TypeVar, Union, overload

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    ColumnElement,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import BaseModel

# Type variables for generic type hints
T = TypeVar("T")


class DenomMixin:
    """Mixin for models that handle denomination conversions.

    This mixin provides methods to convert between display amounts (e.g., 1.5 ETH)
    and base amounts (e.g., 1500000000000000000 wei) using a conversion factor.
    """

    @staticmethod
    def to_base_amount(
        amount: Union[str, int, float, Decimal], factor: Union[int, ColumnElement[int]]
    ) -> int:
        """Convert display amount to base units.

        Args:
            amount: The amount to convert (can be string, int, float, or Decimal)
            factor: The conversion factor (10^decimals) as an int or SQL column

        Returns:
            int: The amount in base units

        Raises:
            ValueError: If the amount cannot be converted or is invalid
        """
        try:
            if isinstance(amount, str):
                amount = Decimal(amount)

            # Handle both direct int and SQLAlchemy column for factor
            factor_value = int(
                factor.scalar_subquery().scalar()
                if hasattr(factor, "scalar_subquery")
                else factor
            )

            # Calculate with proper rounding to avoid floating point issues
            result = (Decimal(str(amount)) * Decimal(str(factor_value))).quantize(
                Decimal("1"), rounding=ROUND_DOWN
            )
            return int(result)

        except (ValueError, DecimalException, TypeError) as e:
            raise ValueError(f"Invalid amount {amount} for conversion: {str(e)}") from e

    @overload
    @staticmethod
    def to_display_amount(
        amount: int, factor: Union[int, ColumnElement[int]], precision: int = 18
    ) -> Decimal:
        ...

    @overload
    @staticmethod
    def to_display_amount(
        amount: ColumnElement[int],
        factor: Union[int, ColumnElement[int]],
        precision: int = 18,
    ) -> ColumnElement[Numeric]:
        ...

    @staticmethod
    def to_display_amount(
        amount: Union[int, ColumnElement[int]],
        factor: Union[int, ColumnElement[int]],
        precision: int = 18,
    ) -> Union[Decimal, ColumnElement[Numeric]]:
        """Convert base amount to display units with specified precision.

        Args:
            amount: The amount in base units (int or SQL column)
            factor: The conversion factor (10^decimals) as an int or SQL column
            precision: Number of decimal places for the result

        Returns:
            Decimal or SQL expression: The amount in display units

        Raises:
            ValueError: If the amount cannot be converted or is invalid
        """
        try:
            # If either amount or factor is a SQL expression, return a SQL expression
            if isinstance(amount, ColumnElement) or isinstance(factor, ColumnElement):
                from sqlalchemy import Numeric as SANumeric
                from sqlalchemy import cast as sa_cast
                from sqlalchemy.sql.expression import case

                # Handle SQL expression case
                amount_expr = (
                    amount
                    if isinstance(amount, ColumnElement)
                    else sa_cast(amount, Integer)
                )
                factor_expr = (
                    factor
                    if isinstance(factor, ColumnElement)
                    else sa_cast(factor, Integer)
                )

                # Build the SQL expression: (amount / factor) with proper casting
                result = sa_cast(amount_expr, SANumeric(36, 18)) / sa_cast(
                    factor_expr, SANumeric(36, 18)
                )

                # Add rounding if precision is specified
                if precision is not None:
                    round_factor = Decimal(10) ** -precision
                    result = func.round(result, precision)

                return result

            # Handle Python values
            amount_value = int(amount)
            factor_value = int(factor)

            if factor_value == 0:
                raise ValueError("Conversion factor cannot be zero")

            result = Decimal(amount_value) / Decimal(factor_value)

            # Apply rounding if precision is specified
            if precision is not None:
                result = result.quantize(
                    Decimal(10) ** -precision, rounding=ROUND_HALF_UP
                )

            return result

        except (ValueError, DecimalException, TypeError) as e:
            raise ValueError(f"Invalid base amount {amount} for conversion: {str(e)}")


class DenomReference(BaseModel):
    """Reference for denomination types and their properties.

    This model stores information about different denominations used for prices and sizes,
    including their conversion factors and display properties.
    """

    __tablename__ = "denom_reference"

    #: Denomination type - either 'PRICE' or 'SIZE'
    denom_type: Mapped[str] = mapped_column(
        String(10), nullable=False, doc="Type of denomination (PRICE or SIZE)"
    )

    #: Base denomination (e.g., 'wei', 'satoshi', 'microUSD')
    base_denom: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        doc="Base denomination for calculations (e.g., wei, satoshi, microUSD)",
    )

    #: Display denomination (e.g., 'ETH', 'BTC', 'USD')
    display_denom: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        doc="Display denomination for UI (e.g., ETH, BTC, USD)",
    )

    #: Description of the denomination
    description: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, doc="Description of the denomination"
    )

    #: Number of decimal places for this denomination
    decimals: Mapped[int] = mapped_column(
        Integer, nullable=False, doc="Number of decimal places for this denomination"
    )

    #: Whether this denomination is currently active
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
        doc="Whether this denomination is currently active",
    )

    __table_args__ = (
        # Composite unique constraint on denom_type and base_denom
        Index("idx_denom_ref_type_base", "denom_type", "base_denom", unique=True),
        # Check constraint to ensure valid denom_type values
        CheckConstraint("denom_type IN ('PRICE', 'SIZE')", name="chk_denom_type"),
        # Check constraint to ensure decimals is non-negative
        CheckConstraint("decimals >= 0", name="chk_denom_decimals_non_negative"),
    )

    @property
    def factor(self) -> int:
        """Return the conversion factor (10^decimals)."""
        return 10 ** int(self.decimals) if self.decimals is not None else 1

    def __repr__(self) -> str:
        return (
            f"<DenomReference({self.denom_type}: "
            f"{self.base_denom} -> {self.display_denom}, "
            f"{self.decimals}dp, active={self.is_active})>"
        )


class Asset(BaseModel):
    """Asset model representing a tradable asset with denomination information.

    This model represents a tradable asset (e.g., cryptocurrency, stock, etc.) and manages
    the conversion between base units (e.g., wei, satoshi) and display units (e.g., ETH, BTC).
    """

    __tablename__ = "asset"

    #: Unique symbol identifier for the asset (e.g., 'BTC', 'ETH', 'HASH')
    symbol: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        doc="Unique symbol identifier for the asset (e.g., 'BTC', 'ETH', 'HASH')",
    )

    #: Human-readable name of the asset (e.g., 'Bitcoin', 'Ethereum')
    name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        doc="Human-readable name of the asset (e.g., 'Bitcoin', 'Ethereum')",
    )

    # Base denominations (for internal calculations)
    #: Base denomination for prices (e.g., 'microUSD', 'satoshi')
    base_price_denom: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        doc="Base denomination for prices (e.g., 'microUSD', 'satoshi')",
    )

    #: Base denomination for sizes/quantities (e.g., 'wei', 'satoshi')
    base_size_denom: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        doc="Base denomination for sizes/quantities (e.g., 'wei', 'satoshi')",
    )

    # Display denominations (for user interface)
    #: Display denomination for prices (e.g., 'USD', 'BTC')
    display_price_denom: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        doc="Display denomination for prices (e.g., 'USD', 'BTC')",
    )

    #: Display denomination for sizes/quantities (e.g., 'ETH', 'BTC')
    display_size_denom: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        doc="Display denomination for sizes/quantities (e.g., 'ETH', 'BTC')",
    )

    # Denomination conversion factors (10^decimals)
    #: Conversion factor for price (10^decimals)
    price_denom_factor: Mapped[int] = mapped_column(
        BigInteger, nullable=False, doc="Conversion factor for price (10^decimals)"
    )

    #: Conversion factor for size/quantity (10^decimals)
    size_denom_factor: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        doc="Conversion factor for size/quantity (10^decimals)",
    )

    # Relationships

    #: List of trades for this asset
    trades: Mapped[List["Trade"]] = relationship(
        "Trade",
        back_populates="asset",
        cascade="all, delete-orphan",
        lazy="dynamic",
        doc="List of trades for this asset",
    )

    __table_args__ = (
        # Ensure positive denomination factors
        CheckConstraint(
            "price_denom_factor > 0", name="chk_price_denom_factor_positive"
        ),
        CheckConstraint("size_denom_factor > 0", name="chk_size_denom_factor_positive"),
        # Add index on commonly queried columns
        Index("idx_asset_symbol_lower", func.lower(symbol), unique=True),
    )

    def __repr__(self) -> str:
        return (
            f"<Asset(symbol='{self.symbol}', "
            f"price={self.display_price_denom}({self.base_price_denom}), "
            f"size={self.display_size_denom}({self.base_size_denom}))>"
        )

    @classmethod
    def create_asset(
        cls,
        symbol: str,
        base_price_denom: str,
        base_size_denom: str,
        display_price_denom: str,
        display_size_denom: str,
        price_decimals: int,
        size_decimals: int,
        name: Optional[str] = None,
    ) -> "Asset":
        """Factory method to create a new asset with proper denomination settings.

        Args:
            symbol: Unique symbol for the asset (e.g., 'BTC', 'ETH')
            base_price_denom: Base denomination for prices (e.g., 'microUSD')
            base_size_denom: Base denomination for sizes (e.g., 'wei')
            display_price_denom: Display denomination for prices (e.g., 'USD')
            display_size_denom: Display denomination for sizes (e.g., 'ETH')
            price_decimals: Number of decimal places for price conversion
            size_decimals: Number of decimal places for size conversion
            name: Optional human-readable name of the asset

        Returns:
            A new Asset instance with calculated conversion factors
        """
        return cls(
            symbol=symbol.upper(),
            name=name,
            base_price_denom=base_price_denom,
            base_size_denom=base_size_denom,
            display_price_denom=display_price_denom,
            display_size_denom=display_size_denom,
            price_denom_factor=10**price_decimals,
            size_denom_factor=10**size_decimals,
        )

    def to_base_price(self, amount: Union[str, int, float, Decimal]) -> int:
        """Convert display price to base units.

        Args:
            amount: The amount in display units (e.g., USD)

        Returns:
            int: The amount in base units (e.g., microUSD)

        Raises:
            ValueError: If the amount cannot be converted or is invalid
        """
        return DenomMixin.to_base_amount(amount, self.price_denom_factor)

    @overload
    def to_display_price(self, amount: int, precision: int = 8) -> Decimal:
        ...

    @overload
    def to_display_price(
        self, amount: ColumnElement[int], precision: int = 8
    ) -> ColumnElement[Numeric]:
        ...

    def to_display_price(
        self, amount: Union[int, ColumnElement[int]], precision: int = 8
    ) -> Union[Decimal, Any]:
        """Convert base price to display units.

        Args:
            amount: The amount in base units (e.g., microUSD) or a SQLAlchemy Column
            precision: Number of decimal places to round to

        Returns:
            Decimal or SQL expression: The amount in display units (e.g., USD)

        Raises:
            ValueError: If the amount cannot be converted or is invalid
        """
        from sqlalchemy import Numeric, cast  # pylint: disable=import-outside-toplevel

        if isinstance(amount, int):
            try:
                return (Decimal(amount) / Decimal(10**precision)).quantize(
                    Decimal(10) ** -precision, rounding=ROUND_HALF_UP
                )
            except (ValueError, DecimalException) as e:
                raise ValueError(f"Invalid base amount {amount} for conversion") from e

        # Handle SQLAlchemy Column case
        return cast(amount / (10**precision), Numeric(36, precision))

    def to_base_size(self, amount: Union[str, int, float, Decimal]) -> int:
        """Convert display size to base units.

        Args:
            amount: The amount in display units (e.g., ETH)

        Returns:
            int: The amount in base units (e.g., wei)

        Raises:
            ValueError: If the amount cannot be converted or is invalid
        """
        return DenomMixin.to_base_amount(amount, self.size_denom_factor)

    @overload
    def to_display_size(self, amount: int, precision: int = 18) -> Decimal:
        ...

    @overload
    def to_display_size(
        self, amount: ColumnElement[int], precision: int = 18
    ) -> ColumnElement[Numeric]:
        ...

    def to_display_size(
        self, amount: Union[int, ColumnElement[int]], precision: int = 18
    ) -> Union[Decimal, Any]:
        """Convert base size to display units.

        Args:
            amount: The amount in base units (e.g., wei) or a SQLAlchemy Column
            precision: Number of decimal places to round to

        Returns:
            Decimal or SQL expression: The amount in display units (e.g., ETH)

        Raises:
            ValueError: If the amount cannot be converted or is invalid
        """
        return DenomMixin.to_display_amount(amount, self.size_denom_factor, precision)

    def get_price_denom_info(self) -> Dict[str, Any]:
        """Get price denomination information.

        Returns:
            Dict containing price denomination details
        """
        return {
            "base_denom": self.base_price_denom,
            "display_denom": self.display_price_denom,
            "factor": self.price_denom_factor,
            "decimals": int(round(Decimal(str(self.price_denom_factor)).log10())),
        }

    def get_size_denom_info(self) -> Dict[str, Any]:
        """Get size denomination information.

        Returns:
            Dict containing size denomination details
        """
        return {
            "base_denom": self.base_size_denom,
            "display_denom": self.display_size_denom,
            "factor": self.size_denom_factor,
            "decimals": int(round(Decimal(str(self.size_denom_factor)).log10())),
        }


class Trade(BaseModel):
    """Trade data model with denom support.

    Represents a single trade with price/quantity in both base and display denominations.
    """

    __tablename__ = "trade"

    # Primary trade identifier from the exchange
    trade_id: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )

    # Reference to the asset being traded
    asset_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("asset.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Price in base denomination (e.g., microUSD)
    price_amount: Mapped[int] = mapped_column(Numeric(36, 0), nullable=False)

    # Quantity in base denomination (e.g., wei, satoshi)
    quantity_amount: Mapped[int] = mapped_column(Numeric(36, 0), nullable=False)

    # Timestamp of the trade
    trade_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    # Channel UUID from the exchange
    channel_uuid: Mapped[Optional[str]] = mapped_column(String(50), index=True)

    # Raw message data
    raw_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # Relationships
    asset: Mapped["Asset"] = relationship("Asset", back_populates="trades")

    # Indexes
    __table_args__ = (Index("idx_trade_asset_time", "asset_id", "trade_time"),)

    def __repr__(self) -> str:
        return (
            f"<Trade(trade_id='{self.trade_id}', "
            f"asset_id={self.asset_id}, "
            f"price={self.price_amount}, qty={self.quantity_amount})>"
        )

    # Hybrid properties for display values
    @hybrid_property
    def price_display(self) -> Decimal:
        """Get the trade price in display units.

        Returns:
            Decimal: The trade price in display units (e.g., USD)

        Raises:
            ValueError: If asset is not loaded
        """
        if not hasattr(self, "asset") or self.asset is None:
            raise ValueError("Asset not loaded for this Trade")
        return self.asset.to_display_price(self.price_amount)

    @hybrid_property
    def quantity_display(self) -> Decimal:
        """Get the trade quantity in display units.

        Returns:
            Decimal: The trade quantity in display units (e.g., ETH)

        Raises:
            ValueError: If asset is not loaded
        """
        if not hasattr(self, "asset") or self.asset is None:
            raise ValueError("Asset not loaded for this Trade")
        return self.asset.to_display_size(self.quantity_amount)

    @hybrid_property
    def notional_display(self) -> Decimal:
        """Calculate the notional value in display units (price * quantity).

        Returns:
            Decimal: The notional value in display units

        Raises:
            ValueError: If asset is not loaded or prices/quantities are not available
        """
        if not hasattr(self, "asset") or self.asset is None:
            raise ValueError("Asset not loaded for this Trade")
        return self.price_display * self.quantity_display
