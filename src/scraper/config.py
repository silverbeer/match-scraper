"""Configuration module for MLS Match Scraper.

Handles environment variable parsing with defaults and validation.
"""

import os
from dataclasses import dataclass
from datetime import date
from typing import Optional

from .date_handler import calculate_date_range, validate_date_range


@dataclass
class ScrapingConfig:
    """Configuration for scraping parameters."""

    age_group: str
    club: str
    competition: str
    division: str
    look_back_days: int
    start_date: date
    end_date: date
    missing_table_api_url: str
    missing_table_api_key: str
    log_level: str

    # OpenTelemetry configuration
    otel_exporter_otlp_endpoint: Optional[str] = None
    otel_exporter_otlp_headers: Optional[str] = None
    otel_metrics_exporter: str = "otlp"
    otel_exporter_otlp_protocol: str = "http/protobuf"
    otel_service_name: str = "mls-match-scraper"
    otel_service_version: str = "1.0.0"


def load_config() -> ScrapingConfig:
    """Load configuration from environment variables with defaults.

    Returns:
        ScrapingConfig: Parsed configuration object

    Raises:
        ValueError: If required environment variables are missing
    """
    # Required environment variables
    missing_table_api_url = os.getenv("MISSING_TABLE_API_URL")
    if not missing_table_api_url:
        raise ValueError("MISSING_TABLE_API_URL environment variable is required")

    missing_table_api_key = os.getenv("MISSING_TABLE_API_KEY")
    if not missing_table_api_key:
        raise ValueError("MISSING_TABLE_API_KEY environment variable is required")

    # Optional environment variables with defaults
    age_group = os.getenv("AGE_GROUP", "U14")
    club = os.getenv("CLUB", "")
    competition = os.getenv("COMPETITION", "")
    division = os.getenv("DIVISION", "Northeast")
    log_level = os.getenv("LOG_LEVEL", "INFO")

    # Parse look_back_days with validation
    try:
        look_back_days = int(os.getenv("LOOK_BACK_DAYS", "1"))
        if look_back_days < 0:
            raise ValueError("LOOK_BACK_DAYS must be non-negative")
    except ValueError as e:
        if "invalid literal" in str(e):
            raise ValueError("LOOK_BACK_DAYS must be a valid integer") from e
        raise

    # Calculate date range using date_handler
    start_date, end_date = calculate_date_range(look_back_days)

    # OpenTelemetry configuration
    otel_exporter_otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    otel_exporter_otlp_headers = os.getenv("OTEL_EXPORTER_OTLP_HEADERS")
    otel_metrics_exporter = os.getenv("OTEL_METRICS_EXPORTER", "otlp")
    otel_exporter_otlp_protocol = os.getenv(
        "OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf"
    )
    otel_service_name = os.getenv("OTEL_SERVICE_NAME", "mls-match-scraper")
    otel_service_version = os.getenv("OTEL_SERVICE_VERSION", "1.0.0")

    return ScrapingConfig(
        age_group=age_group,
        club=club,
        competition=competition,
        division=division,
        look_back_days=look_back_days,
        start_date=start_date,
        end_date=end_date,
        missing_table_api_url=missing_table_api_url,
        missing_table_api_key=missing_table_api_key,
        log_level=log_level,
        otel_exporter_otlp_endpoint=otel_exporter_otlp_endpoint,
        otel_exporter_otlp_headers=otel_exporter_otlp_headers,
        otel_metrics_exporter=otel_metrics_exporter,
        otel_exporter_otlp_protocol=otel_exporter_otlp_protocol,
        otel_service_name=otel_service_name,
        otel_service_version=otel_service_version,
    )


def validate_config(config: ScrapingConfig) -> None:
    """Validate configuration values.

    Args:
        config: Configuration object to validate

    Raises:
        ValueError: If configuration values are invalid
    """
    # Validate age group format
    valid_age_groups = ["U13", "U14", "U15", "U16", "U17", "U18", "U19"]
    if config.age_group and config.age_group not in valid_age_groups:
        raise ValueError(
            f"Invalid age_group: {config.age_group}. Must be one of {valid_age_groups}"
        )

    # Validate date range using date_handler
    validate_date_range(config.start_date, config.end_date)

    # Validate log level
    valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    if config.log_level.upper() not in valid_log_levels:
        raise ValueError(
            f"Invalid log_level: {config.log_level}. Must be one of {valid_log_levels}"
        )

    # Validate API URL format
    if not config.missing_table_api_url.startswith(("http://", "https://")):
        raise ValueError("missing_table_api_url must be a valid HTTP/HTTPS URL")
