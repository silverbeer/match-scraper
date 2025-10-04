"""Configuration module for MLS Match Scraper.

Handles environment variable parsing with defaults and validation.
"""

import os
from datetime import date
from typing import Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator

from .date_handler import calculate_date_range, validate_date_range


class ScrapingConfig(BaseModel):
    """Configuration for scraping parameters."""

    age_group: str = Field(..., description="Age group for scraping (e.g., U14)")
    club: str = Field(default="", description="Club filter")
    competition: str = Field(default="", description="Competition filter")
    division: str = Field(..., description="Division for scraping")
    look_back_days: int = Field(ge=0, description="Number of days to look back")
    start_date: date = Field(..., description="Start date for scraping")
    end_date: date = Field(..., description="End date for scraping")
    missing_table_api_url: str = Field(..., description="Missing Table API base URL")
    missing_table_api_key: str = Field(..., description="Missing Table API key")
    log_level: str = Field(default="INFO", description="Logging level")

    # Team cache configuration
    enable_team_cache: bool = Field(default=True, description="Enable team caching")
    cache_refresh_on_miss: bool = Field(default=True, description="Refresh cache on miss")
    cache_preload_timeout: int = Field(default=30, ge=1, description="Cache preload timeout in seconds")

    # Score parsing configuration
    placeholder_scores: list[tuple[int, int]] = Field(
        default=[(0, 0)], 
        description="Score combinations that should be treated as placeholders/TBD"
    )

    # OpenTelemetry configuration
    otel_exporter_otlp_endpoint: Optional[str] = Field(default=None, description="OTLP exporter endpoint")
    otel_exporter_otlp_headers: Optional[str] = Field(default=None, description="OTLP exporter headers")
    otel_metrics_exporter: str = Field(default="otlp", description="Metrics exporter type")
    otel_exporter_otlp_protocol: str = Field(default="http/protobuf", description="OTLP protocol")
    otel_service_name: str = Field(default="mls-match-scraper", description="Service name for telemetry")
    otel_service_version: str = Field(default="1.0.0", description="Service version for telemetry")

    @field_validator('age_group')
    @classmethod
    def validate_age_group(cls, v: str) -> str:
        """Validate age group format."""
        valid_age_groups = ["U13", "U14", "U15", "U16", "U17", "U18", "U19"]
        if v and v not in valid_age_groups:
            raise ValueError(f"Invalid age_group: {v}. Must be one of {valid_age_groups}")
        return v

    @field_validator('log_level')
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_log_levels:
            raise ValueError(f"Invalid log_level: {v}. Must be one of {valid_log_levels}")
        return v.upper()

    @field_validator('missing_table_api_url')
    @classmethod
    def validate_api_url(cls, v: str) -> str:
        """Validate API URL format."""
        if not v.startswith(("http://", "https://")):
            raise ValueError("missing_table_api_url must be a valid HTTP/HTTPS URL")
        parsed = urlparse(v)
        if not parsed.netloc:
            raise ValueError("missing_table_api_url must have a valid domain")
        return v

    @model_validator(mode='after')
    def validate_date_range(self) -> 'ScrapingConfig':
        """Validate that date range is logical."""
        validate_date_range(self.start_date, self.end_date)
        return self

    class Config:
        """Pydantic configuration."""
        # Allow arbitrary types for date objects
        arbitrary_types_allowed = True
        # JSON schema extra information
        json_schema_extra = {
            "example": {
                "age_group": "U14",
                "club": "",
                "competition": "",
                "division": "Northeast",
                "look_back_days": 1,
                "start_date": "2025-09-28",
                "end_date": "2025-09-29",
                "missing_table_api_url": "http://localhost:8000",
                "missing_table_api_key": "your-api-key",
                "log_level": "INFO"
            }
        }


def load_config() -> ScrapingConfig:
    """Load configuration from environment variables with defaults.

    Returns:
        ScrapingConfig: Parsed and validated configuration object

    Raises:
        ValueError: If required environment variables are missing or invalid
    """
    # Required environment variables (support both old and new naming)
    missing_table_api_url = (
        os.getenv("MISSING_TABLE_API_BASE_URL") or
        os.getenv("MISSING_TABLE_API_URL")
    )
    if not missing_table_api_url:
        raise ValueError("MISSING_TABLE_API_BASE_URL (or MISSING_TABLE_API_URL) environment variable is required")

    missing_table_api_key = (
        os.getenv("MISSING_TABLE_API_TOKEN") or
        os.getenv("MISSING_TABLE_API_KEY")
    )
    if not missing_table_api_key:
        raise ValueError("MISSING_TABLE_API_TOKEN (or MISSING_TABLE_API_KEY) environment variable is required")

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

    # Team cache configuration
    enable_team_cache = os.getenv("ENABLE_TEAM_CACHE", "true").lower() == "true"
    cache_refresh_on_miss = os.getenv("CACHE_REFRESH_ON_MISS", "true").lower() == "true"
    cache_preload_timeout = int(os.getenv("CACHE_PRELOAD_TIMEOUT", "30"))

    # OpenTelemetry configuration
    otel_exporter_otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    otel_exporter_otlp_headers = os.getenv("OTEL_EXPORTER_OTLP_HEADERS")
    otel_metrics_exporter = os.getenv("OTEL_METRICS_EXPORTER", "otlp")
    otel_exporter_otlp_protocol = os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf")
    otel_service_name = os.getenv("OTEL_SERVICE_NAME", "mls-match-scraper")
    otel_service_version = os.getenv("OTEL_SERVICE_VERSION", "1.0.0")

    # Create and validate config using Pydantic
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
        enable_team_cache=enable_team_cache,
        cache_refresh_on_miss=cache_refresh_on_miss,
        cache_preload_timeout=cache_preload_timeout,
        otel_exporter_otlp_endpoint=otel_exporter_otlp_endpoint,
        otel_exporter_otlp_headers=otel_exporter_otlp_headers,
        otel_metrics_exporter=otel_metrics_exporter,
        otel_exporter_otlp_protocol=otel_exporter_otlp_protocol,
        otel_service_name=otel_service_name,
        otel_service_version=otel_service_version,
    )


# validate_config() function removed - validation is now built into the Pydantic model
# Use ScrapingConfig(...) directly for validation, or config.model_validate() for re-validation
