"""
Structured Logger configuration for MLS Match Scraper.

This module provides a centralized logger configuration with structured JSON logging
and context propagation.

Environment-aware logging:
- In Kubernetes: Writes JSON logs to /var/log/scraper/app.log for Promtail collection
- Locally: Writes JSON logs to stdout for interactive debugging
"""

import logging
import os
import sys
from typing import Any, Optional

from pythonjsonlogger import jsonlogger


class MLSScraperLogger:
    """
    Centralized logger for MLS Match Scraper with structured logging.

    Provides structured logging with consistent log formatting
    across the application.
    """

    def __init__(self, service_name: str = "mls-match-scraper"):
        """
        Initialize the logger with service configuration.

        Environment-aware configuration:
        - In Kubernetes: Logs written to /var/log/scraper/app.log (for Promtail → Loki)
        - Locally: Logs written to stdout (for terminal visibility with --verbose)

        Args:
            service_name: Name of the service for log identification
        """
        self.service_name = service_name
        self.is_kubernetes = self._detect_kubernetes()

        # Create the base logger
        self._logger = logging.getLogger(service_name)
        self._logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

        # Prevent duplicate handlers
        if not self._logger.handlers:
            self._configure_handler()

    @staticmethod
    def _detect_kubernetes() -> bool:
        """
        Detect if running in Kubernetes environment.

        Returns:
            True if running in Kubernetes, False otherwise
        """
        # Kubernetes sets this environment variable in all pods
        return os.getenv("KUBERNETES_SERVICE_HOST") is not None

    def _configure_handler(self) -> None:
        """
        Configure the appropriate log handler based on environment.

        In Kubernetes: Use FileHandler to write to /var/log/scraper/app.log
        Locally: Use StreamHandler (stdout) with JSON formatting
        """
        if self.is_kubernetes:
            # In Kubernetes: Write logs to file for Promtail to collect
            log_file_path = "/var/log/scraper/app.log"

            try:
                # Ensure log directory exists
                os.makedirs(os.path.dirname(log_file_path), exist_ok=True)

                # Create JSON formatter
                file_handler = logging.FileHandler(log_file_path)
                json_formatter = jsonlogger.JsonFormatter(
                    '%(timestamp)s %(level)s %(service)s %(name)s %(message)s',
                    timestamp=True
                )
                file_handler.setFormatter(json_formatter)
                self._logger.addHandler(file_handler)

                # Also log to stderr for kubectl logs visibility (without JSON formatting)
                stderr_handler = logging.StreamHandler(sys.stderr)
                stderr_handler.setLevel(
                    logging.WARNING
                )  # Only warnings and errors to stderr
                stderr_formatter = logging.Formatter("%(levelname)s - %(message)s")
                stderr_handler.setFormatter(stderr_formatter)
                self._logger.addHandler(stderr_handler)

            except (PermissionError, OSError) as e:
                # If we can't write to /var/log/scraper (e.g., local testing with K8s env vars),
                # fall back to stderr
                import warnings

                warnings.warn(
                    f"Cannot write to {log_file_path}: {e}. "
                    f"Falling back to stderr. This is expected when testing locally with "
                    f"KUBERNETES_SERVICE_HOST set.",
                    stacklevel=2,
                )
                # Use default stdout handler
                handler = logging.StreamHandler(sys.stdout)
                json_formatter = jsonlogger.JsonFormatter(
                    '%(timestamp)s %(level)s %(service)s %(name)s %(message)s',
                    timestamp=True
                )
                handler.setFormatter(json_formatter)
                self._logger.addHandler(handler)
        else:
            # Local development: Use stdout with JSON formatting
            handler = logging.StreamHandler(sys.stdout)
            json_formatter = jsonlogger.JsonFormatter(
                '%(timestamp)s %(level)s %(service)s %(name)s %(message)s',
                timestamp=True
            )
            handler.setFormatter(json_formatter)
            self._logger.addHandler(handler)

    def get_logger(self) -> logging.Logger:
        """
        Get the configured structured Logger instance.

        Returns:
            Configured Logger instance
        """
        return self._logger

    def _add_service_context(self, extra: Optional[dict] = None) -> dict:
        """
        Add service context to log extra fields.

        Args:
            extra: Additional fields to include in log

        Returns:
            Extra fields with service context added
        """
        context = extra or {}
        context.setdefault('service', self.service_name)
        return context

    def info(self, message: str, **kwargs) -> None:
        """Log info message with context."""
        extra = self._add_service_context(kwargs.get('extra'))
        self._logger.info(message, extra=extra)

    def debug(self, message: str, **kwargs) -> None:
        """Log debug message with context."""
        extra = self._add_service_context(kwargs.get('extra'))
        self._logger.debug(message, extra=extra)

    def warning(self, message: str, **kwargs) -> None:
        """Log warning message with context."""
        extra = self._add_service_context(kwargs.get('extra'))
        self._logger.warning(message, extra=extra)

    def error(self, message: str, **kwargs) -> None:
        """Log error message with context."""
        extra = self._add_service_context(kwargs.get('extra'))
        self._logger.error(message, extra=extra)

    def log_scraping_start(self, config: dict[str, Any]) -> None:
        """
        Log the start of a scraping operation with configuration details.

        Args:
            config: Scraping configuration parameters
        """
        self.info(
            "Starting MLS match scraping operation",
            extra={
                "operation": "scraping_start",
                "config": config,
            },
        )

    def log_scraping_complete(self, metrics: dict[str, Any]) -> None:
        """
        Log the completion of a scraping operation with metrics.

        Args:
            metrics: Scraping operation metrics
        """
        self.info(
            "MLS match scraping operation completed",
            extra={
                "operation": "scraping_complete",
                "metrics": metrics,
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
        }

        if status_code is not None:
            log_data["status_code"] = status_code
        if duration_ms is not None:
            log_data["duration_ms"] = duration_ms
        if error is not None:
            log_data["error"] = error

        if error or (status_code and status_code >= 400):
            self.error(f"API call failed: {method} {endpoint}", extra=log_data)
        else:
            self.info(f"API call successful: {method} {endpoint}", extra=log_data)

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
        }

        if duration_ms is not None:
            log_data["duration_ms"] = duration_ms
        if error is not None:
            log_data["error"] = error

        if success:
            self.info(f"Browser operation successful: {operation}", extra=log_data)
        else:
            self.error(f"Browser operation failed: {operation}", extra=log_data)


# Global logger instance
scraper_logger = MLSScraperLogger()


# Convenience function to get logger
def get_logger() -> logging.Logger:
    """
    Get the global logger instance.

    Returns:
        Configured structured Logger
    """
    return scraper_logger.get_logger()
