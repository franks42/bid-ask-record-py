# Claude Context - Bid-Ask Recorder Project

## Project Overview
This is a Python application that records bid-ask market data from Figure Markets Exchange using WebSocket connections. The project has been enhanced for production-ready 24/7 operation with comprehensive monitoring and reliability features.

## Current State
- **Working Directory**: `/Users/franksiebenlist/Documents/GitHub/bid-ask-record-py`
- **Main Branch**: `main`
- **Python Environment**: Uses `uv` for dependency management
- **Database**: SQLite database (`market_data.db`) with SQLAlchemy ORM
- **Status**: Fully functional and ready for production use

## Recent Work Completed

### 1. Figure Markets WebSocket Behavior Analysis (Current Session)
**Discovered FM's Connection Requirements:**
- **WebSocket Protocol Pings**: FM requires WebSocket protocol pings every ~60 seconds for keepalive
- **No Pong Responses**: FM accepts pings but does not respond with pongs (one-way keepalive)
- **JSON Ping Rejection**: FM rejects JSON `{"action":"PING"}` messages with "Invalid request"
- **30-Second Order Book Pattern**: FM sends order book snapshots every 30 seconds regardless of changes
- **Duplicate Detection Essential**: Many snapshots are identical when market is inactive

**Implementation:**
- Configured WebSocket protocol pings every 61 seconds (`ping_interval=61`)
- Removed all JSON ping/pong handling code
- Enhanced duplicate detection with separate `order_book_raw` table
- Added comprehensive documentation of FM's behavior

### 2. Fixed Critical Syntax Errors (Previous Session)
- Resolved syntax error in `bidaskrecord/models/market_data.py` (unterminated triple quotes)
- Fixed import errors and code formatting issues
- Applied black formatting and isort import sorting

### 2. Implemented Production Reliability Features (Previous Session)
**Four Major Improvements for 24/7 Operation:**

1. **Unlimited Retry Capability**
   - Modified `bidaskrecord/core/websocket_client.py` retry logic
   - Set `WEBSOCKET_MAX_RETRIES=-1` for unlimited reconnection attempts
   - Implemented exponential backoff with reset on successful connection

2. **Robust Database Session Management**
   - Enhanced `bidaskrecord/models/base.py` with proper context managers
   - Added automatic rollback on exceptions in `get_db()` function
   - Prevents database connection leaks

3. **Health Monitoring System**
   - Added heartbeat monitoring with configurable intervals
   - Implemented connection health checks with forced reconnection
   - Added settings: `HEARTBEAT_INTERVAL`, `HEARTBEAT_TIMEOUT`, `MAX_NO_DATA_SECONDS`

4. **Comprehensive Metrics & Alerting**
   - Created `bidaskrecord/utils/metrics.py` with full metrics tracking
   - Tracks connection health, data flow, heartbeat status, database operations
   - Webhook alerting system with configurable cooldown periods
   - Automatic alerts for: high connection failures, no data received, heartbeat failures

### 3. Fixed Missing Dependencies
- Added `aiohttp` dependency for webhook alerts functionality
- Resolved `ModuleNotFoundError` that prevented startup

### 4. Created Documentation
- Added `HOWTO.txt` - comprehensive plain text usage guide
- Covers starting/stopping, monitoring, configuration, troubleshooting

### 5. Comprehensive Trade-Order Book Correlation Analysis (Current Session)
**Major New Features for Market Analysis:**

1. **Trade Display Columns**
   - Added `price_display`, `quantity_display`, `total_usd_display` to Trade model
   - Automatic calculation of display values with proper decimal precision (3 decimals for price, 0 for quantity)
   - Enhanced Trade.create_with_display_values() factory method

2. **Database Views for Clean Analysis**
   - `order_book_asks_view` - Ask side order book with display values
   - `order_book_bids_view` - Bid side order book with display values
   - `trade_orderbook_impact_view` - Trades with before/after order book context
   - `blockchain_blocks_view` - Groups trades by blockchain block timestamp

