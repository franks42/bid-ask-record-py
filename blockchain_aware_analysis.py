#!/usr/bin/env python3
"""
Blockchain-aware trade and order book analysis.

CRITICAL OBSERVATION: Temporal Data Correlation Challenges
=========================================================

When analyzing decentralized exchange data, we face a fundamental challenge:

1. ATOMIC BLOCKCHAIN EXECUTION:
   - Multiple trades can execute in the same blockchain block
   - Order book updates happen atomically with trades in that block
   - All changes are committed together as a single transaction

2. TIMESTAMP CORRELATION ISSUES:
   - Trade timestamps: Authoritative from exchange (blockchain timestamp)
   - Order book timestamps: Our 'received_at' (when WE received the data)
   - No blockchain block numbers provided by Figure Markets API
   - No exchange-provided order book timestamps

3. TEMPORAL ANALYSIS CHALLENGES:
   - Trades with identical timestamps = Same blockchain block
   - Order book updates arrive ~100-200ms after trade notifications
   - Must use fuzzy time windows instead of exact block correlation
   - Analysis requires aggregating ALL trades in a block to understand order book impact

4. EXAMPLE DISCOVERY:
   Block 2025-07-20 22:09:21.089046:
   - Trade 1: $0.030 × 13 HASH = $0.39
   - Trade 2: $0.029 × 7374 HASH = $213.85
   - Total: 7387 HASH consumed from bid side
   - Order book change: Exactly 7387 HASH removed from bids ✓

5. FORENSIC ANALYSIS APPROACH:
   - Group trades by exact timestamp (blockchain block proxy)
   - Analyze aggregate liquidity consumption
   - Determine trade direction by examining which side lost liquidity
   - Account for receiving delays in order book updates

This script implements blockchain-aware analysis to handle these temporal
correlation challenges properly.
"""

from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import text

from bidaskrecord.models.base import get_db


def group_trades_by_block_time(time_window_seconds=1):
    """
    Group trades by timestamp to simulate blockchain block grouping.

    Args:
        time_window_seconds: Time window to consider trades as same "block"

    Returns:
        dict: {timestamp: [list of trades]}
    """
    with next(get_db()) as db:
        trades = db.execute(
            text(
                """
            SELECT trade_id, price_display, quantity_display, total_usd_display,
                   trade_time, channel_uuid
            FROM trade
            ORDER BY trade_time DESC
            LIMIT 50
        """
            )
        ).fetchall()

        # Group trades by timestamp (same timestamp = same block)
        blocks = defaultdict(list)

        for trade in trades:
            # Use the exact timestamp as block identifier since
            # Figure Markets gives us the same timestamp for same-block trades
            timestamp = trade[4]
            blocks[timestamp].append(
                {
                    "trade_id": trade[0],
                    "price": trade[1],
                    "quantity": trade[2],
                    "total": trade[3],
                    "timestamp": trade[4],
                    "channel": trade[5],
                }
            )

        return dict(blocks)


def analyze_block_impact(block_timestamp, trades_in_block):
    """Analyze the aggregate impact of all trades in a block."""

    print(f"\n🧱 Block Analysis: {block_timestamp}")
    print("=" * 60)

    # Calculate block totals
    total_hash_traded = sum(t["quantity"] for t in trades_in_block)
    total_usd_value = sum(t["total"] for t in trades_in_block)
    trade_count = len(trades_in_block)

    print(f"📊 Block Summary:")
    print(f"   Trades in block: {trade_count}")
    print(f"   Total HASH traded: {total_hash_traded:.0f}")
    print(f"   Total USD value: ${total_usd_value:.2f}")

    # Show individual trades
    print(f"\n💰 Individual Trades:")
    for i, trade in enumerate(trades_in_block, 1):
        print(
            f"   {i}. {trade['trade_id']}: ${trade['price']:.3f} × {trade['quantity']:.0f} = ${trade['total']:.2f}"
        )

    # Determine trade direction based on order book impact
    direction = analyze_trade_direction(block_timestamp, total_hash_traded)

    print(f"\n🎯 Block Impact:")
    print(f"   Direction: {direction}")
    print(f"   Liquidity consumed: {total_hash_traded:.0f} HASH")

    return {
        "timestamp": block_timestamp,
        "trade_count": trade_count,
        "total_hash": total_hash_traded,
        "total_usd": total_usd_value,
        "direction": direction,
        "trades": trades_in_block,
    }


