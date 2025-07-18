#!/usr/bin/env python3
"""Test script to verify WebSocket connection to Figure Markets Exchange."""

import asyncio
import json
import logging
import os
import random
import signal
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import websockets
from websockets.exceptions import (
    ConnectionClosed,
    ConnectionClosedError,
    ConnectionClosedOK,
    WebSocketException,
)
from websockets.typing import Data

# Create output directory for logs and data
OUTPUT_DIR = Path("test_output")
OUTPUT_DIR.mkdir(exist_ok=True)

# Configure logging
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("websockets.client")
logger.setLevel(logging.DEBUG)

# Console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)

# File handler
log_file = OUTPUT_DIR / f"websocket_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
file_handler = logging.FileHandler(log_file)
file_handler.setFormatter(log_formatter)
logger.addHandler(file_handler)

# Message storage for analysis
received_messages: List[Dict[str, Any]] = []

# WebSocket URL
WEBSOCKET_URL = "wss://figuremarkets.com/service-hft-exchange-websocket/ws/v1"

import uuid
from datetime import datetime

# Generate a channel UUID for this session
CHANNEL_UUID = str(uuid.uuid4())

# Define all available channels we want to test
AVAILABLE_CHANNELS = [
    "ORDER_BOOK",  # Order book updates (bids/asks)
    "TRADES",      # Trade executions
    "TICKER",      # 24hr ticker statistics
    "CANDLES_1m",  # 1-minute candles
    "CANDLES_5m",  # 5-minute candles
    "CANDLES_15m", # 15-minute candles
    "DEPTH",       # Market depth
    "AGG_TRADE"    # Aggregate trade information
]

# Create subscription messages for all available channels
TEST_MESSAGES = [
    {
        "action": "SUBSCRIBE",
        "channel": channel,
        "symbol": "HASH-USD",
        "channelUuid": str(uuid.uuid4()),
        "timestamp": int(datetime.utcnow().timestamp() * 1000)
    }
    for channel in AVAILABLE_CHANNELS
]

# Also try a batch subscription message
BATCH_SUBSCRIBE = {
    "action": "SUBSCRIBE",
    "subscriptions": [
        {"channel": channel, "symbol": "HASH-USD"}
        for channel in AVAILABLE_CHANNELS
    ],
    "timestamp": int(datetime.utcnow().timestamp() * 1000)
}

# Add the batch subscription to test if it's supported
TEST_MESSAGES.append(BATCH_SUBSCRIBE)

def save_messages() -> None:
    """Save received messages to a JSON file for analysis."""
    if not received_messages:
        return
        
    output_file = OUTPUT_DIR / f"websocket_messages_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump(received_messages, f, indent=2)
    logger.info(f"Saved {len(received_messages)} messages to {output_file}")

def format_order_book(book_data: dict) -> str:
    """Format order book data for display."""
    if not book_data:
        return "No order book data"
        
    output = []
    
    # Format bids
    if 'bids' in book_data and book_data['bids']:
        output.append("=== BIDS ===")
        for bid in book_data['bids'][:5]:  # Show top 5 bids
            price, size = bid
            output.append(f"BID: {price:>10} x {size:>10}")
    
    # Format asks
    if 'asks' in book_data and book_data['asks']:
        output.append("\n=== ASKS ===")
        for ask in book_data['asks'][:5]:  # Show top 5 asks
            price, size = ask
            output.append(f"ASK: {price:>10} x {size:>10}")
    
    return "\n".join(output)

