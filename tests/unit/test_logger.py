"""
Unit tests for the logging infrastructure.

Tests AWS Powertools Logger configuration, structured logging,
correlation ID handling, and context propagation.
"""

import os
from unittest.mock import Mock, patch

from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.typing import LambdaContext

from src.utils.logger import MLSScraperLogger, get_logger, scraper_logger


class TestMLSScraperLogger:
    """Test cases for MLSScraperLogger class."""

    def test_init_default_service_name(self):
        """Test logger initialization with default service name."""
        logger = MLSScraperLogger()
        assert logger.service_name == "mls-match-scraper"
        assert isinstance(logger.get_logger(), Logger)

    def test_init_custom_service_name(self):
        """Test logger initialization with custom service name."""
        custom_name = "test-service"
        logger = MLSScraperLogger(service_name=custom_name)
        assert logger.service_name == custom_name

    def test_init_with_log_level_env_var(self):
        """Test logger initialization with LOG_LEVEL environment variable."""
        with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}):
            logger = MLSScraperLogger()
            # Verify logger is created successfully with environment variable set
            assert logger.get_logger() is not None
            assert isinstance(logger.get_logger(), Logger)

    def test_get_logger_returns_powertools_logger(self):
        """Test that get_logger returns AWS Powertools Logger instance."""
        logger = MLSScraperLogger()
        powertools_logger = logger.get_logger()
        assert isinstance(powertools_logger, Logger)

    def test_inject_lambda_context_decorator(self):
        """Test Lambda context injection decorator."""
        logger = MLSScraperLogger()

        @logger.inject_lambda_context
        def mock_handler(event, context):
            return {"statusCode": 200}

        # The decorator should return a callable
        assert callable(mock_handler)

    def test_log_scraping_start(self):
        """Test logging scraping start with configuration."""
        logger = MLSScraperLogger()

        with patch.object(logger._logger, "info") as mock_info:
            config = {"age_group": "U14", "division": "Northeast", "look_back_days": 1}

            logger.log_scraping_start(config)

            mock_info.assert_called_once()
            call_args = mock_info.call_args
            assert "Starting MLS match scraping operation" in call_args[0][0]
            assert call_args[1]["extra"]["operation"] == "scraping_start"
            assert call_args[1]["extra"]["config"] == config
            assert call_args[1]["extra"]["service"] == "mls-match-scraper"

    def test_log_scraping_complete(self):
        """Test logging scraping completion with metrics."""
        logger = MLSScraperLogger()

        with patch.object(logger._logger, "info") as mock_info:
            metrics = {"games_scheduled": 5, "games_scored": 3, "duration_ms": 1500}

            logger.log_scraping_complete(metrics)

            mock_info.assert_called_once()
            call_args = mock_info.call_args
            assert "MLS match scraping operation completed" in call_args[0][0]
            assert call_args[1]["extra"]["operation"] == "scraping_complete"
            assert call_args[1]["extra"]["metrics"] == metrics

    def test_log_api_call_success(self):
        """Test logging successful API call."""
        logger = MLSScraperLogger()

        with patch.object(logger._logger, "info") as mock_info:
            logger.log_api_call(
                endpoint="/api/games", method="POST", status_code=201, duration_ms=250.5
            )

            mock_info.assert_called_once()
            call_args = mock_info.call_args
            assert "API call successful: POST /api/games" in call_args[0][0]
            extra = call_args[1]["extra"]
            assert extra["operation"] == "api_call"
            assert extra["endpoint"] == "/api/games"
            assert extra["method"] == "POST"
            assert extra["status_code"] == 201
            assert extra["duration_ms"] == 250.5

    def test_log_api_call_error_with_status_code(self):
        """Test logging API call with error status code."""
        logger = MLSScraperLogger()

        with patch.object(logger._logger, "error") as mock_error:
            logger.log_api_call(
                endpoint="/api/games",
                method="POST",
                status_code=500,
                duration_ms=1000.0,
            )

            mock_error.assert_called_once()
            call_args = mock_error.call_args
            assert "API call failed: POST /api/games" in call_args[0][0]
            extra = call_args[1]["extra"]
            assert extra["status_code"] == 500

    def test_log_api_call_error_with_exception(self):
        """Test logging API call with exception."""
        logger = MLSScraperLogger()

        with patch.object(logger._logger, "error") as mock_error:
            logger.log_api_call(
                endpoint="/api/games", method="POST", error="Connection timeout"
            )

            mock_error.assert_called_once()
            call_args = mock_error.call_args
            assert "API call failed: POST /api/games" in call_args[0][0]
            extra = call_args[1]["extra"]
            assert extra["error"] == "Connection timeout"

    def test_log_browser_operation_success(self):
        """Test logging successful browser operation."""
        logger = MLSScraperLogger()

        with patch.object(logger._logger, "info") as mock_info:
            logger.log_browser_operation(
                operation="page_load", success=True, duration_ms=500.0
            )

            mock_info.assert_called_once()
            call_args = mock_info.call_args
            assert "Browser operation successful: page_load" in call_args[0][0]
            extra = call_args[1]["extra"]
            assert extra["operation"] == "browser_operation"
            assert extra["browser_operation"] == "page_load"
            assert extra["success"] is True
            assert extra["duration_ms"] == 500.0

    def test_log_browser_operation_failure(self):
        """Test logging failed browser operation."""
        logger = MLSScraperLogger()

        with patch.object(logger._logger, "error") as mock_error:
            logger.log_browser_operation(
                operation="click_element", success=False, error="Element not found"
            )

            mock_error.assert_called_once()
            call_args = mock_error.call_args
            assert "Browser operation failed: click_element" in call_args[0][0]
            extra = call_args[1]["extra"]
            assert extra["success"] is False
            assert extra["error"] == "Element not found"

    def test_custom_serializer_datetime(self):
        """Test custom serializer handles datetime objects."""
        from datetime import datetime

        dt = datetime(2023, 1, 1, 12, 0, 0)
        result = MLSScraperLogger._custom_serializer(dt)
        assert result == "2023-01-01T12:00:00"

    def test_custom_serializer_object_with_dict(self):
        """Test custom serializer handles objects with __dict__."""

        class TestObj:
            def __init__(self):
                self.name = "test"
                self.value = 42

        obj = TestObj()
        result = MLSScraperLogger._custom_serializer(obj)
        assert result == {"name": "test", "value": 42}

    def test_custom_serializer_fallback_to_str(self):
        """Test custom serializer falls back to str() for other objects."""
        result = MLSScraperLogger._custom_serializer(42)
        assert result == "42"