3. **Blockchain-Aware Analysis System**
   - Discovered temporal correlation challenges between trade timestamps (authoritative) and order book timestamps (our received_at)
   - Implemented forensic analysis to determine trade direction (buy vs sell) by examining liquidity consumption
   - Critical insight: Trades with identical timestamps execute atomically in same blockchain block

4. **Advanced Analysis Tools**
   - `trade_impact_analysis.py` - Analyze specific trade impacts on order book levels
   - `blockchain_aware_analysis.py` - Handle temporal correlation challenges and atomic block analysis
   - `create_order_book_views.py` - Generate clean SQL views for analysis
   - `query_order_book_examples.py` - Example queries and usage patterns
   - `trade_orderbook_correlation.py` - Comprehensive correlation analysis
   - `trade_orderbook_queries.sql` - Pre-built SQL queries for common analysis patterns

### 6. Critical Market Microstructure Discoveries
**Documented Temporal Data Correlation Challenges:**

1. **The Problem**: DEX trades execute atomically in blockchain blocks, but API provides:
   - Trade timestamps (authoritative from blockchain)
   - Order book timestamps (our received_at, ~100-200ms delayed)
   - No blockchain block numbers for correlation

2. **Example Discovery**: Block 2025-07-20 22:09:21.089046
   - Trade 1: $0.030 × 13 HASH = $0.39
   - Trade 2: $0.029 × 7374 HASH = $213.85
   - Total: 7387 HASH removed from bid side (forensic match ✓)

3. **Forensic Trade Direction Detection**:
   - SELL orders consume bid-side liquidity (sellers "hit the bids")
   - BUY orders consume ask-side liquidity (buyers "hit the asks")
   - Can reliably determine direction by examining which side lost liquidity

4. **DEX Trade Mechanics Understanding**:
   - Trades are NOT separate transactions but order overlap settlements
   - Order submission → Overlap detection → Atomic settlement in single block
   - What we see as "trades" are settlement events from overlapping orders

5. **Analysis Limitations Documented**:
   - Can detect: direction, settlement quantities, atomic execution patterns
   - Cannot detect: order types, fill conditions, partial fills vs complete fills, hidden orders

### 7. Major Database Schema Refactor (Previous Session)
**Unified Order Book System with Production Quality:**

1. **Unified order_book Table**
   - Replaced fragmented tables (bid_ask, order_book_snapshot, order_book_level) with single comprehensive table
   - All order book information now in one table with proper relationships
   - Eliminated complex joins and improved query performance

2. **Timestamp Optimization**
   - Removed exchange_timestamp column (always NULL from Figure Markets)
   - Single received_at timestamp ensures consistency across all levels in same message
   - Simplified schema and removed unnecessary complexity

3. **Data Quality & Precision**
   - Implement duplicate detection - only saves when order book actually changes
   - Pre-computed display values with exact precision requirements:
     * Prices: 3 decimal places (e.g., 0.026)
     * Quantities: whole tokens (e.g., 1923)
     * Costs: whole USD amounts (e.g., 50)
   - Proper base denomination handling: microUSD for prices, nanoHASH for quantities

4. **Full Depth Order Book Recording**
   - Process ALL bid/ask levels (not just best prices)
   - Capture complete market depth with level ranking
   - Include cumulative quantities and cost calculations
   - Store raw data for auditing

5. **Production Testing & Validation**
   - Fixed critical bug: undefined exchange_timestamp references
   - Verified database writes with proper error handling
   - Tested complete order book snapshots (33 levels recorded successfully)
   - Clean imports and removed all legacy code references

## Key Files and Their Purpose

