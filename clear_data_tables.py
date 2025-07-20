#!/usr/bin/env python3
"""
Database utility script to clear data tables but preserve/create assets.

This script:
1. Clears all rows from order_book, order_book_raw, and trade tables
2. Checks if HASH-USD asset exists, creates it if missing
3. Leaves the database ready for fresh data collection
"""

import sys
from datetime import datetime

from bidaskrecord.config.settings import get_settings
from bidaskrecord.models.base import get_db
from bidaskrecord.models.market_data import Asset, Trade
from bidaskrecord.models.order_book import OrderBook
from bidaskrecord.models.order_book_raw import OrderBookRaw


def clear_data_tables():
    """Clear all data tables but preserve/create assets."""
    print("=== DATABASE TABLE CLEANUP ===")

    # Get database session
    db = next(get_db())

    try:
        # Count existing records
        order_book_count = db.query(OrderBook).count()
        order_book_raw_count = db.query(OrderBookRaw).count()
        trade_count = db.query(Trade).count()
        asset_count = db.query(Asset).count()

        print(f"Current record counts:")
        print(f"  - order_book: {order_book_count}")
        print(f"  - order_book_raw: {order_book_raw_count}")
        print(f"  - trade: {trade_count}")
        print(f"  - asset: {asset_count}")
        print()

        # Clear data tables
        print("Clearing data tables...")

        # Delete all order book records
        deleted_order_book = db.query(OrderBook).delete()
        print(f"  - Deleted {deleted_order_book} order_book records")

        # Delete all raw order book records
        deleted_raw = db.query(OrderBookRaw).delete()
        print(f"  - Deleted {deleted_raw} order_book_raw records")

        # Delete all trade records
        deleted_trades = db.query(Trade).delete()
        print(f"  - Deleted {deleted_trades} trade records")

        # Check if HASH-USD asset exists
        hash_usd_asset = db.query(Asset).filter(Asset.symbol == "HASH-USD").first()

        if hash_usd_asset:
            print(f"  - HASH-USD asset already exists (ID: {hash_usd_asset.id})")
        else:
            print("  - Creating HASH-USD asset...")

            # Create HASH-USD asset with proper configuration
            hash_usd_asset = Asset(
                symbol="HASH-USD",
                name="HASH Token traded in USD",
                base_price_denom="microUSD",  # Price in microUSD (1/1,000,000 USD)
                base_size_denom="nanoHASH",  # Quantity in nanoHASH (1/1,000,000,000 HASH)
                display_price_denom="USD",  # Display prices in USD
                display_size_denom="HASH",  # Display quantities in HASH
                price_denom_factor=1000000,  # 1 USD = 1,000,000 microUSD
                size_denom_factor=1000000000,  # 1 HASH = 1,000,000,000 nanoHASH
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )

            db.add(hash_usd_asset)
            print(f"  - Created HASH-USD asset")

        # Commit all changes
        db.commit()
        print()
        print("✅ Database cleanup completed successfully!")

        # Show final counts
        final_order_book = db.query(OrderBook).count()
        final_raw = db.query(OrderBookRaw).count()
        final_trades = db.query(Trade).count()
        final_assets = db.query(Asset).count()

        print(f"Final record counts:")
        print(f"  - order_book: {final_order_book}")
        print(f"  - order_book_raw: {final_raw}")
        print(f"  - trade: {final_trades}")
        print(f"  - asset: {final_assets}")
        print()
        print("Database is ready for fresh data collection!")

    except Exception as e:
        print(f"❌ Error during cleanup: {e}")
        db.rollback()
        sys.exit(1)

    finally:
        db.close()


if __name__ == "__main__":
    print("This script will clear all order book and trade data but preserve assets.")

    # Confirm with user
    response = input("Continue? [y/N]: ").strip().lower()
    if response not in ["y", "yes"]:
        print("Cancelled.")
        sys.exit(0)

    clear_data_tables()
