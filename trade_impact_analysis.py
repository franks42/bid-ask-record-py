#!/usr/bin/env python3
"""
Simplified Trade Impact Analysis

Shows the exact order book levels that changed due to specific trades,
focusing only on the levels that were actually modified, added, or removed.
"""

import sys

from sqlalchemy import text

from bidaskrecord.models.base import get_db


def analyze_specific_trade(trade_id):
    """Analyze the impact of a specific trade on the order book."""

    with next(get_db()) as db:
        # Get trade details
        trade = db.execute(
            text(
                """
            SELECT t.trade_id, t.price_display, t.quantity_display, t.total_usd_display,
                   t.trade_time, a.symbol
            FROM trade t
            JOIN asset a ON t.asset_id = a.id
            WHERE t.trade_id = :trade_id
        """
            ),
            {"trade_id": trade_id},
        ).fetchone()

        if not trade:
            print(f"❌ Trade {trade_id} not found")
            return

        trade_id, price, quantity, total, trade_time, symbol = trade

        print(f"🔍 Trade Impact Analysis: {trade_id}")
        print("=" * 60)
        print(f"💰 Trade Details:")
        print(f"   Asset: {symbol}")
        print(f"   Price: ${price:.3f}")
        print(f"   Quantity: {quantity:.0f} HASH")
        print(f"   Total Value: ${total:.2f}")
        print(f"   Time: {trade_time}")

        # Get order book context using the view
        context = db.execute(
            text(
                """
            SELECT before_snapshot_id, after_snapshot_id,
                   best_ask_before, best_ask_after,
                   best_bid_before, best_bid_after
            FROM trade_orderbook_impact_view
            WHERE trade_id = :trade_id
        """
            ),
            {"trade_id": trade_id},
        ).fetchone()

        if not context:
            print("❌ No order book context found for this trade")
            return

        before_snap, after_snap, ask_before, ask_after, bid_before, bid_after = context

        print(f"\n📊 Order Book Context:")
        print(f"   Before Snapshot: #{before_snap}")
        print(f"   After Snapshot:  #{after_snap}")
        print(
            f"   Best Ask: ${ask_before:.3f} → ${ask_after:.3f}"
            if ask_before and ask_after
            else "   Best Ask: No data"
        )
        print(
            f"   Best Bid: ${bid_before:.3f} → ${bid_after:.3f}"
            if bid_before and bid_after
            else "   Best Bid: No data"
        )

        if ask_before and ask_after and ask_before != ask_after:
            ask_change = ask_after - ask_before
            print(f"   📈 Ask moved by ${ask_change:+.3f}")

        if bid_before and bid_after and bid_before != bid_after:
            bid_change = bid_after - bid_before
            print(f"   📉 Bid moved by ${bid_change:+.3f}")

        # Analyze detailed changes if we have both snapshots
        if before_snap and after_snap:
            analyze_detailed_changes(before_snap, after_snap, price, quantity)
        else:
            print(
                "\n⚠️  Cannot show detailed level changes - missing before/after snapshots"
            )


