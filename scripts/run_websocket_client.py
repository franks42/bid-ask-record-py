"""Run the WebSocket client with database persistence."""

import asyncio
import logging
import sys
import uuid
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bidaskrecord.config.settings import get_settings
from bidaskrecord.core.websocket_client import WebSocketClient
from bidaskrecord.models.base import get_db, init_db
from bidaskrecord.models.market_data import Asset
from bidaskrecord.utils.logging import configure_logging

# Configure logging
configure_logging()
logger = logging.getLogger(__name__)


async def main():
    """Initialize the database and run the WebSocket client."""
    # Initialize database
    logger.info("Initializing database...")
    init_db()

    # Get settings
    settings = get_settings()

    # Ensure we have the HASH-USD asset in the database
    db = next(get_db())
    try:
        asset = db.query(Asset).filter(Asset.symbol == "HASH-USD").first()
        if not asset:
            logger.info("Creating HASH-USD asset...")
            asset = Asset.create_asset(
                symbol="HASH-USD",
                base_price_denom="microUSD",
                base_size_denom="nanoHASH",
                display_price_denom="USD",
                display_size_denom="HASH",
                price_decimals=6,  # microUSD (6 decimals)
                size_decimals=9,  # nanoHASH (9 decimals)
                name="HASH-USD Trading Pair",
            )
            db.add(asset)
            db.commit()
            logger.info(f"Created asset: {asset}")
    except Exception as e:
        logger.error(f"Error initializing asset: {e}")
        db.rollback()
        raise
    finally:
        db.close()

    # Create and run WebSocket client
    logger.info("Starting WebSocket client...")
    logger.info(f"Connecting to WebSocket URL: {settings.WEBSOCKET_URL}")
    client = WebSocketClient(
        websocket_url=settings.WEBSOCKET_URL,
        reconnect_delay=settings.WEBSOCKET_RECONNECT_DELAY,
        max_retries=settings.WEBSOCKET_MAX_RETRIES,
    )

    try:
        # Start the client
        client_task = asyncio.create_task(client.connect())

        # Give it a moment to connect
        await asyncio.sleep(2)

        # Subscribe to order book and trades for HASH-USD
        symbol = "HASH-USD"
        channels = ["ORDER_BOOK", "TRADES"]

        logger.info(f"Subscribing to {symbol} for channels: {channels}")
        await client.subscribe(symbols=[symbol], channels=channels)

        # Keep the client running
        logger.info("WebSocket client is running. Press Ctrl+C to stop.")
        await client_task

    except asyncio.CancelledError:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Error in main: {e}", exc_info=True)
    finally:
        await client.disconnect()
        logger.info("WebSocket client stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
