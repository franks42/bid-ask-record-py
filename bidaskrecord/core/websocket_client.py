"""WebSocket client for connecting to Figure Markets Exchange."""

import asyncio
import json
import time
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import websockets
from websockets.exceptions import (
    ConnectionClosedError,
    ConnectionClosedOK,
    WebSocketException,
)

from bidaskrecord.config.settings import get_settings
from bidaskrecord.db import get_db
from bidaskrecord.models.market_data import Asset, BidAsk, Trade
from bidaskrecord.utils.logging import get_logger

logger = get_logger(__name__)

MessageHandler = Callable[[Dict[str, Any]], Awaitable[None]]


class WebSocketClient:
    """WebSocket client for connecting to Figure Markets Exchange."""

    def __init__(
        self,
        websocket_url: str,
        reconnect_delay: int = 5,
        max_retries: int = 10,
        message_handler: Optional[MessageHandler] = None,
    ) -> None:
        """
        Initialize the WebSocket client.

        Args:
            websocket_url: The WebSocket URL to connect to.
            reconnect_delay: Delay between reconnection attempts in seconds.
            max_retries: Maximum number of connection retries before giving up.
            message_handler: Optional custom message handler.
        """
        # Convert from UPPER_SNAKE_CASE to instance variables
        self.websocket_url = websocket_url
        self.reconnect_delay = int(reconnect_delay)  # Ensure it's an int
        self.max_retries = int(max_retries)  # Ensure it's an int
        self.message_handler = message_handler or self.default_message_handler
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.connected = False
        self.retry_count = 0
        self.last_message_time = 0.0
        self.heartbeat_interval = 30  # seconds
        self.subscribed_symbols: List[str] = []

        logger.debug(
            "WebSocketClient initialized",
            websocket_url=self.websocket_url,
            reconnect_delay=self.reconnect_delay,
            max_retries=self.max_retries,
        )

    async def connect(self) -> None:
        """Connect to the WebSocket server and handle reconnection logic."""
        while True:
            try:
                logger.info("Connecting to WebSocket", url=self.websocket_url)
                self.websocket = await websockets.connect(
                    self.websocket_url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                )
                self.connected = True
                self.retry_count = 0
                self.last_message_time = time.time()

                logger.info("WebSocket connected")

                # Resubscribe to any previously subscribed symbols
                if self.subscribed_symbols:
                    await self.subscribe(self.subscribed_symbols)

                # Start listening for messages
                await self._listen()

            except (ConnectionRefusedError, OSError) as e:
                logger.error("Connection refused, will retry", error=str(e))
                await self._handle_connection_error()
            except WebSocketException as e:
                logger.error("WebSocket error", error=str(e))
                await self._handle_connection_error()
            except Exception as e:
                logger.error("Unexpected error", error=str(e), exc_info=True)
                await self._handle_connection_error()

    async def disconnect(self) -> None:
        """Disconnect from the WebSocket server."""
        if self.websocket and self.connected:
            logger.info("Disconnecting from WebSocket")
            self.connected = False
            await self.websocket.close()
            logger.info("WebSocket disconnected")

    async def subscribe(self, symbols: List[str], channels: List[str] = None) -> None:
        """
        Subscribe to market data for the given symbols and channels.

        Args:
            symbols: List of asset symbols to subscribe to.
            channels: List of channels to subscribe to (e.g., ["ORDER_BOOK", "TRADES"]).
        """
        if not symbols or not channels:
            return

        self.subscribed_symbols = list(set(self.subscribed_symbols + symbols))

        # Create subscription message according to Figure Markets API
        timestamp = int(time.time() * 1000)

        for symbol in symbols:
            for channel in channels:
                subscription_msg = {
                    "action": "SUBSCRIBE",
                    "channel": channel,
                    "symbol": symbol,
                    "channelUuid": str(uuid.uuid4()),
                    "timestamp": timestamp,
                }
                await self.send_message(subscription_msg)
                logger.info(f"Subscribed to {channel} for {symbol}")

    async def unsubscribe(self, symbols: List[str]) -> None:
        """
        Unsubscribe from market data for the given symbols.

        Args:
            symbols: List of asset symbols to unsubscribe from.
        """
        if not symbols:
            return

        self.subscribed_symbols = [
            s for s in self.subscribed_symbols if s not in symbols
        ]

        # Example unsubscription message - adjust based on Figure Markets API
        unsubscription_msg = {
            "type": "unsubscribe",
            "channels": ["orderbook"],
            "symbols": symbols,
        }

        await self.send_message(unsubscription_msg)

    async def send_message(self, message: Dict[str, Any]) -> None:
        """
        Send a message to the WebSocket server.

        Args:
            message: The message to send (will be JSON-encoded).
        """
        if not self.connected or not self.websocket:
            logger.warning("Cannot send message, WebSocket is not connected")
            return

        try:
            await self.websocket.send(json.dumps(message))
            logger.debug("Message sent", message=message)
        except ConnectionClosedError:
            logger.warning("Connection closed while sending message")
            await self._handle_connection_error()
        except Exception as e:
            logger.error("Error sending message", error=str(e))

    async def _listen(self) -> None:
        """Listen for incoming WebSocket messages."""
        if not self.websocket:
            return

        try:
            async for message in self.websocket:
                self.last_message_time = time.time()
                try:
                    data = json.loads(message)
                    await self.message_handler(data)
                except json.JSONDecodeError as e:
                    logger.error(
                        "Failed to decode message", error=str(e), message=message
                    )
                except Exception as e:
                    logger.error(
                        "Error processing message", error=str(e), exc_info=True
                    )

                # Check if we need to send a heartbeat
                if time.time() - self.last_message_time > self.heartbeat_interval:
                    await self._send_heartbeat()

        except ConnectionClosedOK:
            logger.info("WebSocket connection closed normally")
        except ConnectionClosedError as e:
            logger.error("WebSocket connection closed with error", error=str(e))
            await self._handle_connection_error()
        except Exception as e:
            logger.error("Error in WebSocket listener", error=str(e), exc_info=True)
            await self._handle_connection_error()

    async def _send_heartbeat(self) -> None:
        """Send a heartbeat/ping message to keep the connection alive."""
        if not self.connected or not self.websocket:
            return

        try:
            await self.websocket.ping()
            self.last_message_time = time.time()
            logger.debug("Heartbeat sent")
        except Exception as e:
            logger.error("Error sending heartbeat", error=str(e))
            await self._handle_connection_error()

    async def _handle_connection_error(self) -> None:
        """Handle WebSocket connection errors and attempt reconnection."""
        self.connected = False

        if self.websocket:
            try:
                await self.websocket.close()
            except Exception:
                pass
            self.websocket = None

        self.retry_count += 1

        if 0 < self.max_retries <= self.retry_count:
            logger.error("Max retries reached, giving up")
            return

        logger.info(
            "Attempting to reconnect",
            attempt=f"{self.retry_count}/{self.max_retries}",
            delay=f"{self.reconnect_delay}s",
        )

        await asyncio.sleep(self.reconnect_delay)
        # Exponential backoff for subsequent retries
        self.reconnect_delay = min(60, self.reconnect_delay * 1.5)
        await self.connect()

    async def default_message_handler(self, message: Dict[str, Any]) -> None:
        """
        Default message handler for WebSocket messages.

        Args:
            message: The received message (already parsed as JSON).
        """
        try:
            logger.debug("Received message: %s", message)

            # Handle different message types from Figure Markets
            channel = message.get("channel")

            if channel == "ORDER_BOOK" or ("bids" in message and "asks" in message):
                await self._handle_order_book_update(message)
            elif (
                channel == "TRADES"
                and "id" in message
                and "price" in message
                and "quantity" in message
            ):
                await self._handle_trade_update(message)
            elif "type" in message and message["type"] == "error":
                logger.error(
                    "Received error from server: %s",
                    message.get("message", "Unknown error"),
                )
            elif "type" in message and message["type"] == "subscriptions":
                logger.info("Subscription update: %s", message.get("channels", []))
            else:
                logger.debug("Unhandled message type: %s", message)

        except Exception as e:
            logger.error("Error in message handler: %s", str(e), exc_info=True)

    async def _handle_order_book_update(self, data: Dict[str, Any]) -> None:
        """
        Handle order book update messages.

        Args:
            data: The order book update data.
        """
        try:
            channel_uuid = data.get("channelUuid")
            if not channel_uuid:
                logger.warning(
                    "Received order book update without channelUuid", data=data
                )
                return

            # Get database session
            db = next(get_db())
            try:
                # Get or create the asset (assuming first symbol in subscribed symbols)
                symbol = (
                    self.subscribed_symbols[0]
                    if self.subscribed_symbols
                    else "HASH-USD"
                )
                asset = db.query(Asset).filter(Asset.symbol == symbol).first()
                if not asset:
                    logger.warning(f"Asset not found for symbol: {symbol}")
                    return

                # Process best bid/ask from the order book
                bids = data.get("bids", [])
                asks = data.get("asks", [])

                if not bids or not asks:
                    logger.debug("No bids or asks in order book update")
                    return

                # Get best bid (first in the list is the best price)
                best_bid = (
                    bids[0]
                    if isinstance(bids[0], dict)
                    else {"price": bids[0][0], "quantity": bids[0][1]}
                )
                best_ask = (
                    asks[0]
                    if isinstance(asks[0], dict)
                    else {"price": asks[0][0], "quantity": asks[0][1]}
                )

                # Create bid/ask record
                bidask = BidAsk(
                    asset_id=asset.id,
                    exchange_timestamp=Decimal(str(data.get("timestamp", time.time()))),
                    bid_price_amount=asset.to_base_price(best_bid["price"]),
                    ask_price_amount=asset.to_base_price(best_ask["price"]),
                    bid_size_amount=asset.to_base_size(best_bid["quantity"]),
                    ask_size_amount=asset.to_base_size(best_ask["quantity"]),
                    channel_uuid=channel_uuid,
                    raw_data=data,
                )

                db.add(bidask)
                db.commit()

                logger.debug(
                    "Saved order book update",
                    symbol=symbol,
                    bid_price=best_bid["price"],
                    ask_price=best_ask["price"],
                    bid_size=best_bid["quantity"],
                    ask_size=best_ask["quantity"],
                )

            except Exception as e:
                db.rollback()
                logger.error(
                    "Error processing order book update", error=str(e), exc_info=True
                )
                raise
            finally:
                db.close()

        except Exception as e:
            logger.error(
                "Error in order book update handler", error=str(e), exc_info=True
            )

    async def _handle_trade_update(self, data: Dict[str, Any]) -> None:
        """
        Handle trade update messages.

        Args:
            data: The trade update data.
        """
        try:
            channel_uuid = data.get("channelUuid")
            trade_id = data.get("id")

            if not channel_uuid or not trade_id:
                logger.warning(
                    "Received trade update without required fields", data=data
                )
                return

            # Get database session
            db = next(get_db())
            try:
                # Get or create the asset (assuming first symbol in subscribed symbols)
                symbol = (
                    self.subscribed_symbols[0]
                    if self.subscribed_symbols
                    else "HASH-USD"
                )
                asset = db.query(Asset).filter(Asset.symbol == symbol).first()
                if not asset:
                    logger.warning(f"Asset not found for symbol: {symbol}")
                    return

                # Check if trade already exists
                existing_trade = (
                    db.query(Trade).filter(Trade.trade_id == trade_id).first()
                )
                if existing_trade:
                    logger.debug(f"Trade {trade_id} already exists, skipping")
                    return

                # Parse trade data
                price = data.get("price")
                quantity = data.get("quantity")
                created = data.get("created")

                if not all([price, quantity, created]):
                    logger.warning("Trade data is missing required fields", data=data)
                    return

                # Create trade record
                trade = Trade(
                    trade_id=trade_id,
                    asset_id=asset.id,
                    price_amount=asset.to_base_price(price),
                    quantity_amount=asset.to_base_size(quantity),
                    trade_time=datetime.fromisoformat(created.replace("Z", "+00:00")),
                    channel_uuid=channel_uuid,
                    raw_data=data,
                )

                db.add(trade)
                db.commit()

                logger.info(
                    "Saved trade",
                    trade_id=trade_id,
                    symbol=symbol,
                    price=price,
                    quantity=quantity,
                    timestamp=created,
                )

            except Exception as e:
                db.rollback()
                logger.error(
                    "Error processing trade update", error=str(e), exc_info=True
                )
                raise
            finally:
                db.close()

        except Exception as e:
            logger.error("Error in trade update handler", error=str(e), exc_info=True)
