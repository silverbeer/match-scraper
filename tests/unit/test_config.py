"""Unit tests for configuration module."""

import os
from datetime import date, timedelta
from unittest.mock import patch

import pytest

from src.scraper.config import ScrapingConfig, load_config, validate_config


class TestLoadConfig:
    """Test configuration loading from environment variables."""

    def test_load_config_with_defaults(self):
        """Test loading configuration with default values."""
        env_vars = {
            "MISSING_TABLE_API_URL": "https://api.missing-table.com",
            "MISSING_TABLE_API_KEY": "test-api-key",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            config = load_config()

        assert config.age_group == "U14"
        assert config.club == ""
        assert config.competition == ""
        assert config.division == "Northeast"
        assert config.look_back_days == 1
        assert config.log_level == "INFO"
        assert config.missing_table_api_url == "https://api.missing-table.com"
        assert config.missing_table_api_key == "test-api-key"

        # Check date calculations
        expected_end_date = date.today()
        expected_start_date = expected_end_date - timedelta(days=1)
        assert config.end_date == expected_end_date
        assert config.start_date == expected_start_date

    def test_load_config_with_custom_values(self):
        """Test loading configuration with custom environment variables."""
        env_vars = {
            "AGE_GROUP": "U16",
            "CLUB": "Test Club",
            "COMPETITION": "Test Competition",
            "DIVISION": "Southeast",
            "LOOK_BACK_DAYS": "7",
            "LOG_LEVEL": "DEBUG",
            "MISSING_TABLE_API_URL": "https://custom-api.example.com",
            "MISSING_TABLE_API_KEY": "custom-key",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "https://otlp.example.com",
            "OTEL_EXPORTER_OTLP_HEADERS": "Authorization=Bearer token",
            "OTEL_SERVICE_NAME": "custom-scraper",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            config = load_config()

        assert config.age_group == "U16"
        assert config.club == "Test Club"
        assert config.competition == "Test Competition"
        assert config.division == "Southeast"
        assert config.look_back_days == 7
        assert config.log_level == "DEBUG"
        assert config.otel_exporter_otlp_endpoint == "https://otlp.example.com"
        assert config.otel_exporter_otlp_headers == "Authorization=Bearer token"
        assert config.otel_service_name == "custom-scraper"

        # Check date calculations with custom look_back_days
        expected_end_date = date.today()
        expected_start_date = expected_end_date - timedelta(days=7)
        assert config.end_date == expected_end_date
        assert config.start_date == expected_start_date

    def test_load_config_missing_required_api_url(self):
        """Test that missing API URL raises ValueError."""
        env_vars = {
            "MISSING_TABLE_API_KEY": "test-key",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            with pytest.raises(
                ValueError,
                match="MISSING_TABLE_API_URL environment variable is required",
            ):
                load_config()

    def test_load_config_missing_required_api_key(self):
        """Test that missing API key raises ValueError."""
        env_vars = {
            "MISSING_TABLE_API_URL": "https://api.example.com",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            with pytest.raises(
                ValueError,
                match="MISSING_TABLE_API_KEY environment variable is required",
            ):
                load_config()

    def test_load_config_invalid_look_back_days_string(self):
        """Test that invalid look_back_days string raises ValueError."""
        env_vars = {
            "MISSING_TABLE_API_URL": "https://api.example.com",
            "MISSING_TABLE_API_KEY": "test-key",
            "LOOK_BACK_DAYS": "invalid",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            with pytest.raises(
                ValueError, match="LOOK_BACK_DAYS must be a valid integer"
            ):
                load_config()

    def test_load_config_negative_look_back_days(self):
        """Test that negative look_back_days raises ValueError."""
        env_vars = {
            "MISSING_TABLE_API_URL": "https://api.example.com",
            "MISSING_TABLE_API_KEY": "test-key",
            "LOOK_BACK_DAYS": "-1",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            with pytest.raises(ValueError, match="LOOK_BACK_DAYS must be non-negative"):
                load_config()

    def test_load_config_zero_look_back_days(self):
        """Test that zero look_back_days is valid."""
        env_vars = {
            "MISSING_TABLE_API_URL": "https://api.example.com",
            "MISSING_TABLE_API_KEY": "test-key",
            "LOOK_BACK_DAYS": "0",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            config = load_config()

        assert config.look_back_days == 0
        assert config.start_date == config.end_date


class TestValidateConfig:
    """Test configuration validation."""

    def test_validate_config_valid(self):
        """Test validation with valid configuration."""
        config = ScrapingConfig(
            age_group="U14",
            club="Test Club",
            competition="Test Competition",
            division="Northeast",
            look_back_days=1,
            start_date=date.today() - timedelta(days=1),
            end_date=date.today(),
            missing_table_api_url="https://api.example.com",
            missing_table_api_key="test-key",
            log_level="INFO",
        )

        # Should not raise any exception
        validate_config(config)

    def test_validate_config_invalid_age_group(self):
        """Test validation with invalid age group."""
        config = ScrapingConfig(
            age_group="U12",  # Invalid age group
            club="",
            competition="",
            division="Northeast",
            look_back_days=1,
            start_date=date.today() - timedelta(days=1),
            end_date=date.today(),
            missing_table_api_url="https://api.example.com",
            missing_table_api_key="test-key",
            log_level="INFO",
        )

        with pytest.raises(ValueError, match="Invalid age_group: U12"):
            validate_config(config)

    def test_validate_config_empty_age_group(self):
        """Test validation with empty age group (should be valid)."""
        config = ScrapingConfig(
            age_group="",  # Empty age group should be valid
            club="",
            competition="",
            division="Northeast",
            look_back_days=1,
            start_date=date.today() - timedelta(days=1),
            end_date=date.today(),
            missing_table_api_url="https://api.example.com",
            missing_table_api_key="test-key",
            log_level="INFO",
        )

        # Should not raise any exception
        validate_config(config)

    def test_validate_config_invalid_date_range(self):
        """Test validation with invalid date range."""
        config = ScrapingConfig(
            age_group="U14",
            club="",
            competition="",
            division="Northeast",
            look_back_days=1,
            start_date=date.today(),
            end_date=date.today() - timedelta(days=1),  # End before start
            missing_table_api_url="https://api.example.com",
            missing_table_api_key="test-key",
            log_level="INFO",
        )

        with pytest.raises(ValueError, match="start_date .* cannot be after end_date"):
            validate_config(config)

    def test_validate_config_invalid_log_level(self):
        """Test validation with invalid log level."""
        config = ScrapingConfig(
            age_group="U14",
            club="",
            competition="",
            division="Northeast",
            look_back_days=1,
            start_date=date.today() - timedelta(days=1),
            end_date=date.today(),
            missing_table_api_url="https://api.example.com",
            missing_table_api_key="test-key",
            log_level="INVALID",  # Invalid log level
        )

        with pytest.raises(ValueError, match="Invalid log_level: INVALID"):
            validate_config(config)

    def test_validate_config_invalid_api_url(self):
        """Test validation with invalid API URL."""
        config = ScrapingConfig(
            age_group="U14",
            club="",
            competition="",
            division="Northeast",
            look_back_days=1,
            start_date=date.today() - timedelta(days=1),
            end_date=date.today(),
            missing_table_api_url="invalid-url",  # Invalid URL format
            missing_table_api_key="test-key",
            log_level="INFO",
        )

        with pytest.raises(
            ValueError, match="missing_table_api_url must be a valid HTTP/HTTPS URL"
        ):
            validate_config(config)

    def test_validate_config_case_insensitive_log_level(self):
        """Test validation with case-insensitive log level."""
        config = ScrapingConfig(
            age_group="U14",
            club="",
            competition="",
            division="Northeast",
            look_back_days=1,
            start_date=date.today() - timedelta(days=1),
            end_date=date.today(),
            missing_table_api_url="https://api.example.com",
            missing_table_api_key="test-key",
            log_level="debug",  # Lowercase should work
        )

        # Should not raise any exception
        validate_config(config)