### Core Application
- `bidaskrecord/cli.py` - Command-line interface with Click
- `bidaskrecord/core/websocket_client.py` - Main WebSocket client with full order book processing and duplicate detection
- `bidaskrecord/config/settings.py` - Pydantic settings with environment variables
- `bidaskrecord/models/base.py` - SQLAlchemy base models and session management
- `bidaskrecord/models/market_data.py` - Asset, Trade models with denomination conversion (BidAsk removed)
- `bidaskrecord/models/order_book.py` - **NEW** Unified OrderBook model with all order book data
- `bidaskrecord/utils/logging.py` - Structured logging configuration
- `bidaskrecord/utils/metrics.py` - Metrics tracking and alerting system

### Configuration & Setup
- `pyproject.toml` - Project configuration and dependencies
- `uv.lock` - Locked dependency versions
- `.env.example` - Environment variable template
- `alembic.ini` - Database migration configuration

### Documentation
- `README.md` - Project overview
- `HOWTO.txt` - Comprehensive usage guide (plain text)
- `CLAUDE.md` - This context file

### Database
- `market_data.db` - SQLite database with clean 4-table schema:
  * `asset` - Trading pairs with denomination settings
  * `denom_reference` - Denomination metadata
  * `order_book` - **Unified table** with complete order book data
  * `trade` - Individual trade records
- `migrations/` - Alembic database migration files

## Current Configuration
The application supports these key environment variables:

### WebSocket & Retry Settings
- `WEBSOCKET_URL` - Figure Markets WebSocket endpoint
- `WEBSOCKET_MAX_RETRIES=-1` - Unlimited retries
- `WEBSOCKET_RECONNECT_DELAY=5` - Initial reconnect delay

### Health Monitoring
- `CONNECTION_HEALTH_CHECK_INTERVAL=60` - Health check frequency
- `MAX_NO_DATA_SECONDS=300` - Force reconnect threshold
- `HEARTBEAT_INTERVAL=30` - Heartbeat frequency
- `HEARTBEAT_TIMEOUT=10` - Heartbeat response timeout

### Metrics & Alerting
- `MONITORING_ENABLED=true` - Enable metrics tracking
- `METRICS_REPORTING_INTERVAL=300` - Report metrics every 5 minutes
- `ALERT_WEBHOOK_URL` - Optional webhook for alerts

## Usage Commands

### Basic Usage
```bash
# Start recording HASH-USD with debug logging
uv run bidaskrecord --debug record HASH-USD | tee -a bidask.log

# Background mode with PID file
nohup uv run bidaskrecord record HASH-USD > bidask-$(date +%Y%m%d-%H%M%S).log 2>&1 &
echo $! > bidask-recorder.pid
```

### Monitoring
```bash
# Check if running
pgrep -f "bidaskrecord record" && echo "Running" || echo "Not running"

# Check recent database activity
sqlite3 market_data.db "SELECT COUNT(*) FROM bid_ask WHERE created_at > datetime('now', '-1 hour');"

# View recent logs
tail -20 bidask.log
```

### Health Indicators
**Healthy Operation:**
- Regular "Health check passed" messages
- "Heartbeat pong received" every 30 seconds
- "Saved order book update" and "Saved trade" messages
- Metrics reports showing increasing data counts

**Warning Signs:**
- Heartbeat timeout messages
- "No data received for too long, forcing reconnect"
- Frequent reconnection attempts

## Technical Architecture

### Data Flow
1. WebSocket connects to Figure Markets Exchange
2. Subscribes to ORDER_BOOK and TRADES channels for specified symbols
3. Processes incoming messages and converts denomination units
4. Stores bid/ask and trade data in SQLite database
5. Monitors connection health and automatically reconnects

### Reliability Features
- **Unlimited Reconnection**: Never gives up, exponential backoff
- **Health Monitoring**: Detects stale connections and forces reconnection
- **Database Safety**: Proper transaction handling and rollback on errors
- **Metrics Tracking**: Comprehensive monitoring of all system components
- **Alerting**: Webhook notifications for critical issues

