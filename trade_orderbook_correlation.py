#!/usr/bin/env python3
"""
Analyze correlation between trades and order book changes.

Shows trade details with the specific order book levels that changed
before and after each trade execution.
"""

from datetime import datetime, timedelta

from sqlalchemy import text

from bidaskrecord.models.base import get_db


def find_orderbook_around_trade(
    trade_time, asset_symbol="HASH-USD", time_window_minutes=2
):
    """
    Find order book snapshots before and after a specific trade time.

    Args:
        trade_time: Trade execution timestamp (datetime object or string)
        asset_symbol: Asset symbol to analyze
        time_window_minutes: How many minutes before/after to look for snapshots

    Returns:
        tuple: (before_snapshot_id, after_snapshot_id, before_time, after_time)
    """
    # Convert string to datetime if needed
    if isinstance(trade_time, str):
        trade_time = datetime.fromisoformat(trade_time.replace("Z", "+00:00"))
    elif hasattr(trade_time, "replace"):
        # It's already a datetime object, ensure it's timezone-aware
        if trade_time.tzinfo is None:
            trade_time = trade_time.replace(tzinfo=None)  # Keep as naive for SQLite
    with next(get_db()) as db:
        # Find order book snapshot just before the trade
        before_snapshot = db.execute(
            text(
                """
            SELECT DISTINCT snapshot_id, received_at
            FROM order_book_asks_view
            WHERE asset_symbol = :symbol
            AND received_at <= :trade_time
            AND received_at >= :trade_time_start
            ORDER BY received_at DESC
            LIMIT 1
        """
            ),
            {
                "symbol": asset_symbol,
                "trade_time": trade_time,
                "trade_time_start": trade_time - timedelta(minutes=time_window_minutes),
            },
        ).fetchone()

        # Find order book snapshot just after the trade
        after_snapshot = db.execute(
            text(
                """
            SELECT DISTINCT snapshot_id, received_at
            FROM order_book_asks_view
            WHERE asset_symbol = :symbol
            AND received_at > :trade_time
            AND received_at <= :trade_time_end
            ORDER BY received_at ASC
            LIMIT 1
        """
            ),
            {
                "symbol": asset_symbol,
                "trade_time": trade_time,
                "trade_time_end": trade_time + timedelta(minutes=time_window_minutes),
            },
        ).fetchone()

        return (
            before_snapshot[0] if before_snapshot else None,
            after_snapshot[0] if after_snapshot else None,
            before_snapshot[1] if before_snapshot else None,
            after_snapshot[1] if after_snapshot else None,
        )


def get_orderbook_changes(before_snapshot_id, after_snapshot_id, side="ask"):
    """
    Compare two order book snapshots and return only the levels that changed.

    Args:
        before_snapshot_id: Snapshot ID before trade
        after_snapshot_id: Snapshot ID after trade
        side: 'ask' or 'bid'

    Returns:
        dict: Changed levels with before/after data
    """
    view_name = f"order_book_{side}s_view"

    with next(get_db()) as db:
        # Get before snapshot data
        before_data = (
            db.execute(
                text(
                    f"""
            SELECT level_rank, price_usd, quantity_hash, level_cost_usd
            FROM {view_name}
            WHERE snapshot_id = :snapshot_id
            ORDER BY level_rank
        """
                ),
                {"snapshot_id": before_snapshot_id},
            ).fetchall()
            if before_snapshot_id
            else []
        )

        # Get after snapshot data
        after_data = (
            db.execute(
                text(
                    f"""
            SELECT level_rank, price_usd, quantity_hash, level_cost_usd
            FROM {view_name}
            WHERE snapshot_id = :snapshot_id
            ORDER BY level_rank
        """
                ),
                {"snapshot_id": after_snapshot_id},
            ).fetchall()
            if after_snapshot_id
            else []
        )

        # Convert to dictionaries for easier comparison
        before_dict = {
            row[0]: {"price": row[1], "quantity": row[2], "cost": row[3]}
            for row in before_data
        }
        after_dict = {
            row[0]: {"price": row[1], "quantity": row[2], "cost": row[3]}
            for row in after_data
        }

        changes = {}
        all_levels = set(before_dict.keys()) | set(after_dict.keys())

        for level in all_levels:
            before = before_dict.get(level)
            after = after_dict.get(level)

            # Check if level changed (price, quantity, or completely new/removed)
            if before != after:
                changes[level] = {
                    "before": before,
                    "after": after,
                    "change_type": (
                        "removed"
                        if before and not after
                        else "added"
                        if not before and after
                        else "modified"
                    ),
                }

        return changes


