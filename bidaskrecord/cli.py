"""Command-line interface for the Bid-Ask Recorder."""

import asyncio
import signal
from typing import List, Optional

import click
from dotenv import load_dotenv

from bidaskrecord import __version__
from bidaskrecord.config.settings import get_settings
from bidaskrecord.core.websocket_client import WebSocketClient
from bidaskrecord.models.base import init_db
from bidaskrecord.utils.logging import get_logger

logger = get_logger(__name__)


@click.group()
@click.version_option(version=__version__)
@click.option("--debug", is_flag=True, help="Enable debug logging")
@click.pass_context
def cli(ctx: click.Context, debug: bool) -> None:
    """Bid-Ask Recorder - Record market data from Figure Markets Exchange."""
    # Load environment variables
    load_dotenv()

    # Set up context
    ctx.ensure_object(dict)
    ctx.obj["settings"] = get_settings()

    # Configure debug logging if needed
    if debug:
        import logging

        logging.basicConfig(level=logging.DEBUG)
        logger.debug("Debug logging enabled")


@cli.command()
@click.argument("symbols", nargs=-1, required=True)
@click.option("--daemon", is_flag=True, help="Run in daemon mode (background)")
@click.pass_context
def record(ctx: click.Context, symbols: List[str], daemon: bool) -> None:
    """Record market data for the specified symbols."""
    settings = ctx.obj["settings"]

    # Initialize database
    logger.info("Initializing database")
    init_db()

    # Create and run the WebSocket client
    async def run() -> None:
        client = WebSocketClient(
            websocket_url=settings.WEBSOCKET_URL,
            reconnect_delay=settings.WEBSOCKET_RECONNECT_DELAY,
            max_retries=settings.WEBSOCKET_MAX_RETRIES,
        )

        # Set up signal handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(
                sig, lambda: asyncio.create_task(client.disconnect())
            )

        try:
            # Connect and subscribe to symbols
            await client.connect()
            await client.subscribe(list(symbols), ["ORDER_BOOK", "TRADES"])
            logger.info(f"Recording data for symbols: {', '.join(symbols)}")

            # Keep the application running
            while client.connected:
                await asyncio.sleep(1)

        except asyncio.CancelledError:
            logger.info("Shutting down...")
        except Exception as e:
            logger.error("Error in WebSocket client", error=str(e), exc_info=True)
        finally:
            await client.disconnect()

    try:
        if daemon:
            # Daemon mode implementation would go here
            # For now, just run in the foreground
            logger.info("Running in foreground (daemon mode not yet implemented)")
            asyncio.run(run())
        else:
            asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Recording stopped by user")
    except Exception as e:
        logger.critical("Fatal error", error=str(e), exc_info=True)
        raise click.Abort()


@cli.command()
@click.argument("symbols", nargs=-1, required=True)
@click.pass_context
def subscribe(ctx: click.Context, symbols: List[str]) -> None:
    """Subscribe to additional symbols."""
    # This would be implemented to send subscription messages to an already running instance
    logger.warning("Direct subscribe command not yet implemented")
    logger.info(f"Would subscribe to: {', '.join(symbols)}")


@cli.command()
@click.argument("symbols", nargs=-1, required=True)
@click.pass_context
def unsubscribe(ctx: click.Context, symbols: List[str]) -> None:
    """Unsubscribe from symbols."""
    # This would be implemented to send unsubscription messages to an already running instance
    logger.warning("Direct unsubscribe command not yet implemented")
    logger.info(f"Would unsubscribe from: {', '.join(symbols)}")


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show the status of the recorder."""
    # This would query the status of a running instance
    logger.warning("Status command not yet implemented")
    click.echo("Recorder status: Not implemented")


def main() -> None:
    """Run the CLI application."""
    try:
        cli(obj={})
    except Exception as e:
        logger.critical("Fatal error", error=str(e), exc_info=True)
        raise click.Abort()


if __name__ == "__main__":
    main()
