"""
Unit tests for the metrics infrastructure.

Tests OpenTelemetry metrics configuration, OTLP exporter setup,
counter and histogram definitions, and metric recording functionality.
"""

import os
from unittest.mock import Mock, patch

from src.utils.metrics import MLSScraperMetrics, get_metrics, scraper_metrics


class TestMLSScraperMetrics:
    """Test cases for MLSScraperMetrics class."""

    @patch("src.utils.metrics.OTLPMetricExporter")
    @patch("src.utils.metrics.PeriodicExportingMetricReader")
    @patch("src.utils.metrics.MeterProvider")
    @patch("src.utils.metrics.metrics.set_meter_provider")
    def test_init_default_configuration(
        self, mock_set_provider, mock_meter_provider, mock_reader, mock_exporter
    ):
        """Test metrics initialization with default configuration."""
        mock_meter = Mock()
        mock_meter_provider_instance = Mock()
        mock_meter_provider_instance.get_meter.return_value = mock_meter
        mock_meter_provider.return_value = mock_meter_provider_instance

        # Mock counter and histogram creation
        mock_meter.create_counter.return_value = Mock()
        mock_meter.create_histogram.return_value = Mock()

        metrics_instance = MLSScraperMetrics()

        assert metrics_instance.service_name == "mls-match-scraper"
        assert metrics_instance.service_version == "1.0.0"
        mock_set_provider.assert_called_once()

    @patch("src.utils.metrics.OTLPMetricExporter")
    @patch("src.utils.metrics.PeriodicExportingMetricReader")
    @patch("src.utils.metrics.MeterProvider")
    @patch("src.utils.metrics.metrics.set_meter_provider")
    def test_init_custom_configuration(
        self, mock_set_provider, mock_meter_provider, mock_reader, mock_exporter
    ):
        """Test metrics initialization with custom configuration."""
        mock_meter = Mock()
        mock_meter_provider_instance = Mock()
        mock_meter_provider_instance.get_meter.return_value = mock_meter
        mock_meter_provider.return_value = mock_meter_provider_instance

        # Mock counter and histogram creation
        mock_meter.create_counter.return_value = Mock()
        mock_meter.create_histogram.return_value = Mock()

        custom_name = "test-service"
        custom_version = "2.0.0"

        metrics_instance = MLSScraperMetrics(
            service_name=custom_name, service_version=custom_version
        )

        assert metrics_instance.service_name == custom_name
        assert metrics_instance.service_version == custom_version

    def test_parse_otlp_headers_empty(self):
        """Test parsing empty OTLP headers."""
        with patch.dict(os.environ, {}, clear=True):
            metrics_instance = MLSScraperMetrics.__new__(MLSScraperMetrics)
            headers = metrics_instance._parse_otlp_headers()
            assert headers == {}

    def test_parse_otlp_headers_single_header(self):
        """Test parsing single OTLP header."""
        with patch.dict(
            os.environ, {"OTEL_EXPORTER_OTLP_HEADERS": "Authorization=Bearer token123"}
        ):
            metrics_instance = MLSScraperMetrics.__new__(MLSScraperMetrics)
            headers = metrics_instance._parse_otlp_headers()
            assert headers == {"Authorization": "Bearer token123"}

    def test_parse_otlp_headers_multiple_headers(self):
        """Test parsing multiple OTLP headers."""
        headers_str = "Authorization=Bearer token123,Content-Type=application/json"
        with patch.dict(os.environ, {"OTEL_EXPORTER_OTLP_HEADERS": headers_str}):
            metrics_instance = MLSScraperMetrics.__new__(MLSScraperMetrics)
            headers = metrics_instance._parse_otlp_headers()
            expected = {
                "Authorization": "Bearer token123",
                "Content-Type": "application/json",
            }
            assert headers == expected

    @patch("src.utils.metrics.OTLPMetricExporter")
    @patch("src.utils.metrics.PeriodicExportingMetricReader")
    @patch("src.utils.metrics.MeterProvider")
    @patch("src.utils.metrics.metrics.set_meter_provider")
    @patch("src.utils.metrics.metrics.get_meter")
    def test_counter_initialization(
        self,
        mock_get_meter,
        mock_set_provider,
        mock_meter_provider,
        mock_reader,
        mock_exporter,
    ):
        """Test that all counters are properly initialized."""
        mock_meter = Mock()
        mock_get_meter.return_value = mock_meter

        # Track counter creation calls
        counter_calls = []

        def track_counter_creation(name, description, unit):
            counter_calls.append((name, description, unit))
            return Mock()

        mock_meter.create_counter.side_effect = track_counter_creation
        mock_meter.create_histogram.return_value = Mock()

        MLSScraperMetrics()  # Initialize metrics

        # Verify expected counters were created
        expected_counters = [
            (
                "games_scheduled_total",
                "Total number of games scheduled found during scraping",
                "1",
            ),
            (
                "games_scored_total",
                "Total number of games with scores found during scraping",
                "1",
            ),
            (
                "api_calls_total",
                "Total number of API calls made to missing-table.com",
                "1",
            ),
            ("scraping_errors_total", "Total number of scraping errors by type", "1"),
            (
                "browser_operations_total",
                "Total number of browser operations performed",
                "1",
            ),
        ]

        for expected in expected_counters:
            assert expected in counter_calls

    @patch("src.utils.metrics.OTLPMetricExporter")
    @patch("src.utils.metrics.PeriodicExportingMetricReader")
    @patch("src.utils.metrics.MeterProvider")
    @patch("src.utils.metrics.metrics.set_meter_provider")
    @patch("src.utils.metrics.metrics.get_meter")
    def test_histogram_initialization(
        self,
        mock_get_meter,
        mock_set_provider,
        mock_meter_provider,
        mock_reader,
        mock_exporter,
    ):
        """Test that all histograms are properly initialized."""
        mock_meter = Mock()
        mock_get_meter.return_value = mock_meter

        # Track histogram creation calls
        histogram_calls = []

        def track_histogram_creation(name, description, unit):
            histogram_calls.append((name, description, unit))
            return Mock()

        mock_meter.create_counter.return_value = Mock()
        mock_meter.create_histogram.side_effect = track_histogram_creation

        MLSScraperMetrics()  # Initialize metrics

        # Verify expected histograms were created
        expected_histograms = [
            (
                "scraping_duration_seconds",
                "Distribution of scraping operation execution times",
                "s",
            ),
            (
                "api_call_duration_seconds",
                "Distribution of API call response times",
                "s",
            ),
            (
                "browser_operation_duration_seconds",
                "Distribution of browser operation execution times",
                "s",
            ),
            (
                "lambda_execution_duration_seconds",
                "Distribution of Lambda function execution times",
                "s",
            ),
        ]

        for expected in expected_histograms:
            assert expected in histogram_calls