class TestGlobalLoggerFunctions:
    """Test cases for global logger functions."""

    def test_get_logger_returns_powertools_logger(self):
        """Test that get_logger function returns AWS Powertools Logger."""
        logger = get_logger()
        assert isinstance(logger, Logger)

    def test_scraper_logger_is_mls_scraper_logger_instance(self):
        """Test that scraper_logger is an MLSScraperLogger instance."""
        assert isinstance(scraper_logger, MLSScraperLogger)
        assert scraper_logger.service_name == "mls-match-scraper"


class TestLoggerIntegration:
    """Integration tests for logger functionality."""

    def test_logger_with_environment_variables(self):
        """Test logger configuration with environment variables."""
        with patch.dict(
            os.environ,
            {"LOG_LEVEL": "DEBUG", "AWS_LAMBDA_FUNCTION_NAME": "test-function"},
        ):
            logger = MLSScraperLogger()

            # Should create logger successfully with environment variables
            assert logger.get_logger() is not None
            assert isinstance(logger.get_logger(), Logger)

    def test_logger_context_propagation(self):
        """Test that logger properly handles context propagation."""
        logger = MLSScraperLogger()

        # Mock Lambda context
        mock_context = Mock(spec=LambdaContext)
        mock_context.aws_request_id = "test-request-id"
        mock_context.function_name = "test-function"

        # The logger should be able to handle Lambda context
        # This is more of a smoke test since actual context injection
        # happens at runtime with the decorator
        assert logger.get_logger() is not None