def analyze_detailed_changes(before_snap, after_snap, trade_price, trade_quantity):
    """Show detailed level-by-level changes around the trade price."""

    with next(get_db()) as db:
        # Focus on levels around the trade price (±$0.005 range)
        price_range = 0.005

        print(
            f"\n🎯 Detailed Changes (±${price_range} around trade price ${trade_price:.3f}):"
        )
        print("-" * 60)

        # Check ask changes in the relevant price range
        ask_changes = db.execute(
            text(
                """
            WITH before_asks AS (
                SELECT level_rank, price_usd, quantity_hash
                FROM order_book_asks_view
                WHERE snapshot_id = :before_snap
                AND price_usd BETWEEN :min_price AND :max_price
            ),
            after_asks AS (
                SELECT level_rank, price_usd, quantity_hash
                FROM order_book_asks_view
                WHERE snapshot_id = :after_snap
                AND price_usd BETWEEN :min_price AND :max_price
            )
            SELECT
                COALESCE(b.level_rank, a.level_rank) as level_rank,
                COALESCE(b.price_usd, a.price_usd) as price_usd,
                b.quantity_hash as qty_before,
                a.quantity_hash as qty_after,
                CASE
                    WHEN b.quantity_hash IS NULL THEN 'ADDED'
                    WHEN a.quantity_hash IS NULL THEN 'REMOVED'
                    WHEN b.quantity_hash != a.quantity_hash THEN 'MODIFIED'
                    ELSE 'UNCHANGED'
                END as change_type
            FROM before_asks b
            FULL OUTER JOIN after_asks a ON b.level_rank = a.level_rank AND b.price_usd = a.price_usd
            WHERE CASE
                WHEN b.quantity_hash IS NULL THEN 'ADDED'
                WHEN a.quantity_hash IS NULL THEN 'REMOVED'
                WHEN b.quantity_hash != a.quantity_hash THEN 'MODIFIED'
                ELSE 'UNCHANGED'
            END != 'UNCHANGED'
            ORDER BY price_usd ASC
        """
            ),
            {
                "before_snap": before_snap,
                "after_snap": after_snap,
                "min_price": trade_price - price_range,
                "max_price": trade_price + price_range,
            },
        ).fetchall()

        if ask_changes:
            print("📈 Ask Changes:")
            for change in ask_changes:
                level, price, qty_before, qty_after, change_type = change
                print(f"   ${price:.3f} Level {level}: {change_type}")
                if qty_before is not None:
                    print(f"      Before: {qty_before:.0f} HASH")
                if qty_after is not None:
                    print(f"      After:  {qty_after:.0f} HASH")
                if qty_before and qty_after:
                    qty_change = qty_after - qty_before
                    print(f"      Change: {qty_change:+.0f} HASH")

        # Check bid changes in the relevant price range
        bid_changes = db.execute(
            text(
                """
            WITH before_bids AS (
                SELECT level_rank, price_usd, quantity_hash
                FROM order_book_bids_view
                WHERE snapshot_id = :before_snap
                AND price_usd BETWEEN :min_price AND :max_price
            ),
            after_bids AS (
                SELECT level_rank, price_usd, quantity_hash
                FROM order_book_bids_view
                WHERE snapshot_id = :after_snap
                AND price_usd BETWEEN :min_price AND :max_price
            )
            SELECT
                COALESCE(b.level_rank, a.level_rank) as level_rank,
                COALESCE(b.price_usd, a.price_usd) as price_usd,
                b.quantity_hash as qty_before,
                a.quantity_hash as qty_after,
                CASE
                    WHEN b.quantity_hash IS NULL THEN 'ADDED'
                    WHEN a.quantity_hash IS NULL THEN 'REMOVED'
                    WHEN b.quantity_hash != a.quantity_hash THEN 'MODIFIED'
                    ELSE 'UNCHANGED'
                END as change_type
            FROM before_bids b
            FULL OUTER JOIN after_bids a ON b.level_rank = a.level_rank AND b.price_usd = a.price_usd
            WHERE CASE
                WHEN b.quantity_hash IS NULL THEN 'ADDED'
                WHEN a.quantity_hash IS NULL THEN 'REMOVED'
                WHEN b.quantity_hash != a.quantity_hash THEN 'MODIFIED'
                ELSE 'UNCHANGED'
            END != 'UNCHANGED'
            ORDER BY price_usd DESC
        """
            ),
            {
                "before_snap": before_snap,
                "after_snap": after_snap,
                "min_price": trade_price - price_range,
                "max_price": trade_price + price_range,
            },
        ).fetchall()

        if bid_changes:
            print("\n📉 Bid Changes:")
            for change in bid_changes:
                level, price, qty_before, qty_after, change_type = change
                print(f"   ${price:.3f} Level {level}: {change_type}")
                if qty_before is not None:
                    print(f"      Before: {qty_before:.0f} HASH")
                if qty_after is not None:
                    print(f"      After:  {qty_after:.0f} HASH")
                if qty_before and qty_after:
                    qty_change = qty_after - qty_before
                    print(f"      Change: {qty_change:+.0f} HASH")

        if not ask_changes and not bid_changes:
            print(
                f"✅ No order book changes detected in ±${price_range} range around trade price"
            )


def list_recent_trades():
    """List recent trades for analysis."""

    with next(get_db()) as db:
        trades = db.execute(
            text(
                """
            SELECT t.trade_id, t.price_display, t.quantity_display, t.total_usd_display,
                   t.trade_time, a.symbol
            FROM trade t
            JOIN asset a ON t.asset_id = a.id
            ORDER BY t.trade_time DESC
            LIMIT 10
        """
            )
        ).fetchall()

        print("📋 Recent Trades Available for Analysis:")
        print("=" * 70)
        print(
            f"{'Trade ID':<16} {'Symbol':<10} {'Price':<8} {'Quantity':<10} {'Total':<10} {'Time':<20}"
        )
        print("-" * 70)

        for trade in trades:
            trade_id, price, qty, total, trade_time, symbol = trade
            time_str = str(trade_time)[:19]
            print(
                f"{trade_id:<16} {symbol:<10} ${price:<7.3f} {qty:<9.0f} ${total:<9.2f} {time_str}"
            )

        print(f"\nTo analyze a specific trade:")
        print(f"python {sys.argv[0]} <trade_id>")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        trade_id = sys.argv[1]
        analyze_specific_trade(trade_id)
    else:
        list_recent_trades()