class TestMetricsRecording:
    """Test cases for metrics recording functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        with patch("src.utils.metrics.OTLPMetricExporter"), patch(
            "src.utils.metrics.PeriodicExportingMetricReader"
        ), patch("src.utils.metrics.MeterProvider"), patch(
            "src.utils.metrics.metrics.set_meter_provider"
        ):
            self.metrics = MLSScraperMetrics()

            # Mock all counters and histograms
            self.metrics.games_scheduled_counter = Mock()
            self.metrics.games_scored_counter = Mock()
            self.metrics.api_calls_counter = Mock()
            self.metrics.scraping_errors_counter = Mock()
            self.metrics.browser_operations_counter = Mock()
            self.metrics.scraping_duration_histogram = Mock()
            self.metrics.api_call_duration_histogram = Mock()
            self.metrics.browser_operation_duration_histogram = Mock()
            self.metrics.lambda_duration_histogram = Mock()

    def test_record_games_scheduled(self):
        """Test recording games scheduled metric."""
        self.metrics.record_games_scheduled(5, {"age_group": "U14"})

        self.metrics.games_scheduled_counter.add.assert_called_once_with(
            5,
            {
                "age_group": "U14",
                "service": "mls-match-scraper",
                "operation": "scraping",
            },
        )

    def test_record_games_scored(self):
        """Test recording games scored metric."""
        self.metrics.record_games_scored(3, {"division": "Northeast"})

        self.metrics.games_scored_counter.add.assert_called_once_with(
            3,
            {
                "division": "Northeast",
                "service": "mls-match-scraper",
                "operation": "scraping",
            },
        )

    def test_record_api_call(self):
        """Test recording API call metrics."""
        self.metrics.record_api_call(
            endpoint="/api/games",
            method="POST",
            status_code=201,
            duration_seconds=0.25,
            labels={"operation": "create_game"},
        )

        expected_attributes = {
            "operation": "create_game",
            "service": "mls-match-scraper",
            "endpoint": "/api/games",
            "method": "POST",
            "status_code": "201",
            "status_class": "2xx",
        }

        self.metrics.api_calls_counter.add.assert_called_once_with(
            1, expected_attributes
        )
        self.metrics.api_call_duration_histogram.record.assert_called_once_with(
            0.25, expected_attributes
        )

    def test_record_scraping_error(self):
        """Test recording scraping error metric."""
        self.metrics.record_scraping_error("network_timeout", {"retry_attempt": "3"})

        self.metrics.scraping_errors_counter.add.assert_called_once_with(
            1,
            {
                "retry_attempt": "3",
                "service": "mls-match-scraper",
                "error_type": "network_timeout",
            },
        )

    def test_record_browser_operation(self):
        """Test recording browser operation metrics."""
        self.metrics.record_browser_operation(
            operation="page_load",
            success=True,
            duration_seconds=1.5,
            labels={"page": "schedule"},
        )

        expected_attributes = {
            "page": "schedule",
            "service": "mls-match-scraper",
            "operation": "page_load",
            "success": "true",
        }

        self.metrics.browser_operations_counter.add.assert_called_once_with(
            1, expected_attributes
        )
        self.metrics.browser_operation_duration_histogram.record.assert_called_once_with(
            1.5, expected_attributes
        )

    def test_time_operation_context_manager(self):
        """Test timing operation context manager."""
        with patch("time.time", side_effect=[1000.0, 1001.5]):  # 1.5 second duration
            with self.metrics.time_operation(
                "test_operation", {"component": "scraper"}
            ):
                pass  # Simulate some work

        expected_attributes = {
            "component": "scraper",
            "service": "mls-match-scraper",
            "operation": "test_operation",
        }

        self.metrics.scraping_duration_histogram.record.assert_called_once_with(
            1.5, expected_attributes
        )

    def test_time_operation_context_manager_with_exception(self):
        """Test timing operation context manager handles exceptions."""
        with patch("time.time", side_effect=[1000.0, 1001.0]):  # 1 second duration
            try:
                with self.metrics.time_operation("failing_operation"):
                    raise ValueError("Test exception")
            except ValueError:
                pass  # Expected exception

        # Should still record the duration even when exception occurs
        expected_attributes = {
            "service": "mls-match-scraper",
            "operation": "failing_operation",
        }

        self.metrics.scraping_duration_histogram.record.assert_called_once_with(
            1.0, expected_attributes
        )

    @patch.dict(os.environ, {"AWS_LAMBDA_FUNCTION_NAME": "test-function"})
    def test_time_lambda_execution_context_manager(self):
        """Test timing Lambda execution context manager."""
        with patch("time.time", side_effect=[2000.0, 2002.5]):  # 2.5 second duration
            with self.metrics.time_lambda_execution({"version": "1.0"}):
                pass  # Simulate Lambda execution

        expected_attributes = {
            "version": "1.0",
            "service": "mls-match-scraper",
            "function_name": "test-function",
        }

        self.metrics.lambda_duration_histogram.record.assert_called_once_with(
            2.5, expected_attributes
        )


class TestGlobalMetricsFunctions:
    """Test cases for global metrics functions."""

    def test_get_metrics_returns_mls_scraper_metrics(self):
        """Test that get_metrics function returns MLSScraperMetrics instance."""
        metrics_instance = get_metrics()
        assert isinstance(metrics_instance, MLSScraperMetrics)

    def test_scraper_metrics_is_mls_scraper_metrics_instance(self):
        """Test that scraper_metrics is an MLSScraperMetrics instance."""
        assert isinstance(scraper_metrics, MLSScraperMetrics)
        assert scraper_metrics.service_name == "mls-match-scraper"


class TestMetricsIntegration:
    """Integration tests for metrics functionality."""

    @patch.dict(
        os.environ,
        {
            "OTEL_EXPORTER_OTLP_ENDPOINT": "https://otlp-gateway-test.grafana.net",
            "OTEL_EXPORTER_OTLP_HEADERS": "Authorization=Bearer test-token",
            "OTEL_METRIC_EXPORT_INTERVAL": "10000",
            "OTEL_METRIC_EXPORT_TIMEOUT": "60000",
            "AWS_LAMBDA_FUNCTION_NAME": "test-function",
        },
    )
    @patch("src.utils.metrics.OTLPMetricExporter")
    @patch("src.utils.metrics.PeriodicExportingMetricReader")
    @patch("src.utils.metrics.MeterProvider")
    @patch("src.utils.metrics.metrics.set_meter_provider")
    def test_metrics_with_environment_variables(
        self, mock_set_provider, mock_meter_provider, mock_reader, mock_exporter
    ):
        """Test metrics configuration with environment variables."""
        mock_meter = Mock()
        mock_meter_provider_instance = Mock()
        mock_meter_provider_instance.get_meter.return_value = mock_meter
        mock_meter_provider.return_value = mock_meter_provider_instance

        # Mock counter and histogram creation
        mock_meter.create_counter.return_value = Mock()
        mock_meter.create_histogram.return_value = Mock()

        MLSScraperMetrics()  # Initialize metrics

        # Verify OTLP exporter was configured with environment variables
        mock_exporter.assert_called_once_with(
            endpoint="https://otlp-gateway-test.grafana.net",
            headers={"Authorization": "Bearer test-token"},
            timeout=30,
        )

        # Verify periodic reader was configured with environment variables
        mock_reader.assert_called_once_with(
            exporter=mock_exporter.return_value,
            export_interval_millis=10000,
            export_timeout_millis=60000,
        )