async def _receive_messages(websocket) -> None:
    """Helper method to receive and log messages."""
    from colorama import init, Fore, Style
    init()
    
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                received_messages.append({
                    "timestamp": datetime.now().isoformat(),
                    "data": data
                })
                
                # Log the raw message first
                logger.info(f"\n{Fore.CYAN}=== RAW MESSAGE ==={Style.RESET_ALL}")
                logger.info(f"{message}")
                
                # ============================================
                # MESSAGE TYPE DETECTION
                # ============================================
                # Different message types have different structures:
                # 1. Order Book Updates: Have 'bids' and 'asks' arrays, identified by channelUuid
                # 2. Trade Messages: Have 'channel': 'TRADES' and trade details
                # 3. Other messages: May have 'type' field or other identifiers
                # ============================================
                
                # Extract common fields with defaults
                msg_type = data.get("type", "")
                channel = data.get("channel", "")
                channel_uuid = data.get("channelUuid", "")
                symbol = data.get("symbol", "HASH-USD")  # Default to HASH-USD if not specified
                
                # Log basic message info
                logger.info(f"\n{Fore.GREEN}=== MESSAGE ==={Style.RESET_ALL}")
                if channel:
                    logger.info(f"Channel: {Fore.YELLOW}{channel}{Style.RESET_ALL}")
                if channel_uuid:
                    logger.info(f"Channel UUID: {Fore.YELLOW}{channel_uuid}{Style.RESET_ALL}")
                if symbol:
                    logger.info(f"Symbol:  {Fore.YELLOW}{symbol}{Style.RESET_ALL}")
                
                # ============================================
                # HANDLE DIFFERENT MESSAGE TYPES
                # ============================================
                
                # 1. TRADE MESSAGES
                # -----------------------------
                # Format: {"channel": "TRADES", "id": "...", "price": 0.031, ...}
                if channel == "TRADES":
                    logger.info(f"{Fore.YELLOW}=== TRADE EXECUTED ==={Style.RESET_ALL}")
                    logger.info(f"Trade ID: {data.get('id')}")
                    logger.info(f"Price:    {data.get('price')}")
                    logger.info(f"Quantity: {data.get('quantity')}")
                    logger.info(f"Time:     {data.get('created')}")
                    
                    # TODO: Save trade to database
                    # await save_trade_to_db(data)
                
                # 2. ORDER BOOK UPDATES
                # -----------------------------
                # Format: {"channelUuid": "...", "bids": [...], "asks": [...]}
                elif 'bids' in data or 'asks' in data:
                    logger.info(f"{Fore.CYAN}=== ORDER BOOK UPDATE ==={Style.RESET_ALL}")
                    logger.info(f"Bids: {len(data.get('bids', []))} levels")
                    logger.info(f"Asks: {len(data.get('asks', []))} levels")
                    
                    # Show top of book for quick reference
                    if data.get('bids'):
                        best_bid = data['bids'][0]
                        logger.info(f"Best Bid: {best_bid['price']} x {best_bid['quantity']}")
                    if data.get('asks'):
                        best_ask = data['asks'][0]
                        logger.info(f"Best Ask: {best_ask['price']} x {best_ask['quantity']}")
                
                # 3. CANDLE MESSAGES
                # -----------------------------
                # Format: {"channel": "CANDLES_1m", "data": {...}}
                elif channel and channel.startswith("CANDLES_"):
                    logger.info(f"{Fore.MAGENTA}=== CANDLE UPDATE ({channel}) ==={Style.RESET_ALL}")
                    if 'data' in data:
                        logger.info(f"Candle: {data['data']}")
                
                # 4. TICKER MESSAGES
                # -----------------------------
                # Format: {"channel": "TICKER", "data": {...}}
                elif channel == "TICKER":
                    logger.info(f"{Fore.CYAN}=== TICKER UPDATE ==={Style.RESET_ALL}")
                    if 'data' in data:
                        ticker = data['data']
                        logger.info(f"Last Price: {ticker.get('lastPrice')}")
                        logger.info(f"24h Change: {ticker.get('priceChangePercent')}%")
                        logger.info(f"24h Volume: {ticker.get('volume')}")
                
                # 5. AGGREGATE TRADE MESSAGES
                # -----------------------------
                # Format: {"channel": "AGG_TRADE", "data": {...}}
                elif channel == "AGG_TRADE":
                    logger.info(f"{Fore.YELLOW}=== AGGREGATE TRADE ==={Style.RESET_ALL}")
                    if 'data' in data:
                        trade = data['data']
                        logger.info(f"Price: {trade.get('p')}  Qty: {trade.get('q')}")
                
                # 6. DEPTH MESSAGES
                # -----------------------------
                # Format: {"channel": "DEPTH", "data": {...}}
                elif channel == "DEPTH":
                    logger.info(f"{Fore.BLUE}=== DEPTH UPDATE ==={Style.RESET_ALL}")
                    if 'data' in data:
                        depth = data['data']
                        logger.info(f"Last Update ID: {depth.get('lastUpdateId')}")
                        logger.info(f"Bids: {len(depth.get('bids', []))} levels")
                        logger.info(f"Asks: {len(depth.get('asks', []))} levels")
                
                # 7. OTHER MESSAGE TYPES
                # -----------------------------
                # Handle any other message types we might receive
                elif msg_type:
                    logger.info(f"{Fore.BLUE}=== {msg_type.upper()} MESSAGE ==={Style.RESET_ALL}")
                else:
                    logger.info(f"{Fore.BLUE}=== UNKNOWN MESSAGE TYPE ==={Style.RESET_ALL}")
                    logger.info(f"Available keys: {', '.join(data.keys())}")
                    if 'data' in data and isinstance(data['data'], dict):
                        logger.info(f"Data keys: {', '.join(data['data'].keys())}")
                
                # Log the full message for debugging
                logger.info(f"{Fore.BLUE}=== FULL MESSAGE ==={Style.RESET_ALL}")
                
                # Print all data for inspection
                logger.info(f"\n{Fore.BLUE}=== FULL MESSAGE ==={Style.RESET_ALL}")
                logger.info(json.dumps(data, indent=2))
                
                # Save messages periodically
                if len(received_messages) % 5 == 0:  # Save more frequently
                    save_messages()
                    
            except json.JSONDecodeError:
                logger.warning(f"\n{Fore.RED}=== NON-JSON MESSAGE ==={Style.RESET_ALL}")
                logger.warning(f"{message}")
                received_messages.append({
                    "timestamp": datetime.now().isoformat(),
                    "raw_message": message
                })
    except Exception as e:
        logger.error(f"Error in message receiver: {e}", exc_info=True)
    finally:
        # Save all messages when done
        save_messages()

