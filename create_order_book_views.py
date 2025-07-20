#!/usr/bin/env python3
"""
Create database views for order book display.

This script creates two views:
1. order_book_asks_view - Shows ask side order book with display values
2. order_book_bids_view - Shows bid side order book with display values
"""

from sqlalchemy import text

from bidaskrecord.models.base import get_db
from bidaskrecord.utils.logging import get_logger

logger = get_logger(__name__)


def create_order_book_views():
    """Create database views for order book display."""

    # SQL for the asks view
    asks_view_sql = """
    CREATE VIEW IF NOT EXISTS order_book_asks_view AS
    SELECT
        ob.id,
        a.symbol as asset_symbol,
        ob.snapshot_id,
        ob.received_at,
        ob.level_rank,
        ob.price_display as price_usd,
        ob.quantity_display as quantity_hash,
        ob.cumulative_display as cumulative_quantity_hash,
        ob.level_cost_display as level_cost_usd,
        ob.cumulative_cost_display as cumulative_cost_usd,
        ob.total_orders,
        ob.channel_uuid
    FROM order_book ob
    JOIN asset a ON ob.asset_id = a.id
    WHERE ob.side = 'ask'
    ORDER BY ob.received_at DESC, ob.level_rank ASC;
    """

    # SQL for the bids view
    bids_view_sql = """
    CREATE VIEW IF NOT EXISTS order_book_bids_view AS
    SELECT
        ob.id,
        a.symbol as asset_symbol,
        ob.snapshot_id,
        ob.received_at,
        ob.level_rank,
        ob.price_display as price_usd,
        ob.quantity_display as quantity_hash,
        ob.cumulative_display as cumulative_quantity_hash,
        ob.level_cost_display as level_cost_usd,
        ob.cumulative_cost_display as cumulative_cost_usd,
        ob.total_orders,
        ob.channel_uuid
    FROM order_book ob
    JOIN asset a ON ob.asset_id = a.id
    WHERE ob.side = 'bid'
    ORDER BY ob.received_at DESC, ob.level_rank ASC;
    """

    with next(get_db()) as db:
        try:
            # Create asks view
            logger.info("Creating order_book_asks_view...")
            db.execute(text(asks_view_sql))

            # Create bids view
            logger.info("Creating order_book_bids_view...")
            db.execute(text(bids_view_sql))

            db.commit()
            logger.info("✅ Successfully created order book views")

            # Test the views by counting records
            asks_count = db.execute(
                text("SELECT COUNT(*) FROM order_book_asks_view")
            ).scalar()
            bids_count = db.execute(
                text("SELECT COUNT(*) FROM order_book_bids_view")
            ).scalar()

            print(f"📊 View Summary:")
            print(f"  - order_book_asks_view: {asks_count} records")
            print(f"  - order_book_bids_view: {bids_count} records")

        except Exception as e:
            logger.error(f"Error creating views: {e}")
            db.rollback()
            raise


def drop_order_book_views():
    """Drop the order book views if they exist."""

    with next(get_db()) as db:
        try:
            logger.info("Dropping existing order book views...")
            db.execute(text("DROP VIEW IF EXISTS order_book_asks_view"))
            db.execute(text("DROP VIEW IF EXISTS order_book_bids_view"))
            db.commit()
            logger.info("✅ Successfully dropped order book views")

        except Exception as e:
            logger.error(f"Error dropping views: {e}")
            db.rollback()
            raise


def show_view_samples():
    """Show sample data from the views."""

    with next(get_db()) as db:
        try:
            print("\n📋 Sample Asks (Top 5 levels from latest snapshot):")
            print("=" * 80)

            asks_sample = db.execute(
                text(
                    """
                SELECT asset_symbol, received_at, level_rank, price_usd, quantity_hash, level_cost_usd
                FROM order_book_asks_view
                WHERE snapshot_id = (SELECT MAX(snapshot_id) FROM order_book_asks_view)
                LIMIT 5
            """
                )
            ).fetchall()

            if asks_sample:
                print(
                    f"{'Rank':<4} {'Price USD':<10} {'Quantity HASH':<15} {'Cost USD':<10} {'Timestamp':<20}"
                )
                print("-" * 70)
                for row in asks_sample:
                    print(
                        f"{row[2]:<4} {row[3]:<10.3f} {row[4]:<15.0f} {row[5]:<10.0f} {row[1]}"
                    )
            else:
                print("No ask data available")

            print("\n📋 Sample Bids (Top 5 levels from latest snapshot):")
            print("=" * 80)

            bids_sample = db.execute(
                text(
                    """
                SELECT asset_symbol, received_at, level_rank, price_usd, quantity_hash, level_cost_usd
                FROM order_book_bids_view
                WHERE snapshot_id = (SELECT MAX(snapshot_id) FROM order_book_bids_view)
                LIMIT 5
            """
                )
            ).fetchall()

            if bids_sample:
                print(
                    f"{'Rank':<4} {'Price USD':<10} {'Quantity HASH':<15} {'Cost USD':<10} {'Timestamp':<20}"
                )
                print("-" * 70)
                for row in bids_sample:
                    print(
                        f"{row[2]:<4} {row[3]:<10.3f} {row[4]:<15.0f} {row[5]:<10.0f} {row[1]}"
                    )
            else:
                print("No bid data available")

        except Exception as e:
            logger.error(f"Error showing samples: {e}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--drop":
        print("Dropping existing order book views...")
        drop_order_book_views()

    if len(sys.argv) > 1 and sys.argv[1] == "--sample":
        print("Showing sample data from views...")
        show_view_samples()
        sys.exit(0)

    print("Creating order book display views...")
    print()

    # Drop existing views first (if any)
    drop_order_book_views()

    # Create new views
    create_order_book_views()

    print()
    print("🎯 Views Created Successfully!")
    print()
    print("You can now query:")
    print("  📈 order_book_asks_view - Ask side order book with display values")
    print("  📉 order_book_bids_view - Bid side order book with display values")
    print()
    print("Example queries:")
    print(
        "  SELECT * FROM order_book_asks_view WHERE asset_symbol = 'HASH-USD' LIMIT 10;"
    )
    print(
        "  SELECT * FROM order_book_bids_view WHERE asset_symbol = 'HASH-USD' LIMIT 10;"
    )
    print()
    print("Run with --sample to see sample data:")
    print("  python create_order_book_views.py --sample")
