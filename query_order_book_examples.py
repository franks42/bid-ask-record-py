#!/usr/bin/env python3
"""
Example queries for the order book views.

Demonstrates various ways to query the order_book_asks_view and order_book_bids_view.
"""

from sqlalchemy import text

from bidaskrecord.models.base import get_db


def show_latest_order_book():
    """Show the latest order book snapshot."""

    with next(get_db()) as db:
        print("🔍 Latest Order Book Snapshot")
        print("=" * 60)

        # Get latest snapshot ID
        latest_snapshot = db.execute(
            text(
                """
            SELECT MAX(snapshot_id) FROM order_book_asks_view
            WHERE asset_symbol = 'HASH-USD'
        """
            )
        ).scalar()

        if not latest_snapshot:
            print("No order book data available")
            return

        print(f"Snapshot ID: {latest_snapshot}")

        # Show top 5 asks
        print("\n📈 Top 5 Asks:")
        asks = db.execute(
            text(
                """
            SELECT level_rank, price_usd, quantity_hash, level_cost_usd
            FROM order_book_asks_view
            WHERE asset_symbol = 'HASH-USD' AND snapshot_id = :snapshot_id
            ORDER BY level_rank
            LIMIT 5
        """
            ),
            {"snapshot_id": latest_snapshot},
        ).fetchall()

        print(f"{'Rank':<4} {'Price':<8} {'Quantity':<12} {'Cost USD':<10}")
        print("-" * 40)
        for ask in asks:
            print(f"{ask[0]:<4} ${ask[1]:<7.3f} {ask[2]:<12.0f} ${ask[3]:<9.0f}")

        # Show top 5 bids
        print("\n📉 Top 5 Bids:")
        bids = db.execute(
            text(
                """
            SELECT level_rank, price_usd, quantity_hash, level_cost_usd
            FROM order_book_bids_view
            WHERE asset_symbol = 'HASH-USD' AND snapshot_id = :snapshot_id
            ORDER BY level_rank
            LIMIT 5
        """
            ),
            {"snapshot_id": latest_snapshot},
        ).fetchall()

        print(f"{'Rank':<4} {'Price':<8} {'Quantity':<12} {'Cost USD':<10}")
        print("-" * 40)
        for bid in bids:
            print(f"{bid[0]:<4} ${bid[1]:<7.3f} {bid[2]:<12.0f} ${bid[3]:<9.0f}")


def show_best_bid_ask_over_time():
    """Show best bid/ask prices over the last few snapshots."""

    with next(get_db()) as db:
        print("\n⏰ Best Bid/Ask Over Time (Last 10 snapshots)")
        print("=" * 60)

        # Get best asks over time
        best_asks = db.execute(
            text(
                """
            SELECT snapshot_id, received_at, price_usd, quantity_hash
            FROM order_book_asks_view
            WHERE asset_symbol = 'HASH-USD' AND level_rank = 1
            ORDER BY snapshot_id DESC
            LIMIT 10
        """
            )
        ).fetchall()

        # Get best bids over time
        best_bids = db.execute(
            text(
                """
            SELECT snapshot_id, received_at, price_usd, quantity_hash
            FROM order_book_bids_view
            WHERE asset_symbol = 'HASH-USD' AND level_rank = 1
            ORDER BY snapshot_id DESC
            LIMIT 10
        """
            )
        ).fetchall()

        print(
            f"{'Snapshot':<8} {'Time':<20} {'Best Ask':<10} {'Best Bid':<10} {'Spread':<8}"
        )
        print("-" * 70)

        # Combine and show data
        ask_dict = {ask[0]: ask for ask in best_asks}
        bid_dict = {bid[0]: bid for bid in best_bids}

        all_snapshots = sorted(
            set(ask_dict.keys()) | set(bid_dict.keys()), reverse=True
        )

        for snapshot_id in all_snapshots[:5]:  # Show only last 5
            ask = ask_dict.get(snapshot_id)
            bid = bid_dict.get(snapshot_id)

            ask_price = ask[2] if ask else None
            bid_price = bid[2] if bid else None
            timestamp = ask[1] if ask else bid[1] if bid else None
            spread = ask_price - bid_price if ask_price and bid_price else None

            print(
                f"{snapshot_id:<8} {str(timestamp)[:19]:<20} " f"${ask_price:.3f} "
                if ask_price
                else "N/A       " + f"${bid_price:.3f} "
                if bid_price
                else "N/A       " + f"${spread:.3f}"
                if spread
                else "N/A"
            )