def analyze_trade_impact(trade_id=None, limit=5):
    """
    Analyze the impact of recent trades on the order book.

    Args:
        trade_id: Specific trade ID to analyze, or None for recent trades
        limit: Number of recent trades to analyze if trade_id is None
    """
    with next(get_db()) as db:
        if trade_id:
            # Analyze specific trade
            trades = db.execute(
                text(
                    """
                SELECT trade_id, price_display, quantity_display, total_usd_display, trade_time
                FROM trade
                WHERE trade_id = :trade_id
            """
                ),
                {"trade_id": trade_id},
            ).fetchall()
        else:
            # Get recent trades
            trades = db.execute(
                text(
                    """
                SELECT trade_id, price_display, quantity_display, total_usd_display, trade_time
                FROM trade
                ORDER BY trade_time DESC
                LIMIT :limit
            """
                ),
                {"limit": limit},
            ).fetchall()

        if not trades:
            print("No trades found")
            return

        print(f"🔍 Trade Impact Analysis")
        print("=" * 80)

        for trade in trades:
            trade_id, price, quantity, total_usd, trade_time = trade

            print(f"\n💰 Trade: {trade_id}")
            print(
                f"   Price: ${price:.3f} | Quantity: {quantity:.0f} HASH | Total: ${total_usd:.2f}"
            )
            print(f"   Time: {trade_time}")

            # Find surrounding order book snapshots
            (
                before_snap,
                after_snap,
                before_time,
                after_time,
            ) = find_orderbook_around_trade(trade_time)

            if not before_snap and not after_snap:
                print("   ❌ No order book data found around this trade")
                continue

            print(f"   📊 Order Book Snapshots:")
            if before_snap:
                print(f"      Before: #{before_snap} at {before_time}")
            if after_snap:
                print(f"      After:  #{after_snap} at {after_time}")

            # Analyze ask changes (usually impacted by buy orders)
            if before_snap and after_snap:
                ask_changes = get_orderbook_changes(before_snap, after_snap, "ask")
                bid_changes = get_orderbook_changes(before_snap, after_snap, "bid")

                if ask_changes:
                    print(f"\n   📈 Ask Changes ({len(ask_changes)} levels):")
                    for level, change in sorted(ask_changes.items()):
                        print(f"      Level {level}: {change['change_type'].upper()}")
                        if change["before"]:
                            print(
                                f"         Before: ${change['before']['price']:.3f} x {change['before']['quantity']:.0f}"
                            )
                        if change["after"]:
                            print(
                                f"         After:  ${change['after']['price']:.3f} x {change['after']['quantity']:.0f}"
                            )

                if bid_changes:
                    print(f"\n   📉 Bid Changes ({len(bid_changes)} levels):")
                    for level, change in sorted(bid_changes.items()):
                        print(f"      Level {level}: {change['change_type'].upper()}")
                        if change["before"]:
                            print(
                                f"         Before: ${change['before']['price']:.3f} x {change['before']['quantity']:.0f}"
                            )
                        if change["after"]:
                            print(
                                f"         After:  ${change['after']['price']:.3f} x {change['after']['quantity']:.0f}"
                            )

                if not ask_changes and not bid_changes:
                    print("   ✅ No order book changes detected")

            print("-" * 80)


