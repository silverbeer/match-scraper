"""
Unit tests for the logging infrastructure.

Tests structured logging configuration and log formatting.
"""

import logging
import os
from unittest.mock import patch

from src.utils.logger import MLSScraperLogger, get_logger, scraper_logger


class TestMLSScraperLogger:
    """Test cases for MLSScraperLogger class."""

    def test_init_default_service_name(self):
        """Test logger initialization with default service name."""
        logger = MLSScraperLogger()
        assert logger.service_name == "mls-match-scraper"
        assert isinstance(logger.get_logger(), logging.Logger)

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
            assert isinstance(logger.get_logger(), logging.Logger)

    def test_get_logger_returns_standard_logger(self):
        """Test that get_logger returns standard Python Logger instance."""
        logger = MLSScraperLogger()
        python_logger = logger.get_logger()
        assert isinstance(python_logger, logging.Logger)


    def test_log_scraping_start(self):
        """Test logging scraping start with configuration."""
        logger = MLSScraperLogger()

        with patch.object(logger._logger, "info") as mock_info:
            config = {"age_group": "U14", "division": "Northeast", "look_back_days": 1}

            logger.log_scraping_start(config)

            mock_info.assert_called_once()
            call_args = mock_info.call_args
            assert "Starting MLS match scraping operation" in call_args[0][0]
            extra = call_args[1]["extra"]
            assert extra["operation"] == "scraping_start"
            assert extra["config"] == config
            assert extra["service"] == "mls-match-scraper"

    def test_log_scraping_complete(self):
        """Test logging scraping completion with metrics."""
        logger = MLSScraperLogger()

        with patch.object(logger._logger, "info") as mock_info:
            metrics = {"games_scheduled": 5, "games_scored": 3, "duration_ms": 1500}

            logger.log_scraping_complete(metrics)

            mock_info.assert_called_once()
            call_args = mock_info.call_args
            assert "MLS match scraping operation completed" in call_args[0][0]
            extra = call_args[1]["extra"]
            assert extra["operation"] == "scraping_complete"
            assert extra["metrics"] == metrics

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



class TestGlobalLoggerFunctions:
    """Test cases for global logger functions."""

    def test_get_logger_returns_standard_logger(self):
        """Test that get_logger function returns standard Python Logger."""
        logger = get_logger()
        assert isinstance(logger, logging.Logger)

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
            {"LOG_LEVEL": "DEBUG"},
        ):
            logger = MLSScraperLogger()

            # Should create logger successfully with environment variables
            assert logger.get_logger() is not None
            assert isinstance(logger.get_logger(), logging.Logger)

    def test_logger_kubernetes_detection(self):
        """Test that logger properly detects Kubernetes environment."""
        # Test without Kubernetes env var
        logger_local = MLSScraperLogger()
        assert logger_local.is_kubernetes is False

        # Test with Kubernetes env var
        with patch.dict(os.environ, {"KUBERNETES_SERVICE_HOST": "10.0.0.1"}):
            logger_k8s = MLSScraperLogger(service_name="test-k8s-logger")
            assert logger_k8s.is_kubernetes is True
