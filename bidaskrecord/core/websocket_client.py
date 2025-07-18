"""WebSocket client for connecting to Figure Markets Exchange."""

import asyncio
import json
import time
from typing import Any, Dict, Optional, Callable, Awaitable, List, Tuple

import websockets
from websockets.exceptions import (
    ConnectionClosedError,
    ConnectionClosedOK,
    WebSocketException,
)

from bidaskrecord.config.settings import get_settings
from bidaskrecord.utils.logging import get_logger
from bidaskrecord.db import get_db
from bidaskrecord.models.market_data import Asset, BidAskData

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
        self.websocket_url = websocket_url
        self.reconnect_delay = reconnect_delay
        self.max_retries = max_retries
        self.message_handler = message_handler or self.default_message_handler
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.connected = False
        self.retry_count = 0
        self.last_message_time = 0.0
        self.heartbeat_interval = 30  # seconds
        self.subscribed_symbols: List[str] = []
    
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
    
    async def subscribe(self, symbols: List[str]) -> None:
        """
        Subscribe to market data for the given symbols.
        
        Args:
            symbols: List of asset symbols to subscribe to.
        """
        if not symbols:
            return
            
        self.subscribed_symbols = list(set(self.subscribed_symbols + symbols))
        
        # Example subscription message - adjust based on Figure Markets API
        subscription_msg = {
            "type": "subscribe",
            "channels": ["orderbook"],
            "symbols": symbols
        }
        
        await self.send_message(subscription_msg)
    
    async def unsubscribe(self, symbols: List[str]) -> None:
        """
        Unsubscribe from market data for the given symbols.
        
        Args:
            symbols: List of asset symbols to unsubscribe from.
        """
        if not symbols:
            return
            
        self.subscribed_symbols = [s for s in self.subscribed_symbols if s not in symbols]
        
        # Example unsubscription message - adjust based on Figure Markets API
        unsubscription_msg = {
            "type": "unsubscribe",
            "channels": ["orderbook"],
            "symbols": symbols
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
                    logger.error("Failed to decode message", error=str(e), message=message)
                except Exception as e:
                    logger.error("Error processing message", error=str(e), exc_info=True)
                    
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
        logger.debug("Received message", message=message)
        
        # Handle different message types from Figure Markets
        if "type" in message:
            if message["type"] == "orderbook":
                await self._handle_order_book_update(message)
            elif message["type"] == "trade":
                await self._handle_trade_update(message)
            elif message["type"] == "subscriptions":
                logger.info("Subscription update", subscriptions=message.get("channels", []))
            elif message["type"] == "error":
                logger.error("Received error from server", error=message.get("message", "Unknown error"))
        
        # Handle order book updates (bids/asks)
        elif "bids" in message and "asks" in message:
            await self._handle_order_book_update(message)
    
    async def _handle_order_book_update(self, data: Dict[str, Any]) -> None:
        """
        Handle order book update messages.
        
        Args:
            data: The order book update data.
        """
        try:
            symbol = data.get("symbol")
            if not symbol:
                logger.warning("Received order book update without symbol", data=data)
                return
                
            timestamp = data.get("timestamp", time.time() * 1000)  # Default to current time in ms
            
            with next(get_db()) as db:
                # Get or create the asset
                asset = db.query(Asset).filter(Asset.symbol == symbol).first()
                if not asset:
                    asset = Asset(symbol=symbol, name=symbol)
                    db.add(asset)
                    db.commit()
                    db.refresh(asset)
                
                # Process bids
                for bid in data.get("bids", []):
                    bid_record = BidAskData(
                        asset_id=asset.id,
                        exchange_timestamp=timestamp,
                        bid_price=float(bid.get("price", 0)),
                        bid_size=float(bid.get("size", 0)),
                        ask_price=0,  # Will be updated by asks
                        ask_size=0,   # Will be updated by asks
                        raw_data=bid
                    )
                    db.add(bid_record)
                
                # Process asks
                for ask in data.get("asks", []):
                    ask_record = BidAskData(
                        asset_id=asset.id,
                        exchange_timestamp=timestamp,
                        bid_price=0,  # Will be updated by bids
                        bid_size=0,   # Will be updated by bids
                        ask_price=float(ask.get("price", 0)),
                        ask_size=float(ask.get("size", 0)),
                        raw_data=ask
                    )
                    db.add(ask_record)
                
                db.commit()
                logger.debug("Saved order book update", symbol=symbol, 
                           bid_count=len(data.get("bids", [])), 
                           ask_count=len(data.get("asks", [])))
                
        except Exception as e:
            logger.error("Error processing order book update", error=str(e), exc_info=True)
    
    async def _handle_trade_update(self, data: Dict[str, Any]) -> None:
        """
        Handle trade update messages.
        
        Args:
            data: The trade update data.
        """
        logger.debug("Received trade update", trade=data)
        # Implement trade update handling if needed
        # This is a placeholder for future implementation