def create_trade_orderbook_view():
    """Create a comprehensive view showing trades with their order book context."""

    view_sql = """
    CREATE VIEW IF NOT EXISTS trade_orderbook_impact_view AS
    WITH trade_context AS (
        SELECT
            t.trade_id,
            t.price_display,
            t.quantity_display,
            t.total_usd_display,
            t.trade_time,
            a.symbol as asset_symbol,

            -- Find order book snapshot before trade
            (SELECT ob1.snapshot_id
             FROM order_book ob1
             WHERE ob1.asset_id = t.asset_id
             AND ob1.received_at <= t.trade_time
             ORDER BY ob1.received_at DESC
             LIMIT 1) as before_snapshot_id,

            -- Find order book snapshot after trade
            (SELECT ob2.snapshot_id
             FROM order_book ob2
             WHERE ob2.asset_id = t.asset_id
             AND ob2.received_at > t.trade_time
             ORDER BY ob2.received_at ASC
             LIMIT 1) as after_snapshot_id

        FROM trade t
        JOIN asset a ON t.asset_id = a.id
    )
    SELECT
        tc.trade_id,
        tc.asset_symbol,
        tc.price_display as trade_price_usd,
        tc.quantity_display as trade_quantity_hash,
        tc.total_usd_display as trade_total_usd,
        tc.trade_time,
        tc.before_snapshot_id,
        tc.after_snapshot_id,

        -- Best ask before trade
        (SELECT price_display FROM order_book_asks_view
         WHERE snapshot_id = tc.before_snapshot_id AND level_rank = 1) as best_ask_before,

        -- Best ask after trade
        (SELECT price_display FROM order_book_asks_view
         WHERE snapshot_id = tc.after_snapshot_id AND level_rank = 1) as best_ask_after,

        -- Best bid before trade
        (SELECT price_display FROM order_book_bids_view
         WHERE snapshot_id = tc.before_snapshot_id AND level_rank = 1) as best_bid_before,

        -- Best bid after trade
        (SELECT price_display FROM order_book_bids_view
         WHERE snapshot_id = tc.after_snapshot_id AND level_rank = 1) as best_bid_after

    FROM trade_context tc
    ORDER BY tc.trade_time DESC;
    """

    with next(get_db()) as db:
        try:
            # Drop existing view
            db.execute(text("DROP VIEW IF EXISTS trade_orderbook_impact_view"))

            # Create new view
            db.execute(text(view_sql))
            db.commit()

            print("✅ Created trade_orderbook_impact_view")

            # Show sample data
            sample = db.execute(
                text(
                    """
                SELECT trade_id, trade_price_usd, trade_quantity_hash,
                       best_ask_before, best_ask_after, best_bid_before, best_bid_after
                FROM trade_orderbook_impact_view
                LIMIT 3
            """
                )
            ).fetchall()

            if sample:
                print("\n📋 Sample Data:")
                print(
                    f"{'Trade ID':<15} {'Price':<8} {'Qty':<8} {'Ask Before':<10} {'Ask After':<10} {'Bid Before':<10} {'Bid After':<10}"
                )
                print("-" * 85)
                for row in sample:
                    print(
                        f"{row[0]:<15} ${row[1]:<7.3f} {row[2]:<7.0f} "
                        f"${row[3]:<9.3f} "
                        if row[3]
                        else "N/A       " + f"${row[4]:<9.3f} "
                        if row[4]
                        else "N/A       " + f"${row[5]:<9.3f} "
                        if row[5]
                        else "N/A       " + f"${row[6]:<9.3f}"
                        if row[6]
                        else "N/A"
                    )

        except Exception as e:
            print(f"❌ Error creating view: {e}")
            db.rollback()


if __name__ == "__main__":
    print("🔗 Trade-Order Book Correlation Analysis")
    print("=" * 50)

    # Create comprehensive view
    create_trade_orderbook_view()

    # Analyze recent trades
    print(f"\n{'-'*50}")
    analyze_trade_impact(limit=3)

    print(f"\n💡 Usage Examples:")
    print("=" * 30)
    print("# Analyze specific trade:")
    print("python trade_orderbook_correlation.py --trade-id 'your-trade-id'")
    print()
    print("# Query the comprehensive view:")
    print(
        "SELECT * FROM trade_orderbook_impact_view WHERE trade_time > datetime('now', '-1 day');"
    )
    print()
    print("# Find trades that moved the best bid/ask:")
    print("SELECT * FROM trade_orderbook_impact_view")
    print(
        "WHERE best_ask_before != best_ask_after OR best_bid_before != best_bid_after;"
    )
