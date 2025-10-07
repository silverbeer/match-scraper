"""
OpenTelemetry metrics configuration for MLS Match Scraper.

This module provides centralized metrics collection using OpenTelemetry with OTLP
exporter for Grafana Cloud integration. Includes counter and histogram definitions
for tracking scraping operations, API calls, and performance metrics.
"""

import os
import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import Optional

from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource


class MLSScraperMetrics:
    """
    Centralized metrics collection for MLS Match Scraper using OpenTelemetry.

    Provides counters and histograms for tracking scraping operations, API calls,
    and performance metrics with automatic export to Grafana Cloud via OTLP.
    """

    def __init__(
        self, service_name: str = "mls-match-scraper", service_version: str = "1.0.0"
    ):
        """
        Initialize OpenTelemetry metrics with OTLP exporter configuration.

        Args:
            service_name: Name of the service for metric identification
            service_version: Version of the service
        """
        self.service_name = service_name
        self.service_version = service_version

        # Configure resource with service information including Grafana Cloud attributes
        resource = Resource.create(
            {
                "service.name": service_name,
                "service.version": service_version,
                "service.instance.id": os.getenv("HOSTNAME", "local"),
                "deployment.environment": os.getenv("DEPLOYMENT_ENV", "production"),
                "k8s.namespace.name": os.getenv("K8S_NAMESPACE", "match-scraper"),
                "k8s.pod.name": os.getenv("HOSTNAME", "local"),
                "cloud.provider": "gcp",
                "cloud.platform": "gcp_kubernetes_engine",
            }
        )

        # Only configure OTLP exporter if endpoint is provided
        metric_readers = []
        otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")

        if otlp_endpoint:
            try:
                # Configure OTLP exporter for Grafana Cloud
                otlp_exporter = OTLPMetricExporter(
                    endpoint=otlp_endpoint,
                    headers=self._parse_otlp_headers(),
                    timeout=30,
                )

                # Configure periodic metric reader
                metric_reader = PeriodicExportingMetricReader(
                    exporter=otlp_exporter,
                    export_interval_millis=int(
                        os.getenv("OTEL_METRIC_EXPORT_INTERVAL", "5000")
                    ),
                    export_timeout_millis=int(
                        os.getenv("OTEL_METRIC_EXPORT_TIMEOUT", "30000")
                    ),
                )
                metric_readers.append(metric_reader)

                import logging

                logging.getLogger(__name__).info(
                    f"OpenTelemetry metrics configured for endpoint: {otlp_endpoint}"
                )
            except Exception as e:
                import logging

                logging.getLogger(__name__).warning(
                    f"Failed to configure OTLP metrics exporter: {e}. Metrics will not be exported."
                )
        else:
            import logging

            logging.getLogger(__name__).info(
                "OTEL_EXPORTER_OTLP_ENDPOINT not configured. Metrics will be collected but not exported."
            )

        # Set up meter provider
        meter_provider = MeterProvider(resource=resource, metric_readers=metric_readers)
        metrics.set_meter_provider(meter_provider)

        # Get meter instance
        self.meter = metrics.get_meter(service_name, service_version)

        # Initialize metrics
        self._init_counters()
        self._init_histograms()

    def _parse_otlp_headers(self) -> dict[str, str]:
        """
        Parse OTLP headers from environment variable.

        Returns:
            Dictionary of headers for OTLP exporter
        """
        headers_str = os.getenv("OTEL_EXPORTER_OTLP_HEADERS", "")
        headers = {}

        if headers_str:
            for header in headers_str.split(","):
                if "=" in header:
                    key, value = header.strip().split("=", 1)
                    headers[key] = value

        return headers

    def _init_counters(self) -> None:
        """Initialize counter metrics for tracking events."""

        # Scraping operation counters
        self.games_scheduled_counter = self.meter.create_counter(
            name="games_scheduled_total",
            description="Total number of games scheduled found during scraping",
            unit="1",
        )

        self.games_scored_counter = self.meter.create_counter(
            name="games_scored_total",
            description="Total number of games with scores found during scraping",
            unit="1",
        )

        # API operation counters
        self.api_calls_counter = self.meter.create_counter(
            name="api_calls_total",
            description="Total number of API calls made to missing-table.com",
            unit="1",
        )

        # Error counters
        self.scraping_errors_counter = self.meter.create_counter(
            name="scraping_errors_total",
            description="Total number of scraping errors by type",
            unit="1",
        )

        # Browser operation counters
        self.browser_operations_counter = self.meter.create_counter(
            name="browser_operations_total",
            description="Total number of browser operations performed",
            unit="1",
        )

    def _init_histograms(self) -> None:
        """Initialize histogram metrics for tracking distributions."""

        # Execution time histograms
        self.scraping_duration_histogram = self.meter.create_histogram(
            name="scraping_duration_seconds",
            description="Distribution of scraping operation execution times",
            unit="s",
        )

        self.api_call_duration_histogram = self.meter.create_histogram(
            name="api_call_duration_seconds",
            description="Distribution of API call response times",
            unit="s",
        )

        # Browser operation histograms
        self.browser_operation_duration_histogram = self.meter.create_histogram(
            name="browser_operation_duration_seconds",
            description="Distribution of browser operation execution times",
            unit="s",
        )

        # Application execution histogram
        self.execution_duration_histogram = self.meter.create_histogram(
            name="application_execution_duration_seconds",
            description="Distribution of application execution times",
            unit="s",
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
