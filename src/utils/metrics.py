"""
OpenTelemetry metrics configuration for MLS Match Scraper.

This module provides centralized metrics collection using grafana-otel-py library
for tracking scraping operations, API calls, and performance metrics.
"""

import os
import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import Optional

from grafana_otel import GrafanaOTELClient


class MLSScraperMetrics(GrafanaOTELClient):
    """
    Centralized metrics collection for MLS Match Scraper.

    Extends GrafanaOTELClient with domain-specific metrics for tracking
    scraping operations, API calls, and performance.
    """

    def __init__(
        self, service_name: str = "mls-match-scraper", service_version: str = "1.0.0"
    ):
        """
        Initialize metrics with MLS-specific configuration.

        Args:
            service_name: Name of the service for metric identification
            service_version: Version of the service
        """
        # Pass additional Grafana Cloud resource attributes
        super().__init__(
            service_name=service_name,
            service_version=service_version,
            **{
                "service.instance.id": os.getenv("HOSTNAME", "local"),
                "deployment.environment": os.getenv("DEPLOYMENT_ENV", "production"),
                "k8s.namespace.name": os.getenv("K8S_NAMESPACE", "match-scraper"),
                "k8s.pod.name": os.getenv("HOSTNAME", "local"),
                "cloud.provider": "gcp",
                "cloud.platform": "gcp_kubernetes_engine",
            },
        )

        # Initialize domain-specific metrics
        self._init_scraper_metrics()

    def _init_scraper_metrics(self) -> None:
        """Initialize scraper-specific metrics."""
        # Game-related counters
        self.games_scheduled_counter = self.create_counter(
            name="games_scheduled_total",
            description="Total number of games scheduled found during scraping",
        )

        self.games_scored_counter = self.create_counter(
            name="games_scored_total",
            description="Total number of games with scores found during scraping",
        )

        # API operation counters
        self.api_calls_counter = self.create_counter(
            name="api_calls_total",
            description="Total number of API calls made to missing-table.com",
        )

        # Error counters
        self.scraping_errors_counter = self.create_counter(
            name="scraping_errors_total",
            description="Total number of scraping errors by type",
        )

        # Browser operation counters
        self.browser_operations_counter = self.create_counter(
            name="browser_operations_total",
            description="Total number of browser operations performed",
        )

        # Execution time histograms
        self.scraping_duration_histogram = self.create_histogram(
            name="scraping_duration_seconds",
            description="Distribution of scraping operation execution times",
        )

        self.api_call_duration_histogram = self.create_histogram(
            name="api_call_duration_seconds",
            description="Distribution of API call response times",
        )

        # Browser operation histograms
        self.browser_operation_duration_histogram = self.create_histogram(
            name="browser_operation_duration_seconds",
            description="Distribution of browser operation execution times",
        )

        # Application execution histogram
        self.execution_duration_histogram = self.create_histogram(
            name="application_execution_duration_seconds",
            description="Distribution of application execution times",
        )

    def record_games_scheduled(
        self, count: int, labels: Optional[dict[str, str]] = None
    ) -> None:
        """
        Record the number of games scheduled found.

        Args:
            count: Number of games scheduled
            labels: Additional labels for the metric
        """
        attributes = labels or {}
        attributes.update({"service": self.service_name, "operation": "scraping"})
        self.games_scheduled_counter.add(count, attributes)

    def record_games_scored(
        self, count: int, labels: Optional[dict[str, str]] = None
    ) -> None:
        """
        Record the number of games with scores found.

        Args:
            count: Number of games with scores
            labels: Additional labels for the metric
        """
        attributes = labels or {}
        attributes.update({"service": self.service_name, "operation": "scraping"})
        self.games_scored_counter.add(count, attributes)

    def record_api_call(
        self,
        endpoint: str,
        method: str,
        status_code: int,
        duration_seconds: float,
        labels: Optional[dict[str, str]] = None,
    ) -> None:
        """
        Record an API call with timing and status information.

        Args:
            endpoint: API endpoint called
            method: HTTP method used
            status_code: HTTP response status code
            duration_seconds: Request duration in seconds
            labels: Additional labels for the metric
        """
        attributes = labels or {}
        attributes.update(
            {
                "service": self.service_name,
                "endpoint": endpoint,
                "method": method,
                "status_code": str(status_code),
                "status_class": f"{status_code // 100}xx",
            }
        )

        self.api_calls_counter.add(1, attributes)
        self.api_call_duration_histogram.record(duration_seconds, attributes)

    def record_scraping_error(
        self, error_type: str, labels: Optional[dict[str, str]] = None
    ) -> None:
        """
        Record a scraping error by type.

        Args:
            error_type: Type of error encountered
            labels: Additional labels for the metric
        """
        attributes = labels or {}
        attributes.update({"service": self.service_name, "error_type": error_type})
        self.scraping_errors_counter.add(1, attributes)

    def record_browser_operation(
        self,
        operation: str,
        success: bool,
        duration_seconds: float,
        labels: Optional[dict[str, str]] = None,
    ) -> None:
        """
        Record a browser operation with timing and success information.

        Args:
            operation: Browser operation performed
            success: Whether operation was successful
            duration_seconds: Operation duration in seconds
            labels: Additional labels for the metric
        """
        attributes = labels or {}
        attributes.update(
            {
                "service": self.service_name,
                "operation": operation,
                "success": str(success).lower(),
            }
        )

        self.browser_operations_counter.add(1, attributes)
        self.browser_operation_duration_histogram.record(duration_seconds, attributes)

    @contextmanager
    def time_operation(
        self, operation_name: str, labels: Optional[dict[str, str]] = None
    ) -> Generator[None, None, None]:
        """
        Context manager to time an operation and record the duration.

        Args:
            operation_name: Name of the operation being timed
            labels: Additional labels for the metric

        Yields:
            None
        """
        start_time = time.time()
        try:
            yield
        finally:
            duration = time.time() - start_time
            attributes = labels or {}
            attributes.update(
                {"service": self.service_name, "operation": operation_name}
            )
            self.scraping_duration_histogram.record(duration, attributes)

    @contextmanager
    def time_execution(
        self, labels: Optional[dict[str, str]] = None
    ) -> Generator[None, None, None]:
        """
        Context manager to time application execution.

        Args:
            labels: Additional labels for the metric

        Yields:
            None
        """
        start_time = time.time()
        try:
            yield
        finally:
            duration = time.time() - start_time
            attributes = labels or {}
            attributes.update(
                {
                    "service": self.service_name,
                    "instance": os.getenv("HOSTNAME", "local"),
                }
            )
            self.execution_duration_histogram.record(duration, attributes)


# Global metrics instance
scraper_metrics = MLSScraperMetrics()


# Convenience functions
def get_metrics() -> MLSScraperMetrics:
    """
    Get the global metrics instance.

    Returns:
        Configured MLSScraperMetrics instance
    """
    return scraper_metrics
