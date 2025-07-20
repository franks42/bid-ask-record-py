-- Trade-Order Book Correlation Queries
-- These queries help analyze how trades impact the order book

-- 1. Get trade with order book context (uses the view we created)
SELECT
    trade_id,
    asset_symbol,
    trade_price_usd,
    trade_quantity_hash,
    trade_total_usd,
    trade_time,
    best_ask_before,
    best_ask_after,
    best_bid_before,
    best_bid_after,
    CASE
        WHEN best_ask_before != best_ask_after THEN 'Ask Moved'
        WHEN best_bid_before != best_bid_after THEN 'Bid Moved'
        ELSE 'No Best Price Change'
    END as impact_summary
FROM trade_orderbook_impact_view
ORDER BY trade_time DESC
LIMIT 10;

-- 2. Find order book levels that changed due to a specific trade
-- Replace 'YOUR_TRADE_ID' with actual trade ID
WITH trade_context AS (
    SELECT before_snapshot_id, after_snapshot_id, trade_price_usd
    FROM trade_orderbook_impact_view
    WHERE trade_id = 'YOUR_TRADE_ID'
),
before_levels AS (
    SELECT 'ask' as side, level_rank, price_usd, quantity_hash
    FROM order_book_asks_view, trade_context
    WHERE snapshot_id = before_snapshot_id
    AND price_usd BETWEEN trade_price_usd - 0.01 AND trade_price_usd + 0.01

    UNION ALL

    SELECT 'bid' as side, level_rank, price_usd, quantity_hash
    FROM order_book_bids_view, trade_context
    WHERE snapshot_id = before_snapshot_id
    AND price_usd BETWEEN trade_price_usd - 0.01 AND trade_price_usd + 0.01
),
after_levels AS (
    SELECT 'ask' as side, level_rank, price_usd, quantity_hash
    FROM order_book_asks_view, trade_context
    WHERE snapshot_id = after_snapshot_id
    AND price_usd BETWEEN trade_price_usd - 0.01 AND trade_price_usd + 0.01

    UNION ALL

    SELECT 'bid' as side, level_rank, price_usd, quantity_hash
    FROM order_book_bids_view, trade_context
    WHERE snapshot_id = after_snapshot_id
    AND price_usd BETWEEN trade_price_usd - 0.01 AND trade_price_usd + 0.01
)
SELECT
    COALESCE(b.side, a.side) as side,
    COALESCE(b.price_usd, a.price_usd) as price_usd,
    COALESCE(b.level_rank, a.level_rank) as level_rank,
    b.quantity_hash as qty_before,
    a.quantity_hash as qty_after,
    CASE
        WHEN b.quantity_hash IS NULL THEN 'ADDED'
        WHEN a.quantity_hash IS NULL THEN 'REMOVED'
        WHEN b.quantity_hash != a.quantity_hash THEN 'MODIFIED'
        ELSE 'UNCHANGED'
    END as change_type,
    COALESCE(a.quantity_hash, 0) - COALESCE(b.quantity_hash, 0) as quantity_change
FROM before_levels b
FULL OUTER JOIN after_levels a ON b.side = a.side AND b.price_usd = a.price_usd AND b.level_rank = a.level_rank
WHERE CASE
    WHEN b.quantity_hash IS NULL THEN 'ADDED'
    WHEN a.quantity_hash IS NULL THEN 'REMOVED'
    WHEN b.quantity_hash != a.quantity_hash THEN 'MODIFIED'
    ELSE 'UNCHANGED'
END != 'UNCHANGED'
ORDER BY side, price_usd;

-- 3. Find trades that significantly moved the best bid/ask
SELECT
    trade_id,
    trade_price_usd,
    trade_quantity_hash,
    trade_time,
    best_ask_before,
    best_ask_after,
    best_bid_before,
    best_bid_after,
    ROUND((best_ask_after - best_ask_before) * 1000, 2) as ask_move_milli_usd,
    ROUND((best_bid_after - best_bid_before) * 1000, 2) as bid_move_milli_usd
FROM trade_orderbook_impact_view
WHERE (ABS(best_ask_after - best_ask_before) > 0.001
    OR ABS(best_bid_after - best_bid_before) > 0.001)
ORDER BY trade_time DESC;

-- 4. Calculate spread changes around trades
SELECT
    trade_id,
    trade_price_usd,
    trade_time,
    best_ask_before,
    best_bid_before,
    best_ask_after,
    best_bid_after,
    ROUND((best_ask_before - best_bid_before) * 1000, 2) as spread_before_milli,
    ROUND((best_ask_after - best_bid_after) * 1000, 2) as spread_after_milli,
    ROUND(((best_ask_after - best_bid_after) - (best_ask_before - best_bid_before)) * 1000, 2) as spread_change_milli
FROM trade_orderbook_impact_view
WHERE best_ask_before IS NOT NULL
    AND best_bid_before IS NOT NULL
    AND best_ask_after IS NOT NULL
    AND best_bid_after IS NOT NULL
ORDER BY ABS(spread_change_milli) DESC;

-- 5. Summary: Trades by their order book impact type
SELECT
    CASE
        WHEN best_ask_before IS NULL OR best_ask_after IS NULL THEN 'Missing Ask Data'
        WHEN best_bid_before IS NULL OR best_bid_after IS NULL THEN 'Missing Bid Data'
        WHEN ABS(best_ask_after - best_ask_before) > 0.001 THEN 'Ask Price Moved'
        WHEN ABS(best_bid_after - best_bid_before) > 0.001 THEN 'Bid Price Moved'
        ELSE 'No Best Price Change'
    END as impact_type,
    COUNT(*) as trade_count,
    ROUND(AVG(trade_quantity_hash), 0) as avg_quantity,
    ROUND(AVG(trade_total_usd), 2) as avg_total_usd
FROM trade_orderbook_impact_view
GROUP BY impact_type
ORDER BY trade_count DESC;