def show_order_book_depth():
    """Show order book depth (cumulative quantities and costs)."""

    with next(get_db()) as db:
        print("\n📊 Order Book Depth (Latest Snapshot)")
        print("=" * 60)

        # Get latest snapshot ID
        latest_snapshot = db.execute(
            text(
                """
            SELECT MAX(snapshot_id) FROM order_book_asks_view
            WHERE asset_symbol = 'HASH-USD'
        """
            )
        ).scalar()

        if not latest_snapshot:
            print("No order book data available")
            return

        print(f"Snapshot ID: {latest_snapshot}")

        # Show asks depth
        print("\n📈 Ask Depth:")
        asks_depth = db.execute(
            text(
                """
            SELECT level_rank, price_usd, quantity_hash, cumulative_quantity_hash, cumulative_cost_usd
            FROM order_book_asks_view
            WHERE asset_symbol = 'HASH-USD' AND snapshot_id = :snapshot_id
            ORDER BY level_rank
            LIMIT 10
        """
            ),
            {"snapshot_id": latest_snapshot},
        ).fetchall()

        print(
            f"{'Rank':<4} {'Price':<8} {'Quantity':<12} {'Cumulative Qty':<15} {'Cumulative Cost':<15}"
        )
        print("-" * 65)
        for ask in asks_depth:
            print(
                f"{ask[0]:<4} ${ask[1]:<7.3f} {ask[2]:<12.0f} " f"{ask[3]:<15.0f} "
                if ask[3]
                else "N/A            " + f"${ask[4]:<14.0f}"
                if ask[4]
                else "N/A"
            )


def query_by_time_range():
    """Show order book data within a specific time range."""

    with next(get_db()) as db:
        print("\n🕐 Order Book Data (Last Hour)")
        print("=" * 60)

        # Count snapshots in last hour
        snapshot_count = db.execute(
            text(
                """
            SELECT COUNT(DISTINCT snapshot_id)
            FROM order_book_asks_view
            WHERE asset_symbol = 'HASH-USD'
            AND received_at > datetime('now', '-1 hour')
        """
            )
        ).scalar()

        print(f"Order book snapshots in last hour: {snapshot_count}")

        if snapshot_count > 0:
            # Show average spread over last hour
            avg_spread = db.execute(
                text(
                    """
                SELECT AVG(a.price_usd - b.price_usd) as avg_spread
                FROM order_book_asks_view a
                JOIN order_book_bids_view b ON a.snapshot_id = b.snapshot_id
                WHERE a.asset_symbol = 'HASH-USD'
                AND b.asset_symbol = 'HASH-USD'
                AND a.level_rank = 1 AND b.level_rank = 1
                AND a.received_at > datetime('now', '-1 hour')
            """
                )
            ).scalar()

            print(
                f"Average spread in last hour: ${avg_spread:.4f}"
                if avg_spread
                else "N/A"
            )


if __name__ == "__main__":
    print("📋 Order Book View Examples")
    print("=" * 50)

    show_latest_order_book()
    show_best_bid_ask_over_time()
    show_order_book_depth()
    query_by_time_range()

    print("\n💡 More Query Examples:")
    print("=" * 30)
    print("# Get all asks below $0.035:")
    print("SELECT * FROM order_book_asks_view WHERE price_usd < 0.035;")
    print()
    print("# Get bids with more than 100,000 HASH:")
    print("SELECT * FROM order_book_bids_view WHERE quantity_hash > 100000;")
    print()
    print("# Get recent order book activity:")
    print(
        "SELECT * FROM order_book_asks_view WHERE received_at > datetime('now', '-30 minutes');"
    )
    print()
    print("# Calculate total liquidity at each level:")
    print("SELECT level_rank, SUM(quantity_hash) as total_liquidity")
    print("FROM order_book_asks_view GROUP BY level_rank ORDER BY level_rank;")