### Database Schema
- **Asset**: Trading pair definitions with denomination conversion (microUSD/nanoHASH)
- **OrderBook**: **Unified table** containing all order book levels with:
  * Full depth (all bid/ask levels with ranking)
  * Pre-computed display values (proper precision)
  * Cost calculations (level and cumulative)
  * Duplicate detection support
  * Consistent timestamps for all levels
- **Trade**: Individual trade records with full details
- **DenomReference**: Denomination metadata and conversion factors

## Development Notes

### Dependencies Management
- Uses `uv` for fast Python package management
- Key dependencies: SQLAlchemy, websockets, pydantic, click, aiohttp
- Pre-commit hooks configured for code quality

### Code Quality
- Black formatting, isort import sorting
- Pylint and mypy type checking (with some existing issues)
- Structured logging with context

### Testing
- `test_websocket.py` - Manual WebSocket testing script
- Logs output to `test_output/` directory

## Troubleshooting

### Common Issues
1. **ModuleNotFoundError**: Run `uv pip install -e .` to reinstall in editable mode
2. **Connection failures**: Check network connectivity to figuremarkets.com
3. **Database issues**: Verify file permissions and disk space
4. **High memory usage**: Monitor with `ps aux | grep bidaskrecord`

### Log Analysis
```bash
# Error analysis
grep -i error bidask.log | tail -20

# Connection patterns
grep -E "(Connected|Disconnected|Retry)" bidask.log

# Performance metrics
grep "Metrics summary" bidask.log | tail -5
```

## Next Steps & Potential Improvements

### Completed ✅
- [x] Fix syntax errors and code formatting
- [x] Implement unlimited retry capability
- [x] Add robust database session management
- [x] Create health monitoring system
- [x] Build comprehensive metrics and alerting
- [x] Add missing dependencies
- [x] Create usage documentation

### Completed Major Milestones ✅
- [x] Fix syntax errors and code formatting
- [x] Implement unlimited retry capability
- [x] Add robust database session management
- [x] Create health monitoring system
- [x] Build comprehensive metrics and alerting
- [x] Add missing dependencies
- [x] Create usage documentation
- [x] **Implement unified order_book table**
- [x] **Remove unnecessary exchange_timestamp column**
- [x] **Add full order book depth recording**
- [x] **Implement duplicate detection**
- [x] **Fix precision requirements (3 decimals, whole tokens, whole USD)**
- [x] **Clean database schema (4 tables)**
- [x] **Test and verify database writes**

### Future Enhancements (if needed)
- [ ] Add email alerting (webhook alerts currently implemented)
- [ ] Implement database connection pooling for high throughput
- [ ] Add support for multiple exchanges
- [ ] Create web dashboard for monitoring
- [ ] Add data export/analysis tools
- [ ] Implement data compression for long-term storage

## Important Notes
- The application is designed for continuous 24/7 operation
- All major reliability concerns have been addressed
- Monitoring and alerting provide proactive issue detection
- Database operations are transaction-safe with proper error handling
- The system will automatically recover from most network issues

## User's Goal
The user wanted a utility that can run 24/7, reconnects when needed, regularly retries if the server goes down, and does its very best to record market data from Figure Markets Exchange. This has been fully implemented and tested.

## Current Status & Usage

### Database Schema
**Clean 4-table design:**
- `asset` (1 record: HASH-USD with microUSD/nanoHASH denominations)
- `denom_reference` (denomination metadata)
- `order_book` (unified table with complete market depth)
- `trade` (individual trades)

### Verified Working Features
- ✅ Full order book depth recording (all levels)
- ✅ Duplicate detection (only saves changes)
- ✅ Proper precision formatting (prices: 3 decimals, quantities: whole, costs: whole USD)
- ✅ Consistent timestamps across all levels
- ✅ Complete database writes tested and verified

### Last Command to Run
```bash
uv run bidaskrecord --debug record HASH-USD | tee -a bidask.log
```

This starts the recorder with the new unified schema. System verified to save complete order book snapshots (33 levels recorded successfully).
