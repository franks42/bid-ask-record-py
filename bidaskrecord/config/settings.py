"""Application settings and configuration.

This module provides a centralized way to manage application settings
using environment variables with sensible defaults.
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from pydantic import AnyHttpUrl, Field, PostgresDsn, validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    # Application
    DEBUG: bool = Field(False, env="DEBUG")
    ENVIRONMENT: str = Field("production", env="ENVIRONMENT")
    LOG_LEVEL: str = Field("INFO", env="LOG_LEVEL")
    LOG_FILE: str = Field("bidaskrecord.log", env="LOG_FILE")

    # Database
    DATABASE_URL: str = Field(
        "sqlite:///./market_data.db",
        env="DATABASE_URL",
        description="Database connection URL. Defaults to SQLite.",
    )
    SQL_ECHO: bool = Field(False, env="SQL_ECHO")

    # WebSocket
    WEBSOCKET_URL: str = Field(
        "wss://figuremarkets.com/service-hft-exchange-websocket/ws/v1",
        env="WEBSOCKET_URL",
    )
    WEBSOCKET_RECONNECT_DELAY: int = Field(
        5, env="WEBSOCKET_RECONNECT_DELAY", description="Reconnection delay in seconds"
    )
    WEBSOCKET_MAX_RETRIES: int = Field(
        10,
        env="WEBSOCKET_MAX_RETRIES",
        description="Maximum number of connection retries",
    )

    # API
    API_PREFIX: str = "/api/v1"
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Bid-Ask Recorder"

    # Security
    SECRET_KEY: str = Field(
        "change-this-in-production",
        env="SECRET_KEY",
        description="Secret key for cryptographic operations",
    )

    # CORS
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = []

    @validator("BACKEND_CORS_ORIGINS", pre=True)
    def assemble_cors_origins(
        cls, v: Union[str, List[str]], values: Dict[str, Any]
    ) -> List[str]:
        """Parse CORS origins from environment."""
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        return []

    class Config:
        """Pydantic config."""

        case_sensitive = True
        env_file = ".env"
        env_file_encoding = "utf-8"

        @classmethod
        def parse_env_var(cls, field_name: str, raw_val: str) -> Any:
            """Parse environment variables."""
            if field_name == "BACKEND_CORS_ORIGINS":
                if not raw_val:
                    return []
                return [i.strip() for i in raw_val.split(",")]
            return cls.json_loads(raw_val)


# Create settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get the settings instance.

    Returns:
        Settings: The settings instance.
    """
    return settings


def ensure_dirs() -> None:
    """Ensure required directories exist."""
    # Create log directory if it doesn't exist
    log_dir = Path(settings.LOG_FILE).parent
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)


# Ensure directories exist when module is imported
ensure_dirs()
