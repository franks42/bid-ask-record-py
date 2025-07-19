"""Metrics tracking and monitoring for the bid-ask recorder."""

import asyncio
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Dict, Optional

import aiohttp

from bidaskrecord.config.settings import get_settings
from bidaskrecord.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ConnectionMetrics:
    """Connection-related metrics."""

    total_connections: int = 0
    successful_connections: int = 0
    failed_connections: int = 0
    reconnect_attempts: int = 0
    current_uptime_start: Optional[float] = None
    total_uptime_seconds: float = 0.0
    last_disconnect_time: Optional[float] = None


@dataclass
class DataMetrics:
    """Data processing metrics."""

    total_messages_received: int = 0
    order_book_updates: int = 0
    trade_updates: int = 0
    error_messages: int = 0
    invalid_messages: int = 0
    database_writes: int = 0
    database_errors: int = 0
    last_data_received: Optional[float] = None


@dataclass
class HealthMetrics:
    """Health monitoring metrics."""

    heartbeat_sent: int = 0
    heartbeat_received: int = 0
    heartbeat_failures: int = 0
    consecutive_heartbeat_failures: int = 0
    health_checks_performed: int = 0
    forced_reconnects: int = 0


class MetricsTracker:
    """Tracks and manages application metrics."""

    def __init__(self):
        """Initialize the metrics tracker."""
        self.settings = get_settings()
        self.connection_metrics = ConnectionMetrics()
        self.data_metrics = DataMetrics()
        self.health_metrics = HealthMetrics()
        self.start_time = time.time()

        # Alert state
        self._last_alert_time = 0.0
        self._alert_cooldown = 300  # 5 minutes between alerts

    def record_connection_attempt(self) -> None:
        """Record a connection attempt."""
        self.connection_metrics.total_connections += 1

    def record_successful_connection(self) -> None:
        """Record a successful connection."""
        self.connection_metrics.successful_connections += 1
        self.connection_metrics.current_uptime_start = time.time()
        logger.info(
            "Recorded successful connection",
            total=self.connection_metrics.total_connections,
            successful=self.connection_metrics.successful_connections,
        )

    def record_failed_connection(self) -> None:
        """Record a failed connection."""
        self.connection_metrics.failed_connections += 1

    def record_reconnect_attempt(self) -> None:
        """Record a reconnection attempt."""
        self.connection_metrics.reconnect_attempts += 1

    def record_disconnect(self) -> None:
        """Record a disconnection."""
        current_time = time.time()
        self.connection_metrics.last_disconnect_time = current_time

        # Add to total uptime if we were connected
        if self.connection_metrics.current_uptime_start:
            uptime = current_time - self.connection_metrics.current_uptime_start
            self.connection_metrics.total_uptime_seconds += uptime
            self.connection_metrics.current_uptime_start = None

    def record_message_received(self, message_type: str = "unknown") -> None:
        """Record a received message."""
        self.data_metrics.total_messages_received += 1
        self.data_metrics.last_data_received = time.time()

        if message_type == "order_book":
            self.data_metrics.order_book_updates += 1
        elif message_type == "trade":
            self.data_metrics.trade_updates += 1
        elif message_type == "error":
            self.data_metrics.error_messages += 1
        elif message_type == "invalid":
            self.data_metrics.invalid_messages += 1

    def record_database_write(self, success: bool = True) -> None:
        """Record a database write attempt."""
        if success:
            self.data_metrics.database_writes += 1
        else:
            self.data_metrics.database_errors += 1

    def record_heartbeat_sent(self) -> None:
        """Record a heartbeat sent."""
        self.health_metrics.heartbeat_sent += 1

    def record_heartbeat_received(self) -> None:
        """Record a heartbeat response received."""
        self.health_metrics.heartbeat_received += 1
        self.health_metrics.consecutive_heartbeat_failures = 0

    def record_heartbeat_failure(self) -> None:
        """Record a heartbeat failure."""
        self.health_metrics.heartbeat_failures += 1
        self.health_metrics.consecutive_heartbeat_failures += 1

    def record_health_check(self) -> None:
        """Record a health check performed."""
        self.health_metrics.health_checks_performed += 1

    def record_forced_reconnect(self) -> None:
        """Record a forced reconnection."""
        self.health_metrics.forced_reconnects += 1

    def get_current_uptime(self) -> float:
        """Get current uptime in seconds."""
        if self.connection_metrics.current_uptime_start:
            return time.time() - self.connection_metrics.current_uptime_start
        return 0.0

    def get_total_runtime(self) -> float:
        """Get total runtime in seconds."""
        return time.time() - self.start_time

    def get_connection_success_rate(self) -> float:
        """Get connection success rate as percentage."""
        total = self.connection_metrics.total_connections
        if total == 0:
            return 0.0
        return (self.connection_metrics.successful_connections / total) * 100

    def get_heartbeat_success_rate(self) -> float:
        """Get heartbeat success rate as percentage."""
        total = self.health_metrics.heartbeat_sent
        if total == 0:
            return 0.0
        return (self.health_metrics.heartbeat_received / total) * 100

    def get_summary(self) -> Dict:
        """Get a summary of all metrics."""
        current_time = time.time()
        current_uptime = self.get_current_uptime()
        total_runtime = self.get_total_runtime()

        return {
            "timestamp": datetime.now().isoformat(),
            "runtime_seconds": total_runtime,
            "current_uptime_seconds": current_uptime,
            "connection": {
                **asdict(self.connection_metrics),
                "success_rate_percent": self.get_connection_success_rate(),
                "current_uptime_seconds": current_uptime,
            },
            "data": {
                **asdict(self.data_metrics),
                "seconds_since_last_data": (
                    current_time - self.data_metrics.last_data_received
                    if self.data_metrics.last_data_received
                    else None
                ),
            },
            "health": {
                **asdict(self.health_metrics),
                "heartbeat_success_rate_percent": self.get_heartbeat_success_rate(),
            },
        }

    def should_alert(self) -> bool:
        """Check if we should send an alert (respects cooldown)."""
        current_time = time.time()
        return (current_time - self._last_alert_time) > self._alert_cooldown

    async def send_alert_if_needed(
        self, message: str, severity: str = "warning"
    ) -> None:
        """Send alert if conditions warrant it."""
        if not self.should_alert():
            return

        # Check alert conditions
        should_alert = False
        alert_reasons = []

        # Check connection issues
        if self.connection_metrics.failed_connections > 5:
            should_alert = True
            alert_reasons.append(
                f"High connection failures: {self.connection_metrics.failed_connections}"
            )

        # Check data flow issues
        current_time = time.time()
        if (
            self.data_metrics.last_data_received
            and current_time - self.data_metrics.last_data_received > 600
        ):  # 10 minutes
            should_alert = True
            alert_reasons.append("No data received for over 10 minutes")

        # Check heartbeat issues
        if self.health_metrics.consecutive_heartbeat_failures >= 5:
            should_alert = True
            alert_reasons.append(
                f"Consecutive heartbeat failures: {self.health_metrics.consecutive_heartbeat_failures}"
            )

        if should_alert:
            self._last_alert_time = current_time
            alert_message = f"{message}. Issues: {'; '.join(alert_reasons)}"
            await self._send_alert(alert_message, severity)

    async def _send_alert(self, message: str, severity: str) -> None:
        """Send alert via configured channels."""
        alert_data = {
            "timestamp": datetime.now().isoformat(),
            "severity": severity,
            "message": message,
            "metrics_summary": self.get_summary(),
        }

        # Log the alert
        logger.warning("ALERT", severity=severity, message=message)

        # Send webhook alert if configured
        webhook_url = getattr(self.settings, "ALERT_WEBHOOK_URL", "")
        if webhook_url:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        webhook_url,
                        json=alert_data,
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as response:
                        if response.status == 200:
                            logger.info("Alert sent successfully to webhook")
                        else:
                            logger.warning(
                                f"Alert webhook returned status {response.status}"
                            )
            except Exception as e:
                logger.error(f"Failed to send webhook alert: {e}")

        # TODO: Add email alerts if configured
        # email = getattr(self.settings, 'ALERT_EMAIL', '')
        # if email:
        #     await self._send_email_alert(email, alert_data)


# Global metrics instance
_metrics_tracker: Optional[MetricsTracker] = None


def get_metrics_tracker() -> MetricsTracker:
    """Get the global metrics tracker instance."""
    global _metrics_tracker
    if _metrics_tracker is None:
        _metrics_tracker = MetricsTracker()
    return _metrics_tracker


async def start_metrics_reporting(interval: int = 300) -> None:
    """Start periodic metrics reporting."""
    metrics = get_metrics_tracker()

    while True:
        try:
            await asyncio.sleep(interval)
            summary = metrics.get_summary()
            logger.info("Metrics summary", **summary)

            # Check for alert conditions
            await metrics.send_alert_if_needed("Periodic metrics check")

        except asyncio.CancelledError:
            logger.info("Metrics reporting cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in metrics reporting: {e}", exc_info=True)
