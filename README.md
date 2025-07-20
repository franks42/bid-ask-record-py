# Bid-Ask Recorder for Figure Markets

A Python-based utility that records real-time bid and ask prices from Figure Markets Exchange WebSocket feed with comprehensive trade-to-orderbook correlation analysis.

## Features

- **Real-time Data Collection**: WebSocket connection to Figure Markets Exchange
- **Comprehensive Storage**: Trades and order book data with display-friendly values
- **24/7 Reliability**: Unlimited reconnection with exponential backoff
- **Trade-Order Book Correlation**: Analyze how trades impact liquidity and price formation
- **Blockchain-Aware Analysis**: Handle atomic transaction execution and temporal correlation challenges
- **Production Monitoring**: Health checks, metrics, and alerting capabilities
- **Database Views**: Pre-built views for easy querying of bids, asks, and trade impacts

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/franks42/bid-ask-record-py.git
   cd bid-ask-record-py
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. Configure the application by creating a `.env` file (see `.env.example` for reference)
2. Run the application:
   ```bash
   python -m bidaskrecord
   ```

## Configuration

Create a `.env` file in the project root with the following variables:

```
# WebSocket configuration
WEBSOCKET_URL=wss://figuremarkets.com/service-hft-exchange-websocket/ws/v1

# Database configuration
DATABASE_URL=sqlite:///market_data.db

# Logging configuration
LOG_LEVEL=INFO
LOG_FILE=bidaskrecord.log
```

## Trade-Order Book Analysis

This system provides sophisticated analysis of how trades correlate with order book changes. Key tools include:

### Database Views
- `order_book_asks_view` - Clean ask data with display values
- `order_book_bids_view` - Clean bid data with display values
- `trade_orderbook_impact_view` - Trades with before/after order book context
- `blockchain_blocks_view` - Groups trades by blockchain block timestamp

### Analysis Scripts
- `trade_impact_analysis.py` - Analyze specific trade impacts
- `blockchain_aware_analysis.py` - Handle temporal correlation challenges
- `query_order_book_examples.py` - Example queries for order book data

### Critical Insight: Temporal Data Correlation

**⚠️ IMPORTANT: Blockchain vs. API Timestamp Challenges**

When analyzing decentralized exchange data, we discovered a fundamental challenge:

#### The Problem:
1. **Atomic Blockchain Execution**: Multiple trades execute in the same blockchain block with order book updates happening atomically
2. **Timestamp Mismatch**:
   - Trade timestamps are authoritative (from blockchain)
   - Order book timestamps are our `received_at` (when we received the data)
   - No blockchain block numbers provided by Figure Markets API
   - Order book updates arrive ~100-200ms after trade notifications

#### The Solution:
- **Group trades by identical timestamps** (same blockchain block)
- **Analyze aggregate impact** of all trades in a block
- **Use fuzzy time windows** for order book correlation
- **Examine liquidity consumption** to determine trade direction

#### Example Discovery:
```
Blockchain Block 2025-07-20 22:09:21.089046:
├── Trade 1: $0.030 × 13 HASH = $0.39
├── Trade 2: $0.029 × 7374 HASH = $213.85
└── Total Impact: 7387 HASH consumed from bid side ✓

Order Book Change: Exactly 7387 HASH removed from bids
```

This forensic approach ensures accurate analysis despite temporal data correlation challenges inherent in decentralized exchange APIs.

#### Trade Direction Detection:
The system can reliably determine whether trades were **buy orders** or **sell orders** through forensic analysis:

- **SELL orders** consume liquidity from the **bid side** (sellers "hit the bids")
- **BUY orders** consume liquidity from the **ask side** (buyers "hit the asks")

By examining which side of the order book lost liquidity, we can definitively determine trade direction even without explicit order type information from the exchange.

#### Understanding DEX Trade Mechanics:
A key insight: **trades are not separate transactions** but rather the result of order overlap resolution:

1. **Order Submission**: New orders (market/limit) are submitted to the blockchain
2. **Overlap Detection**: Matching engine finds overlapping bid/ask orders
3. **Atomic Settlement**: All changes (order book updates + asset transfers + trade events) commit together in a single block
4. **Trade Events**: What we see as "trades" are actually settlement events from overlapping orders

#### Forensic Analysis Limitations:
While we can determine trade direction and settlement outcomes, several details remain hidden:

**What We Can Detect:**
- Trade direction (buy vs sell) via liquidity consumption analysis
- Settlement quantities and prices
- Atomic block-level execution patterns
- Order book impact and price formation

**What Remains Hidden:**
- **Order Types**: Market vs limit vs stop-loss orders
- **Fill Conditions**: Fill-or-kill, immediate-or-cancel, partial fills allowed
- **Order Management**: Whether trades represent complete fills or partial fills of larger orders
- **Hidden Orders**: Iceberg orders or other non-displayed liquidity
- **Unfilled Portions**: What happens to unmatched order quantities

This represents the fundamental limitation of external market analysis - we can perform "market archaeology" on settlement events, but the full order management layer remains proprietary to the exchange.

## Development

1. Install with uv:
   ```bash
   uv pip install -e .
   ```

2. Run the recorder:
   ```bash
   uv run bidaskrecord record HASH-USD
   ```

3. Analyze trade impacts:
   ```bash
   uv run python trade_impact_analysis.py
   uv run python blockchain_aware_analysis.py
   ```

4. Create database views:
   ```bash
   uv run python create_order_book_views.py
   ```

## License

MIT