def analyze_trade_direction(trade_timestamp, expected_quantity):
    """
    Determine if trades were buys or sells by examining order book changes.

    Args:
        trade_timestamp: When the trades occurred
        expected_quantity: Total quantity that should have been consumed

    Returns:
        str: 'BUY', 'SELL', or 'UNCLEAR'
    """
    with next(get_db()) as db:
        # Find order book snapshots before and after
        before_snapshot = db.execute(
            text(
                """
            SELECT DISTINCT snapshot_id, received_at
            FROM order_book_asks_view
            WHERE received_at <= :trade_time
            ORDER BY received_at DESC
            LIMIT 1
        """
            ),
            {"trade_time": trade_timestamp},
        ).fetchone()

        after_snapshot = db.execute(
            text(
                """
            SELECT DISTINCT snapshot_id, received_at
            FROM order_book_asks_view
            WHERE received_at > :trade_time
            ORDER BY received_at ASC
            LIMIT 1
        """
            ),
            {"trade_time": trade_timestamp},
        ).fetchone()

        if not before_snapshot or not after_snapshot:
            return "UNCLEAR - Missing order book data"

        before_snap_id = before_snapshot[0]
        after_snap_id = after_snapshot[0]

        # Check bid side consumption (indicates BUY orders)
        bid_consumption = db.execute(
            text(
                """
            WITH before_bids AS (
                SELECT SUM(quantity_hash) as total_qty
                FROM order_book_bids_view
                WHERE snapshot_id = :before_snap
            ),
            after_bids AS (
                SELECT SUM(quantity_hash) as total_qty
                FROM order_book_bids_view
                WHERE snapshot_id = :after_snap
            )
            SELECT
                b.total_qty as before_total,
                a.total_qty as after_total,
                b.total_qty - a.total_qty as consumed
            FROM before_bids b, after_bids a
        """
            ),
            {"before_snap": before_snap_id, "after_snap": after_snap_id},
        ).fetchone()

        # Check ask side consumption (indicates SELL orders)
        ask_consumption = db.execute(
            text(
                """
            WITH before_asks AS (
                SELECT SUM(quantity_hash) as total_qty
                FROM order_book_asks_view
                WHERE snapshot_id = :before_snap
            ),
            after_asks AS (
                SELECT SUM(quantity_hash) as total_qty
                FROM order_book_asks_view
                WHERE snapshot_id = :after_snap
            )
            SELECT
                b.total_qty as before_total,
                a.total_qty as after_total,
                b.total_qty - a.total_qty as consumed
            FROM before_asks b, after_asks a
        """
            ),
            {"before_snap": before_snap_id, "after_snap": after_snap_id},
        ).fetchone()

        if bid_consumption and ask_consumption:
            bid_consumed = bid_consumption[2] or 0
            ask_consumed = ask_consumption[2] or 0

            # Determine direction based on which side lost more liquidity
            if abs(bid_consumed - expected_quantity) < abs(
                ask_consumed - expected_quantity
            ):
                return f"BUY (consumed {bid_consumed:.0f} HASH from bid side)"
            elif abs(ask_consumed - expected_quantity) < abs(
                bid_consumed - expected_quantity
            ):
                return f"SELL (consumed {ask_consumed:.0f} HASH from ask side)"
            else:
                return f"UNCLEAR (bid: {bid_consumed:.0f}, ask: {ask_consumed:.0f})"

        return "UNCLEAR - Unable to calculate consumption"


