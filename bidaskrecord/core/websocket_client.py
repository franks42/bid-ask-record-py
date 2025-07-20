"""WebSocket client for connecting to Figure Markets Exchange."""

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import websockets
from websockets.exceptions import (
    ConnectionClosedError,
    ConnectionClosedOK,
    WebSocketException,
)

from bidaskrecord.config.settings import get_settings
from bidaskrecord.models.base import get_db
from bidaskrecord.models.market_data import Asset, Trade
from bidaskrecord.models.order_book import OrderBook
from bidaskrecord.models.order_book_raw import OrderBookRaw
from bidaskrecord.utils.logging import get_logger
from bidaskrecord.utils.metrics import get_metrics_tracker, start_metrics_reporting

logger = get_logger(__name__)

MessageHandler = Callable[[Dict[str, Any]], Awaitable[None]]


class WebSocketClient:
    """
    WebSocket client for connecting to Figure Markets Exchange.

    CONNECTION BEHAVIOR:
    - Figure Markets requires WebSocket protocol pings for keepalive (every 61 seconds)
    - FM does NOT respond to WebSocket pings with pongs (one-way keepalive)
    - FM does NOT support JSON ping/pong ({"action":"PING"} gets rejected)
    - FM sends order book snapshots every 30 seconds regardless of changes
    - Duplicate detection is essential to filter identical snapshots
    """

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
        self.subscribed_symbols: List[str] = []

        # Get settings for health monitoring
        self.settings = get_settings()
        self.heartbeat_interval = self.settings.HEARTBEAT_INTERVAL
        self.heartbeat_timeout = self.settings.HEARTBEAT_TIMEOUT
        self.health_check_interval = self.settings.CONNECTION_HEALTH_CHECK_INTERVAL
        self.max_no_data_seconds = self.settings.MAX_NO_DATA_SECONDS

        # Health monitoring state
        self.last_heartbeat_sent = 0.0
        self.last_heartbeat_received = 0.0
        self.consecutive_heartbeat_failures = 0
        self.health_monitor_task: Optional[asyncio.Task] = None
        self.heartbeat_task: Optional[asyncio.Task] = None
        self.metrics_task: Optional[asyncio.Task] = None
        self.listen_task: Optional[asyncio.Task] = None

        # Metrics tracking
        self.metrics = get_metrics_tracker()

        logger.debug(
            "WebSocketClient initialized",
            websocket_url=self.websocket_url,
            reconnect_delay=self.reconnect_delay,
            max_retries=self.max_retries,
            health_monitoring=True,
        )

    async def connect(self) -> None:
        """Connect to the WebSocket server and handle reconnection logic."""
        while True:
            try:
                logger.info("Connecting to WebSocket", url=self.websocket_url)
                self.metrics.record_connection_attempt()
                self.websocket = await websockets.connect(
                    self.websocket_url,
                    ping_interval=25,  # WebSocket protocol ping every 25 seconds (FM times out ~30-40s)
                    ping_timeout=10,
                    close_timeout=5,
                )
                self.connected = True
                self.retry_count = 0  # Reset retry count on successful connection
                self.reconnect_delay = 5  # Reset backoff delay
                self.last_message_time = time.time()
                self.metrics.record_successful_connection()

                logger.info("WebSocket connected successfully")

                # Resubscribe to any previously subscribed symbols
                if self.subscribed_symbols:
                    await self.subscribe(self.subscribed_symbols)

                # Start health monitoring (WebSocket pings handle keepalive automatically)
                self.health_monitor_task = asyncio.create_task(self._health_monitor())

                # Start metrics reporting if enabled
                if self.settings.MONITORING_ENABLED and not self.metrics_task:
                    self.metrics_task = asyncio.create_task(
                        start_metrics_reporting(
                            self.settings.METRICS_REPORTING_INTERVAL
                        )
                    )

                # Start listening for messages as a background task
                self.listen_task = asyncio.create_task(self._listen())

                # Return after setting up the connection
                return

            except (ConnectionRefusedError, OSError) as e:
                logger.error("Connection refused, will retry", error=str(e))
                self.metrics.record_failed_connection()
                await self._handle_connection_error()
            except WebSocketException as e:
                logger.error("WebSocket error", error=str(e))
                self.metrics.record_failed_connection()
                await self._handle_connection_error()
            except Exception as e:
                logger.error("Unexpected error", error=str(e), exc_info=True)
                self.metrics.record_failed_connection()
                await self._handle_connection_error()

    async def disconnect(self) -> None:
        """Disconnect from the WebSocket server."""
        logger.info("Disconnecting from WebSocket")
        self.connected = False
        self.metrics.record_disconnect()

        # Cancel health monitoring task
        if (
            hasattr(self, "health_monitor_task")
            and self.health_monitor_task
            and not self.health_monitor_task.done()
        ):
            self.health_monitor_task.cancel()
            try:
                await self.health_monitor_task
            except asyncio.CancelledError:
                pass

        if self.metrics_task and not self.metrics_task.done():
            self.metrics_task.cancel()
            try:
                await self.metrics_task
            except asyncio.CancelledError:
                pass

        if self.listen_task and not self.listen_task.done():
            self.listen_task.cancel()
            try:
                await self.listen_task
            except asyncio.CancelledError:
                pass

        # Close websocket connection
        if self.websocket:
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
            json_message = json.dumps(message)
            await self.websocket.send(json_message)
            logger.info("JSON message sent: %s", json_message)
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

                # WebSocket protocol pings handle keepalive automatically every 61 seconds

        except ConnectionClosedOK:
            logger.info("WebSocket connection closed normally")
        except ConnectionClosedError as e:
            logger.error("WebSocket connection closed with error", error=str(e))
            await self._handle_connection_error()
        except Exception as e:
            logger.error("Error in WebSocket listener", error=str(e), exc_info=True)
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

        # Check if we should stop retrying (only if max_retries > 0)
        if self.max_retries > 0 and self.retry_count >= self.max_retries:
            logger.error(
                "Max retries reached, giving up",
                retry_count=self.retry_count,
                max_retries=self.max_retries,
            )
            return

        retry_info = (
            f"{self.retry_count}/{self.max_retries}"
            if self.max_retries > 0
            else f"{self.retry_count}/unlimited"
        )
        logger.info(
            "Attempting to reconnect",
            attempt=retry_info,
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
            # Log ALL incoming messages with action/channel info
            msg_info = f"action={message.get('action')}, channel={message.get('channel')}, keys={list(message.keys())}"
            logger.info(f"RECEIVED MESSAGE: {msg_info}")

            # Special alert for any PING messages
            if message.get("action") == "PING":
                logger.error("!!!!! FM SENT US A PING MESSAGE !!!!!")

            self.last_message_time = time.time()

            # Handle different message types from Figure Markets
            channel = message.get("channel")

            if channel == "ORDER_BOOK" or ("bids" in message and "asks" in message):
                self.metrics.record_message_received("order_book")
                await self._handle_order_book_update(message)
            elif (
                channel == "TRADES"
                and "id" in message
                and "price" in message
                and "quantity" in message
            ):
                self.metrics.record_message_received("trade")
                await self._handle_trade_update(message)
            elif "type" in message and message["type"] == "error":
                self.metrics.record_message_received("error")
                logger.error(
                    "Received error from server: %s",
                    message.get("message", "Unknown error"),
                )
            elif "type" in message and message["type"] == "subscriptions":
                self.metrics.record_message_received("subscription")
                logger.info("Subscription update: %s", message.get("channels", []))
            else:
                self.metrics.record_message_received("unknown")
                # Log unrecognized messages but keep processing
                msg_keys = (
                    list(message.keys()) if isinstance(message, dict) else "not_dict"
                )
                logger.warning(
                    "Unrecognized message format - continuing anyway",
                    keys=msg_keys,
                    message_preview=str(message)[:200],
                )

        except Exception as e:
            logger.error("Error in message handler: %s", str(e), exc_info=True)

    async def _handle_order_book_update(self, data: Dict[str, Any]) -> None:
        """
        Handle order book update messages using unified order_book table.

        IMPORTANT: Figure Markets sends order book snapshots every 30 seconds
        regardless of whether the data has changed. This is their standard
        behavior - not caused by any client activity. Many of these messages
        will be duplicates when the market is inactive. Our duplicate detection
        system efficiently filters these out.

        Args:
            data: The order book update data.
        """
        channel_uuid = data.get("channelUuid")
        if not channel_uuid:
            logger.warning("Received order book update without channelUuid", data=data)
            return

        # Use proper database session context manager
        try:
            with next(get_db()) as db:
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

                # Process full order book from the message
                bids = data.get("bids", [])
                asks = data.get("asks", [])

                if not bids and not asks:
                    logger.debug("No bids or asks in order book update")
                    return

                # Check if this order book is different from the last one using new raw table
                logger.info(
                    f"DUPLICATE CHECK: Checking asset {asset.id} with {len(bids)} bids, {len(asks)} asks"
                )
                if OrderBookRaw.is_duplicate(db, asset.id, data):
                    logger.info(
                        "DUPLICATE DETECTED: Order book unchanged, skipping duplicate save"
                    )
                    return
                logger.info("NO DUPLICATE: Order book changed, proceeding to save")

                # Generate consistent received timestamp for all levels
                received_timestamp = datetime.utcnow()

                # Store raw data first (this also confirms it's not a duplicate)
                is_new_data, raw_entry = OrderBookRaw.create_if_changed(
                    db, asset.id, received_timestamp, data
                )
                if not is_new_data:
                    logger.info("Raw data duplicate detected, should not happen here")
                    return

                # Get next snapshot ID for this asset
                last_snapshot = (
                    db.query(OrderBook.snapshot_id)
                    .filter(OrderBook.asset_id == asset.id)
                    .order_by(OrderBook.snapshot_id.desc())
                    .first()
                )
                snapshot_id = (last_snapshot[0] + 1) if last_snapshot else 1

                # Process bid levels
                bid_count = 0
                for rank, bid in enumerate(bids, 1):
                    if isinstance(bid, dict):
                        price = bid.get("price")
                        quantity = bid.get("quantity")
                        cumulative_qty = bid.get("total")
                        total_orders = bid.get("totalOrders")
                    else:
                        # Handle array format [price, quantity]
                        price = bid[0] if len(bid) > 0 else None
                        quantity = bid[1] if len(bid) > 1 else None
                        cumulative_qty = None
                        total_orders = None

                    if price is not None and quantity is not None:
                        order_book_entry = OrderBook.from_exchange_data(
                            asset=asset,
                            snapshot_id=snapshot_id,
                            channel_uuid=channel_uuid,
                            received_at=received_timestamp,
                            side="bid",
                            level_rank=rank,
                            price=price,
                            quantity=quantity,
                            cumulative_quantity=cumulative_qty,
                            total_orders=total_orders,
                        )
                        db.add(order_book_entry)
                        bid_count += 1

                # Process ask levels
                ask_count = 0
                for rank, ask in enumerate(asks, 1):
                    if isinstance(ask, dict):
                        price = ask.get("price")
                        quantity = ask.get("quantity")
                        cumulative_qty = ask.get("total")
                        total_orders = ask.get("totalOrders")
                    else:
                        # Handle array format [price, quantity]
                        price = ask[0] if len(ask) > 0 else None
                        quantity = ask[1] if len(ask) > 1 else None
                        cumulative_qty = None
                        total_orders = None

                    if price is not None and quantity is not None:
                        order_book_entry = OrderBook.from_exchange_data(
                            asset=asset,
                            snapshot_id=snapshot_id,
                            channel_uuid=channel_uuid,
                            received_at=received_timestamp,
                            side="ask",
                            level_rank=rank,
                            price=price,
                            quantity=quantity,
                            cumulative_quantity=cumulative_qty,
                            total_orders=total_orders,
                        )
                        db.add(order_book_entry)
                        ask_count += 1

                db.commit()
                self.metrics.record_database_write(success=True)

                logger.info(
                    "Saved order book change",
                    symbol=symbol,
                    snapshot_id=snapshot_id,
                    bid_levels=bid_count,
                    ask_levels=ask_count,
                    best_bid=bids[0].get("price")
                    if bids and isinstance(bids[0], dict)
                    else (bids[0][0] if bids else None),
                    best_ask=asks[0].get("price")
                    if asks and isinstance(asks[0], dict)
                    else (asks[0][0] if asks else None),
                )

        except Exception as e:
            self.metrics.record_database_write(success=False)
            logger.error(
                "Error in order book update handler", error=str(e), exc_info=True
            )

    async def _handle_trade_update(self, data: Dict[str, Any]) -> None:
        """
        Handle trade update messages with proper database session management.

        Args:
            data: The trade update data.
        """
        channel_uuid = data.get("channelUuid")
        trade_id = data.get("id")

        if not channel_uuid or not trade_id:
            logger.warning("Received trade update without required fields", data=data)
            return

        # Use proper database session context manager
        try:
            with next(get_db()) as db:
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

                # Create trade record with display values
                trade = Trade.create_with_display_values(
                    trade_id=trade_id,
                    asset=asset,
                    price=price,
                    quantity=quantity,
                    trade_time=datetime.fromisoformat(created.replace("Z", "+00:00")),
                    channel_uuid=channel_uuid,
                    raw_data=data,
                )

                db.add(trade)
                db.commit()
                self.metrics.record_database_write(success=True)

                logger.info(
                    "Saved trade",
                    trade_id=trade_id,
                    symbol=symbol,
                    price=price,
                    quantity=quantity,
                    timestamp=created,
                )

        except Exception as e:
            self.metrics.record_database_write(success=False)
            logger.error("Error in trade update handler", error=str(e), exc_info=True)

    async def _health_monitor(self) -> None:
        """Monitor connection health and force reconnect if needed."""
        logger.info("Health monitor started")

        try:
            while self.connected:
                await asyncio.sleep(self.health_check_interval)

                if not self.connected:
                    break

                current_time = time.time()

                # Check if we've received data recently
                time_since_last_message = current_time - self.last_message_time
                if time_since_last_message > self.max_no_data_seconds:
                    logger.warning(
                        "No data received for too long, forcing reconnect",
                        seconds_since_last_message=time_since_last_message,
                        max_no_data_seconds=self.max_no_data_seconds,
                    )
                    self.metrics.record_forced_reconnect()
                    await self._force_reconnect()
                    break

                # Check heartbeat health
                if self.consecutive_heartbeat_failures >= 3:
                    logger.warning(
                        "Too many consecutive heartbeat failures, forcing reconnect",
                        consecutive_failures=self.consecutive_heartbeat_failures,
                    )
                    self.metrics.record_forced_reconnect()
                    await self._force_reconnect()
                    break

                self.metrics.record_health_check()
                logger.debug(
                    "Health check passed",
                    seconds_since_last_message=time_since_last_message,
                    heartbeat_failures=self.consecutive_heartbeat_failures,
                )

        except asyncio.CancelledError:
            logger.info("Health monitor cancelled")
            raise
        except Exception as e:
            logger.error("Error in health monitor", error=str(e), exc_info=True)

    async def _heartbeat_monitor(self) -> None:
        """Send periodic heartbeats and monitor responses."""
        logger.info("Heartbeat monitor started")

        try:
            while self.connected:
                await asyncio.sleep(self.heartbeat_interval)

                if not self.connected or not self.websocket:
                    break

                try:
                    # Monitoring for FM's heartbeat pings (they may have longer intervals)
                    self.last_heartbeat_sent = time.time()
                    self.metrics.record_heartbeat_sent()
                    logger.info(
                        "Heartbeat monitor active (waiting for FM's ping - could be 5-15 minutes)"
                    )

                    # Assume connection is healthy for now
                    self.last_heartbeat_received = time.time()
                    self.consecutive_heartbeat_failures = 0
                    self.metrics.record_heartbeat_received()

                except Exception as e:
                    self.consecutive_heartbeat_failures += 1
                    self.metrics.record_heartbeat_failure()
                    logger.warning(
                        "JSON heartbeat failed",
                        error=str(e),
                        consecutive_failures=self.consecutive_heartbeat_failures,
                    )

        except asyncio.CancelledError:
            logger.info("Heartbeat monitor cancelled")
            raise
        except Exception as e:
            logger.error("Error in heartbeat monitor", error=str(e), exc_info=True)

    async def _force_reconnect(self) -> None:
        """Force a reconnection by closing the current connection."""
        logger.info("Forcing reconnection")
        self.connected = False

        if self.websocket:
            try:
                await self.websocket.close()
            except Exception:
                pass
            self.websocket = None