async def test_websocket_connection(max_reconnect_attempts: int = 10) -> None:
    """Test WebSocket connection with automatic reconnection.
    
    Args:
        max_reconnect_attempts: Maximum number of reconnection attempts before giving up.
                               Set to None for unlimited attempts.
    """
    reconnect_attempt = 0
    last_reconnect_time = 0
    
    while max_reconnect_attempts is None or reconnect_attempt < max_reconnect_attempts:
        try:
            # Calculate backoff time (exponential backoff with jitter)
            if reconnect_attempt > 0:
                backoff = min(60, (2 ** reconnect_attempt) + random.random() * 2)
                if time.time() - last_reconnect_time < backoff:
                    await asyncio.sleep(backoff)
            
            last_reconnect_time = time.time()
            
            logger.info(f"Connecting to WebSocket (attempt {reconnect_attempt + 1})...")
            
            async with websockets.connect(
                WEBSOCKET_URL,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=5,
                max_queue=10000,  # Increase queue size for high-frequency messages
                # Try with different protocols if needed
                # subprotocols=["json"],
            ) as websocket:
                logger.info("WebSocket connected successfully")
                logger.info(f"WebSocket protocol: {websocket.subprotocol}")
                
                # Reset reconnect attempt counter on successful connection
                reconnect_attempt = 0
                
                # Send periodic status updates
                status_task = asyncio.create_task(_send_status_updates(websocket))
                
                try:
                    # First, wait for any welcome or initial messages
                    logger.info("Waiting for initial messages...")
                    try:
                        initial_msg = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                        logger.info(f"Initial message: {initial_msg}")
                        try:
                            initial_data = json.loads(initial_msg)
                            logger.info("Initial message (parsed):")
                            logger.info(json.dumps(initial_data, indent=2))
                            
                            # If the initial message contains connection info, use it
                            if isinstance(initial_data, dict):
                                if 'sessionId' in initial_data:
                                    logger.info(f"Session ID: {initial_data['sessionId']}")
                                if 'heartbeat' in initial_data:
                                    logger.info(f"Heartbeat interval: {initial_data['heartbeat']}ms")
                        except json.JSONDecodeError:
                            logger.info(f"Initial message is not JSON: {initial_msg}")
                    except asyncio.TimeoutError:
                        logger.info("No initial message received")
                    
                    # Test different message formats
                    await _send_test_messages(websocket)
                    
                    # Start receiving messages
                    logger.info("Starting to listen for messages...")
                    try:
                        await _receive_messages(websocket)
                    except websockets.exceptions.ConnectionClosed as e:
                        logger.warning(f"WebSocket connection closed: {e}")
                        logger.info("Will attempt to reconnect...")
                        raise  # Will be caught by the outer try/except
                    
                    # If we get here, the connection was closed cleanly
                    logger.info("WebSocket connection closed by server")
                    return  # Exit successfully
                    
                except asyncio.CancelledError:
                    logger.info("Operation cancelled")
                    raise
                    
                except Exception as e:
                    logger.error(f"Error in WebSocket connection: {e}", exc_info=True)
                    raise
                    
                except (websockets.exceptions.WebSocketException, OSError) as e:
                    reconnect_attempt += 1
                    if max_reconnect_attempts is not None and reconnect_attempt >= max_reconnect_attempts:
                        logger.error(f"Max reconnection attempts ({max_reconnect_attempts}) reached. Giving up.")
                        raise
                        
                    logger.warning(f"Connection attempt {reconnect_attempt} failed: {e}")
                    logger.info("Attempting to reconnect...")
                    
                except Exception as e:
                    logger.error(f"Unexpected error: {e}", exc_info=True)
                    raise
            
        finally:
            # Cancel the status update task if it's still running
            if 'status_task' in locals():
                status_task.cancel()
                try:
                    await status_task
                except asyncio.CancelledError:
                    pass

