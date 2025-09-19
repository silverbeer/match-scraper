"""
AWS Powertools Logger configuration for structured logging.

This module provides a centralized logger configuration using AWS Lambda Powertools
with structured JSON logging, correlation ID handling, and context propagation.
"""

import os
from typing import Any, Optional

from aws_lambda_powertools import Logger
from aws_lambda_powertools.logging import correlation_paths


class MLSScraperLogger:
    """
    Centralized logger for MLS Match Scraper with AWS Powertools integration.

    Provides structured logging with automatic correlation IDs, Lambda context,
    and consistent log formatting across the application.
    """

    def __init__(self, service_name: str = "mls-match-scraper"):
        """
        Initialize the logger with service configuration.

        Args:
            service_name: Name of the service for log identification
        """
        self.service_name = service_name
        self._logger = Logger(
            service=service_name,
            level=os.getenv("LOG_LEVEL", "INFO"),
            use_datetime_directive=True,
            json_serializer=self._custom_serializer,
        )

    def get_logger(self) -> Logger:
        """
        Get the configured AWS Powertools Logger instance.

        Returns:
            Configured Logger instance
        """
        return self._logger

    def inject_lambda_context(self, lambda_handler):
        """
        Decorator to inject Lambda context into logs.

        Args:
            lambda_handler: Lambda function to decorate

        Returns:
            Decorated function with Lambda context injection
        """
        return self._logger.inject_lambda_context(
            correlation_id_path=correlation_paths.API_GATEWAY_REST, log_event=True
        )(lambda_handler)

    def log_scraping_start(self, config: dict[str, Any]) -> None:
        """
        Log the start of a scraping operation with configuration details.

        Args:
            config: Scraping configuration parameters
        """
        self._logger.info(
            "Starting MLS match scraping operation",
            extra={
                "operation": "scraping_start",
                "config": config,
                "service": self.service_name,
            },
        )

    def log_scraping_complete(self, metrics: dict[str, Any]) -> None:
        """
        Log the completion of a scraping operation with metrics.

        Args:
            metrics: Scraping operation metrics
        """
        self._logger.info(
            "MLS match scraping operation completed",
            extra={
                "operation": "scraping_complete",
                "metrics": metrics,
                "service": self.service_name,
            },
        )

    def log_api_call(
        self,
        endpoint: str,
        method: str,
        status_code: Optional[int] = None,
        duration_ms: Optional[float] = None,
        error: Optional[str] = None,
    ) -> None:
        """
        Log API call details with timing and status information.

        Args:
            endpoint: API endpoint called
            method: HTTP method used
            status_code: HTTP response status code
            duration_ms: Request duration in milliseconds
            error: Error message if call failed
        """
        log_data = {
            "operation": "api_call",
            "endpoint": endpoint,
            "method": method,
            "service": self.service_name,
        }

        if status_code is not None:
            log_data["status_code"] = status_code
        if duration_ms is not None:
            log_data["duration_ms"] = duration_ms
        if error is not None:
            log_data["error"] = error

        if error or (status_code and status_code >= 400):
            self._logger.error(f"API call failed: {method} {endpoint}", extra=log_data)
        else:
            self._logger.info(
                f"API call successful: {method} {endpoint}", extra=log_data
            )

    def log_browser_operation(
        self,
        operation: str,
        success: bool,
        duration_ms: Optional[float] = None,
        error: Optional[str] = None,
    ) -> None:
        """
        Log browser/Playwright operation details.

        Args:
            operation: Browser operation performed
            success: Whether operation was successful
            duration_ms: Operation duration in milliseconds
            error: Error message if operation failed
        """
        log_data = {
            "operation": "browser_operation",
            "browser_operation": operation,
            "success": success,
            "service": self.service_name,
        }

        if duration_ms is not None:
            log_data["duration_ms"] = duration_ms
        if error is not None:
            log_data["error"] = error

        if success:
            self._logger.info(
                f"Browser operation successful: {operation}", extra=log_data
            )
        else:
            self._logger.error(f"Browser operation failed: {operation}", extra=log_data)

    @staticmethod
    def _custom_serializer(obj: Any) -> Any:
        """
        Custom JSON serializer for complex objects including Pydantic models.

        Args:
            obj: Object to serialize

        Returns:
            Serializable representation of the object
        """
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        elif hasattr(obj, "model_dump"):
            # Pydantic v2 models
            return obj.model_dump()
        elif hasattr(obj, "dict"):
            # Pydantic v1 models (fallback)
            return obj.dict()
        elif hasattr(obj, "__dict__"):
            return obj.__dict__
        else:
            return str(obj)


# Global logger instance
scraper_logger = MLSScraperLogger()


# Convenience function to get logger
def get_logger() -> Logger:
    """
    Get the global logger instance.

    Returns:
        Configured AWS Powertools Logger
    """
    return scraper_logger.get_logger()
