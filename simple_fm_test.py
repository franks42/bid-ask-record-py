#!/usr/bin/env python3
"""
Ultra-simple FM WebSocket test - Monitor native WebSocket ping/pong AND JSON messages
"""

import asyncio
import json
import logging
from datetime import datetime

import websockets


class PingPongLogger:
    """Custom logger to intercept WebSocket ping/pong frames."""

    def __init__(self):
        self.ping_count = 0
        self.pong_count = 0

    def log_ping_sent(self):
        self.ping_count += 1
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{timestamp}] >>> WEBSOCKET PING SENT (#{self.ping_count})")

    def log_pong_received(self):
        self.pong_count += 1
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{timestamp}] <<< WEBSOCKET PONG RECEIVED (#{self.pong_count})")

    def log_ping_received(self):
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{timestamp}] <<< WEBSOCKET PING RECEIVED FROM FM!")

    def log_pong_sent(self):
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{timestamp}] >>> WEBSOCKET PONG SENT TO FM!")


async def test_fm_websocket():
    """Connect to FM WebSocket and log everything received."""
    url = "wss://figuremarkets.com/service-hft-exchange-websocket/ws/v1"

    print(f"[{datetime.now()}] Connecting to {url}")
    print("Will monitor native WebSocket ping/pong AND JSON messages...")

    ping_logger = PingPongLogger()

    try:
        # Connect with automatic pings to see if FM responds to protocol pings
        websocket = await websockets.connect(
            url,
            ping_interval=25,  # Send protocol pings every 25 seconds
            ping_timeout=10,
            close_timeout=5,
        )

        print(f"[{datetime.now()}] Connected successfully!")
        print("WebSocket protocol pings enabled every 25 seconds")

        # Override ping handler to detect incoming pings from FM
        original_ping = websocket.ping
        original_pong = websocket.pong

        async def logged_ping(*args, **kwargs):
            ping_logger.log_ping_sent()
            return await original_ping(*args, **kwargs)

        async def logged_pong(*args, **kwargs):
            ping_logger.log_pong_sent()
            return await original_pong(*args, **kwargs)

        websocket.ping = logged_ping
        websocket.pong = logged_pong

        # Send ONLY a subscription to ORDER_BOOK
        import time
        import uuid

        subscription = {
            "action": "SUBSCRIBE",
            "channel": "ORDER_BOOK",
            "symbol": "HASH-USD",
            "channelUuid": str(uuid.uuid4()),
            "timestamp": int(time.time() * 1000),
        }

        await websocket.send(json.dumps(subscription))
        print(f"[{datetime.now()}] Sent subscription: {subscription}")

        print("Now listening for messages...")
        print("Monitoring both JSON messages AND WebSocket protocol ping/pong...")

        message_count = 0

        # Listen for incoming messages
        async for message in websocket:
            message_count += 1
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]

            try:
                # Parse JSON
                data = json.loads(message)

                # Log message info
                action = data.get("action", "None")
                channel = data.get("channel", "None")
                msg_type = data.get("type", "None")
                keys = list(data.keys())

                print(f"[{timestamp}] MSG #{message_count}")
                print(f"  action={action}, channel={channel}, type={msg_type}")
                print(f"  keys={keys}")

                # Always show full message content (truncated if too long)
                full_msg = str(data)
                if len(full_msg) > 200:
                    print(f"  CONTENT: {full_msg[:200]}...")
                else:
                    print(f"  CONTENT: {full_msg}")

                # Special alerts
                if action == "PING":
                    print("  *** FM SENT A JSON PING! ***")
                if action == "PONG":
                    print("  *** FM SENT A JSON PONG! ***")
                if "bids" in data and "asks" in data:
                    bid_count = len(data.get("bids", []))
                    ask_count = len(data.get("asks", []))
                    print(f"  ORDER BOOK: {bid_count} bids, {ask_count} asks")
                if "message" in data and "code" in data:
                    print(
                        f"  ERROR RESPONSE: message='{data.get('message')}' code={data.get('code')}"
                    )

                print()  # Empty line for readability

            except json.JSONDecodeError as e:
                print(f"[{timestamp}] NON-JSON MESSAGE: {message}")
                print()

    except Exception as e:
        print(f"[{datetime.now()}] ERROR: {e}")


if __name__ == "__main__":
    print("=== SIMPLE FM WEBSOCKET TEST ===")
    print(
        "This script subscribes to ORDER_BOOK and monitors WebSocket protocol ping/pong"
    )
    print("WebSocket pings every 25 seconds to keep connection alive")
    print()

    asyncio.run(test_fm_websocket())