async def _send_test_messages(websocket) -> None:
    """Send test subscription messages with retry logic."""
    for msg in TEST_MESSAGES:
        retry_count = 0
        max_retries = 3
        
        while retry_count < max_retries:
            try:
                if isinstance(msg, dict):
                    msg_str = json.dumps(msg)
                    logger.info(f"Sending message: {msg_str}")
                    await websocket.send(msg_str)
                    
                    # Wait for a short time between messages
                    await asyncio.sleep(0.1)
                    
                    # Check for immediate response
                    try:
                        response = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                        logger.info(f"Response: {response}")
                        break  # Message sent successfully
                    except asyncio.TimeoutError:
                        logger.info("No immediate response received")
                        break  # No response but message was sent
                    except Exception as e:
                        logger.warning(f"Error reading response: {e}")
                        retry_count += 1
                        if retry_count < max_retries:
                            logger.info(f"Retrying message ({retry_count}/{max_retries})...")
                            await asyncio.sleep(1)  # Wait before retry
                            
            except Exception as e:
                logger.error(f"Error sending message (attempt {retry_count + 1}): {e}")
                retry_count += 1
                if retry_count >= max_retries:
                    logger.error(f"Failed to send message after {max_retries} attempts: {msg}")
                    break
                await asyncio.sleep(1)  # Wait before retry

async def _send_status_updates(websocket, interval: int = 300) -> None:
    """Send periodic status updates to keep the connection alive and log status."""
    start_time = time.time()
    message_count = 0
    
    try:
        while True:
            await asyncio.sleep(interval)
            
            # Log status
            uptime = time.time() - start_time
            hours, remainder = divmod(uptime, 3600)
            minutes, seconds = divmod(remainder, 60)
            
            logger.info(
                f"Status: Running for {int(hours)}h {int(minutes)}m {int(seconds)}s, "
                f"Messages received: {message_count}"
            )
            
            # Send a ping to keep the connection alive
            try:
                await websocket.ping()
            except Exception as e:
                logger.warning(f"Error sending ping: {e}")
                raise  # This will trigger a reconnection
                
            except asyncio.CancelledError:
                logger.info("Status updates cancelled")
                logger.warning(f"Connection attempt {reconnect_attempt} failed: {e}")
                logger.info("Attempting to reconnect...")
                
            except Exception as e:
                logger.error(f"Unexpected error: {e}", exc_info=True)
                raise

async def main() -> None:
    """Run the WebSocket test."""
    logger.info(f"Starting WebSocket test at {datetime.now().isoformat()}")
    logger.info(f"Logging to file: {log_file.absolute()}")
    
    # Set up signal handler for graceful shutdown
    loop = asyncio.get_running_loop()
    stop = loop.create_future()
    loop.add_signal_handler(signal.SIGINT, stop.set_result, None)
    
    try:
        # Run the WebSocket test
        test_task = asyncio.create_task(test_websocket_connection())
        
        # Wait for either the test to complete or a signal to stop
        done, pending = await asyncio.wait(
            [test_task, stop],
            return_when=asyncio.FIRST_COMPLETED
        )
        
        # Clean up
        if test_task in pending:
            logger.info("Cancelling test task...")
            test_task.cancel()
            try:
                await test_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Test completed")
        
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
    finally:
        # Ensure all messages are saved
        save_messages()
        logger.info(f"Test completed at {datetime.now().isoformat()}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        sys.exit(1)
