# Bid-Ask Recorder for Figure Markets

A Python-based utility that records real-time bid and ask prices from Figure Markets Exchange WebSocket feed.

## Features

- Real-time WebSocket connection to Figure Markets Exchange
- Persistent storage of market data in SQLite database
- Automatic reconnection on connection drops
- Configurable logging
- Robust error handling and recovery

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

## Development

1. Install development dependencies:
   ```bash
   pip install -r requirements-dev.txt
   ```

2. Run tests:
   ```bash
   pytest
   ```

3. Format code:
   ```bash
   black .
   isort .
   ```

## License

MIT