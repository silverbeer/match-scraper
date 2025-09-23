"""Unit tests for MLS scraper module."""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from src.scraper.config import ScrapingConfig
from src.scraper.mls_scraper import MLSScraper, MLSScraperError
from src.scraper.models import Match


class TestMLSScraperError:
    """Test cases for MLSScraperError exception."""

    def test_mls_scraper_error_creation(self):
        """Test MLSScraperError creation."""
        error = MLSScraperError("Test error message")
        assert str(error) == "Test error message"
        assert isinstance(error, Exception)

    def test_mls_scraper_error_with_cause(self):
        """Test MLSScraperError with underlying cause."""
        original_error = ValueError("Original error")
        try:
            raise MLSScraperError("Wrapper error") from original_error
        except MLSScraperError as error:
            assert str(error) == "Wrapper error"
            assert error.__cause__ == original_error


class TestMLSScraper:
    """Test cases for MLSScraper class."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock ScrapingConfig."""
        config = ScrapingConfig(
            age_group="U14",
            division="Northeast",
            club="Test Club",
            competition="Test Competition",
            look_back_days=7,
            start_date=datetime.now().date() - timedelta(days=1),
            end_date=datetime.now().date() + timedelta(days=7),
            missing_table_api_url="https://api.test.com",
            missing_table_api_key="test-key",
            log_level="INFO",
        )
        return config

    @pytest.fixture
    def mls_scraper(self, mock_config):
        """Create MLSScraper instance with mocked config."""
        return MLSScraper(mock_config, headless=True)

    def test_init(self, mock_config):
        """Test MLSScraper initialization."""
        scraper = MLSScraper(mock_config, headless=False)

        assert scraper.config == mock_config
        assert scraper.headless is False
        assert scraper.browser_manager is None
        assert hasattr(scraper, "execution_metrics")
        assert scraper.execution_metrics.errors_encountered == 0
        assert scraper.execution_metrics.api_calls_successful == 0
        assert scraper.execution_metrics.api_calls_failed == 0

    def test_init_with_defaults(self, mock_config):
        """Test MLSScraper initialization with default parameters."""
        scraper = MLSScraper(mock_config)

        assert scraper.config == mock_config
        assert scraper.headless is True

    def test_class_constants(self):
        """Test that class constants are properly defined."""
        assert hasattr(MLSScraper, "MLS_NEXT_URL")
        assert hasattr(MLSScraper, "MAX_RETRIES")
        assert hasattr(MLSScraper, "RETRY_DELAY_BASE")
        assert hasattr(MLSScraper, "RETRY_BACKOFF_MULTIPLIER")

        # Verify constants have expected types and values
        assert isinstance(MLSScraper.MLS_NEXT_URL, str)
        assert "mlssoccer.com" in MLSScraper.MLS_NEXT_URL
        assert isinstance(MLSScraper.MAX_RETRIES, int)
        assert MLSScraper.MAX_RETRIES > 0
        assert isinstance(MLSScraper.RETRY_DELAY_BASE, float)
        assert isinstance(MLSScraper.RETRY_BACKOFF_MULTIPLIER, float)

    def test_calculate_retry_delay(self, mls_scraper):
        """Test retry delay calculation."""
        # Test first attempt (attempt 0)
        delay = mls_scraper._calculate_retry_delay(0)
        expected = MLSScraper.RETRY_DELAY_BASE
        assert delay == expected

        # Test second attempt (attempt 1)
        delay = mls_scraper._calculate_retry_delay(1)
        expected = MLSScraper.RETRY_DELAY_BASE * (
            MLSScraper.RETRY_BACKOFF_MULTIPLIER**1
        )
        assert delay == expected

        # Test third attempt (attempt 2)
        delay = mls_scraper._calculate_retry_delay(2)
        expected = MLSScraper.RETRY_DELAY_BASE * (
            MLSScraper.RETRY_BACKOFF_MULTIPLIER**2
        )
        assert delay == expected

    def test_log_discovered_matches_empty_list(self, mls_scraper):
        """Test logging with empty matches list."""
        with patch("src.scraper.mls_scraper.logger") as mock_logger:
            mls_scraper._log_discovered_matches([])

            # Should log info about no matches found
            mock_logger.info.assert_called()
            call_args = mock_logger.info.call_args[0][0]
            assert "No matches" in call_args or "0 matches" in call_args

    def test_log_discovered_matches_with_matches(self, mls_scraper):
        """Test logging with actual matches."""
        # Create sample matches
        matches = [
            Match(
                match_id="test_1",
                home_team="Team A",
                away_team="Team B",
                match_datetime=datetime.now(),
            ),
            Match(
                match_id="test_2",
                home_team="Team C",
                away_team="Team D",
                match_datetime=datetime.now() + timedelta(days=1),
                home_score=2,
                away_score=1,
            ),
        ]

        with patch("src.scraper.mls_scraper.logger") as mock_logger:
            mls_scraper._log_discovered_matches(matches)

            # Should log info about matches found
            mock_logger.info.assert_called()

            # Should have been called multiple times for match details
            assert mock_logger.info.call_count >= 1

    def test_get_execution_metrics_returns_correct_object(self, mls_scraper):
        """Test get_execution_metrics returns the execution_metrics object."""
        metrics = mls_scraper.get_execution_metrics()

        # Should return the same object as the internal execution_metrics
        assert metrics is mls_scraper.execution_metrics
        assert metrics.games_scheduled == 0
        assert metrics.games_scored == 0
        assert metrics.api_calls_successful == 0
        assert metrics.api_calls_failed == 0
        assert metrics.execution_duration_ms == 0
        assert metrics.errors_encountered == 0

    def test_execution_metrics_is_scraping_metrics_object(self, mls_scraper):
        """Test that execution_metrics is a ScrapingMetrics object."""
        from src.scraper.models import ScrapingMetrics

        assert isinstance(mls_scraper.execution_metrics, ScrapingMetrics)

        # Test that the metrics object has the success rate method
        success_rate = mls_scraper.execution_metrics.get_success_rate()
        assert success_rate == 0.0  # No calls yet, so 0% success rate

    def test_emit_final_metrics_method_exists(self, mls_scraper):
        """Test that emit_final_metrics method exists and is async."""
        import inspect

        assert hasattr(mls_scraper, "_emit_final_metrics")
        method = mls_scraper._emit_final_metrics
        assert inspect.iscoroutinefunction(method)

    def test_scraper_workflow_methods_exist(self, mls_scraper):
        """Test that main workflow methods exist and are async."""
        import inspect

        workflow_methods = [
            "scrape_matches",
            "_initialize_browser_with_retry",
            "_execute_scraping_workflow",
            "_navigate_to_mls_website",
            "_apply_filters_with_retry",
            "_set_date_range_with_retry",
            "_extract_matches_with_retry",
        ]

        for method_name in workflow_methods:
            assert hasattr(mls_scraper, method_name)
            method = getattr(mls_scraper, method_name)
            assert inspect.iscoroutinefunction(method)

    def test_execution_metrics_tracking(self, mls_scraper):
        """Test execution metrics tracking through execution_metrics object."""
        metrics = mls_scraper.execution_metrics

        assert isinstance(metrics.errors_encountered, int)
        assert isinstance(metrics.api_calls_successful, int)
        assert isinstance(metrics.api_calls_failed, int)

        # Should start at 0
        assert metrics.errors_encountered == 0
        assert metrics.api_calls_successful == 0
        assert metrics.api_calls_failed == 0

    @patch("src.scraper.mls_scraper.time")
    def test_calculate_retry_delay_uses_time(self, mock_time, mls_scraper):
        """Test that retry delay calculation is consistent."""
        # This mainly tests the method exists and returns reasonable values
        for attempt in range(3):
            delay = mls_scraper._calculate_retry_delay(attempt)
            assert isinstance(delay, (int, float))
            assert delay >= 0

    def test_mls_url_is_valid_format(self):
        """Test that MLS_NEXT_URL follows expected format."""
        url = MLSScraper.MLS_NEXT_URL
        assert url.startswith("https://")
        assert "mlssoccer.com" in url
        assert "schedule" in url.lower()