def create_blockchain_blocks_view():
    """Create a view that groups trades by timestamp (blockchain blocks)."""

    view_sql = """
    CREATE VIEW IF NOT EXISTS blockchain_blocks_view AS
    WITH trade_blocks AS (
        SELECT
            trade_time as block_timestamp,
            COUNT(*) as trades_in_block,
            SUM(quantity_display) as total_hash_traded,
            SUM(total_usd_display) as total_usd_value,
            AVG(price_display) as avg_price,
            MIN(price_display) as min_price,
            MAX(price_display) as max_price,
            GROUP_CONCAT(trade_id, ', ') as trade_ids
        FROM trade
        GROUP BY trade_time
        HAVING COUNT(*) >= 1  -- Include all blocks, even single trades
    )
    SELECT
        block_timestamp,
        trades_in_block,
        total_hash_traded,
        total_usd_value,
        avg_price,
        CASE
            WHEN trades_in_block = 1 THEN 'Single Trade'
            ELSE 'Multi-Trade Block'
        END as block_type,
        CASE
            WHEN min_price = max_price THEN 'Same Price'
            ELSE 'Price Range: $' || ROUND(min_price, 3) || ' - $' || ROUND(max_price, 3)
        END as price_info,
        trade_ids
    FROM trade_blocks
    ORDER BY block_timestamp DESC;
    """

    with next(get_db()) as db:
        try:
            db.execute(text("DROP VIEW IF EXISTS blockchain_blocks_view"))
            db.execute(text(view_sql))
            db.commit()
            print("✅ Created blockchain_blocks_view")

            # Show sample data
            sample = db.execute(
                text(
                    """
                SELECT block_timestamp, trades_in_block, total_hash_traded,
                       total_usd_value, block_type, trade_ids
                FROM blockchain_blocks_view
                LIMIT 5
            """
                )
            ).fetchall()

            print("\n📋 Sample Blockchain Blocks:")
            print(
                f"{'Timestamp':<20} {'Trades':<6} {'HASH':<10} {'USD':<10} {'Type':<15} {'Trade IDs'}"
            )
            print("-" * 90)
            for row in sample:
                timestamp_str = str(row[0])[:19]
                trade_ids_short = row[5][:30] + "..." if len(row[5]) > 30 else row[5]
                print(
                    f"{timestamp_str:<20} {row[1]:<6} {row[2]:<10.0f} ${row[3]:<9.2f} {row[4]:<15} {trade_ids_short}"
                )

        except Exception as e:
            print(f"❌ Error creating view: {e}")
            db.rollback()


if __name__ == "__main__":
    print("🧱 Blockchain-Aware Trade Analysis")
    print("=" * 50)

    # Create the blockchain blocks view
    create_blockchain_blocks_view()

    # Group trades by block timestamp
    blocks = group_trades_by_block_time()

    print(f"\n📊 Found {len(blocks)} blockchain blocks with trades")

    # Analyze the most recent multi-trade blocks
    multi_trade_blocks = {
        ts: trades for ts, trades in blocks.items() if len(trades) > 1
    }

    if multi_trade_blocks:
        print(f"\n🔍 Analyzing {len(multi_trade_blocks)} multi-trade blocks:")

        for timestamp, trades in list(multi_trade_blocks.items())[:3]:  # Analyze top 3
            block_analysis = analyze_block_impact(timestamp, trades)
    else:
        print("\n📝 No multi-trade blocks found in recent data")

    print(f"\n💡 Key Insights:")
    print("=" * 30)
    print("• Trades with identical timestamps represent same blockchain block")
    print("• Order book updates reflect aggregate impact of entire block")
    print("• Direction analysis examines which side lost liquidity")
    print("• Temporal analysis must account for our receiving delays")
    print("\nQuery the blockchain_blocks_view for block-level analysis!")
