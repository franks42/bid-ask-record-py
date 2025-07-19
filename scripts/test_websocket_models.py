"""Test WebSocket message handling with database models using real data from logs."""

import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session

from bidaskrecord.config.settings import get_settings
from bidaskrecord.models.base import engine, get_db, init_db
from bidaskrecord.models.market_data import Asset, BidAsk, Trade

settings = get_settings()


def create_test_asset():
    """Create a test asset if it doesn't exist."""
    with Session(engine) as session:
        # Check if asset exists
        asset = session.query(Asset).filter(Asset.symbol == "HASH-USD").first()
        if not asset:
            # Create test asset based on real data
            asset = Asset.create_asset(
                symbol="HASH-USD",
                base_price_denom="microUSD",
                base_size_denom="nanoHASH",
                display_price_denom="USD",
                display_size_denom="HASH",
                price_decimals=6,  # microUSD (6 decimals)
                size_decimals=9,  # nanoHASH (9 decimals)
                name="HASH-USD Trading Pair",
            )
            session.add(asset)
            session.commit()
            print(f"Created test asset: {asset}")
        return asset


def test_orderbook_message():
    """Test processing an order book update from WebSocket with real data."""
    # Real order book data from logs
    orderbook_msg = {
        "channelUuid": "e538f596-33d5-4749-8eae-af8ef1f40740",
        "asks": [
            {"price": "0.031", "quantity": "292483.233"},
            {"price": "0.032", "quantity": "295000.829"},
            {"price": "0.033", "quantity": "200000.000"},
        ],
        "bids": [
            {"price": "0.030", "quantity": "18.333"},
            {"price": "0.029", "quantity": "237.524"},
            {"price": "0.025", "quantity": "803693.324"},
        ],
        "channel": "ORDER_BOOK",
        "timestamp": 1721335519.944,  # Current timestamp
    }

    # Get a database session
    db = next(get_db())
    try:
        # Get or create test asset
        asset = db.query(Asset).filter(Asset.symbol == "HASH-USD").first()
        if not asset:
            asset = create_test_asset()
            db.add(asset)
            db.commit()

        # Create bid/ask from message (using best bid/ask)
        best_bid = orderbook_msg["bids"][0]
        best_ask = orderbook_msg["asks"][0]

        bidask = BidAsk(
            asset_id=asset.id,
            exchange_timestamp=Decimal(str(orderbook_msg["timestamp"])),
            bid_price_amount=asset.to_base_price(best_bid["price"]),
            ask_price_amount=asset.to_base_price(best_ask["price"]),
            bid_size_amount=asset.to_base_size(best_bid["quantity"]),
            ask_size_amount=asset.to_base_size(best_ask["quantity"]),
            raw_data=orderbook_msg,
        )

        db.add(bidask)
        db.commit()

        # Verify the bid/ask was saved
        saved_bidask = db.query(BidAsk).order_by(BidAsk.id.desc()).first()
        print("\n=== Order Book Test ===")
        print(f"Saved bid/ask: {saved_bidask}")
        print(
            f"Best Bid: {saved_bidask.bid_price_display} {asset.display_price_denom} x {saved_bidask.bid_size_display} {asset.display_size_denom}"
        )
        print(
            f"Best Ask: {saved_bidask.ask_price_display} {asset.display_price_denom} x {saved_bidask.ask_size_display} {asset.display_size_denom}"
        )
        print(f"Raw data: {saved_bidask.raw_data}")

        return saved_bidask is not None
    except Exception as e:
        db.rollback()
        print(f"Error in test_orderbook_message: {e}")
        raise
    finally:
        db.close()


def test_trade_message():
    """Test processing a trade message from WebSocket with real data."""
    # Real trade data from logs
    trade_msg = {
        "channelUuid": "65039603-31af-4f54-a165-ded9e581ad29",
        "id": "3ZXV886H218R",
        "price": 0.0305,  # In display units (USD)
        "quantity": 100.0,  # In display units (HASH)
        "created": "2025-07-18T22:45:21.148Z",
        "channel": "TRADES",
    }

    # Get a database session
    db = next(get_db())
    try:
        # Get or create test asset
        asset = db.query(Asset).filter(Asset.symbol == "HASH-USD").first()
        if not asset:
            asset = create_test_asset()
            db.add(asset)
            db.commit()

        # Create trade from message
        trade = Trade(
            trade_id=trade_msg["id"],
            asset_id=asset.id,
            price_amount=asset.to_base_price(trade_msg["price"]),
            quantity_amount=asset.to_base_size(trade_msg["quantity"]),
            trade_time=datetime.fromisoformat(
                trade_msg["created"].replace("Z", "+00:00")
            ),
            channel_uuid=trade_msg["channelUuid"],
            raw_data=trade_msg,
        )

        db.add(trade)
        db.commit()

        # Verify the trade was saved
        saved_trade = db.query(Trade).filter(Trade.trade_id == trade_msg["id"]).first()
        print("\n=== Trade Test ===")
        print(f"Saved trade: {saved_trade}")
        print(f"Price: {saved_trade.price_display} {asset.display_price_denom}")
        print(f"Quantity: {saved_trade.quantity_display} {asset.display_size_denom}")
        print(f"Total: {saved_trade.notional_display} {asset.display_price_denom}")
        print(f"Raw data: {saved_trade.raw_data}")

        return saved_trade is not None
    except Exception as e:
        db.rollback()
        print(f"Error in test_trade_message: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    # Initialize database
    from bidaskrecord.models.base import engine

    init_db()

    # Run tests
    print("=== Testing Trade Message ===")
    trade_success = test_trade_message()
    print(f"Trade test {'succeeded' if trade_success else 'failed'}")

    print("\n=== Testing Order Book Message ===")
    orderbook_success = test_orderbook_message()
    print(f"Order book test {'succeeded' if orderbook_success else 'failed'}")