class TestMLSScraperIntegration:
    """Integration-style tests for MLSScraper."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock ScrapingConfig."""
        return ScrapingConfig(
            age_group="U14",
            division="Northeast",
            club="",
            competition="",
            look_back_days=3,
            start_date=datetime.now().date(),
            end_date=datetime.now().date() + timedelta(days=3),
            missing_table_api_url="https://api.test.com",
            missing_table_api_key="test-key",
            log_level="INFO",
        )

    def test_scraper_initialization_workflow(self, mock_config):
        """Test that scraper can be initialized with different configurations."""
        # Test with headless=True
        scraper1 = MLSScraper(mock_config, headless=True)
        assert scraper1.headless is True

        # Test with headless=False
        scraper2 = MLSScraper(mock_config, headless=False)
        assert scraper2.headless is False

        # Both should have the same config
        assert scraper1.config == scraper2.config == mock_config

    def test_scraper_attributes_after_init(self, mock_config):
        """Test scraper attributes are properly set after initialization."""
        scraper = MLSScraper(mock_config)

        # Check all expected attributes exist
        expected_attributes = [
            "config",
            "headless",
            "browser_manager",
            "execution_metrics",
        ]

        for attr in expected_attributes:
            assert hasattr(scraper, attr)

        # Check initial values
        assert scraper.browser_manager is None
        assert scraper.execution_metrics.errors_encountered == 0
