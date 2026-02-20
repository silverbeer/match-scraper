"""Unit tests for MLS scraper module."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

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


# Phase 1: Core Workflow Tests
class TestMLSScraperWorkflow:
    """Test main scraping workflow orchestration."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock ScrapingConfig."""
        return ScrapingConfig(
            age_group="U14",
            division="Northeast",
            league="Homegrown",
            club="",
            competition="",
            look_back_days=1,
            start_date=datetime.now().date(),
            end_date=datetime.now().date() + timedelta(days=1),
            missing_table_api_url="https://api.test.com",
            missing_table_api_key="test-key",
            log_level="INFO",
        )

    @pytest.fixture
    def mls_scraper(self, mock_config):
        """Create MLSScraper instance."""
        return MLSScraper(mock_config, headless=True)

    @pytest.fixture
    def sample_matches(self):
        """Create sample matches for testing."""
        return [
            Match(
                match_id="match_1",
                home_team="Team A",
                away_team="Team B",
                match_datetime=datetime.now(),
            ),
            Match(
                match_id="match_2",
                home_team="Team C",
                away_team="Team D",
                match_datetime=datetime.now() + timedelta(days=1),
                home_score=2,
                away_score=1,
            ),
        ]

    @pytest.mark.asyncio
    async def test_scrape_matches_success(self, mls_scraper, sample_matches):
        """Test successful scraping workflow."""
        with (
            patch.object(
                mls_scraper, "_initialize_browser_with_retry", new_callable=AsyncMock
            ) as mock_init,
            patch.object(
                mls_scraper,
                "_execute_scraping_workflow",
                new_callable=AsyncMock,
                return_value=sample_matches,
            ) as mock_execute,
            patch.object(
                mls_scraper, "_emit_final_metrics", new_callable=AsyncMock
            ) as mock_emit,
        ):
            # Mock browser manager for cleanup
            mls_scraper.browser_manager = MagicMock()
            mls_scraper.browser_manager.cleanup = AsyncMock()

            matches = await mls_scraper.scrape_matches()

            assert len(matches) == 2
            assert matches == sample_matches
            mock_init.assert_called_once()
            mock_execute.assert_called_once()
            mock_emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_scrape_matches_browser_init_failure(self, mls_scraper):
        """Test scraping workflow when browser init fails."""
        with patch.object(
            mls_scraper,
            "_initialize_browser_with_retry",
            new_callable=AsyncMock,
            side_effect=MLSScraperError("Browser init failed"),
        ):
            with pytest.raises(MLSScraperError) as exc_info:
                await mls_scraper.scrape_matches()

            assert "Browser init failed" in str(exc_info.value)
            assert mls_scraper.execution_metrics.errors_encountered == 1

    @pytest.mark.asyncio
    async def test_scrape_matches_workflow_failure(self, mls_scraper):
        """Test scraping workflow when execution fails."""
        with (
            patch.object(
                mls_scraper, "_initialize_browser_with_retry", new_callable=AsyncMock
            ),
            patch.object(
                mls_scraper,
                "_execute_scraping_workflow",
                new_callable=AsyncMock,
                side_effect=Exception("Workflow failed"),
            ),
        ):
            # Mock browser manager for cleanup
            mls_scraper.browser_manager = MagicMock()
            mls_scraper.browser_manager.cleanup = AsyncMock()

            with pytest.raises(MLSScraperError) as exc_info:
                await mls_scraper.scrape_matches()

            assert "Workflow failed" in str(exc_info.value)
            assert mls_scraper.execution_metrics.errors_encountered == 1

    @pytest.mark.asyncio
    async def test_scrape_matches_cleanup_on_error(self, mls_scraper):
        """Test that cleanup is called even when errors occur."""
        with (
            patch.object(
                mls_scraper, "_initialize_browser_with_retry", new_callable=AsyncMock
            ),
            patch.object(
                mls_scraper,
                "_execute_scraping_workflow",
                new_callable=AsyncMock,
                side_effect=Exception("Test error"),
            ),
        ):
            # Mock browser manager
            mock_browser = MagicMock()
            mock_browser.cleanup = AsyncMock()
            mls_scraper.browser_manager = mock_browser

            with pytest.raises(MLSScraperError):
                await mls_scraper.scrape_matches()

            # Verify cleanup was called
            mock_browser.cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_scrape_matches_metrics_timing(self, mls_scraper, sample_matches):
        """Test that execution duration is tracked."""
        with (
            patch.object(
                mls_scraper, "_initialize_browser_with_retry", new_callable=AsyncMock
            ),
            patch.object(
                mls_scraper,
                "_execute_scraping_workflow",
                new_callable=AsyncMock,
                return_value=sample_matches,
            ),
            patch.object(mls_scraper, "_emit_final_metrics", new_callable=AsyncMock),
            patch("src.scraper.mls_scraper.time") as mock_time,
        ):
            # Simulate 500ms elapsed time
            mock_time.time = MagicMock(side_effect=[1000.0, 1000.5])

            # Mock browser manager
            mls_scraper.browser_manager = MagicMock()
            mls_scraper.browser_manager.cleanup = AsyncMock()

            await mls_scraper.scrape_matches()

            # Verify metrics were updated
            assert mls_scraper.execution_metrics.execution_duration_ms > 0

    @pytest.mark.asyncio
    async def test_scrape_matches_error_count_tracking(self, mls_scraper):
        """Test that errors are counted in metrics."""
        with patch.object(
            mls_scraper,
            "_initialize_browser_with_retry",
            new_callable=AsyncMock,
            side_effect=Exception("Init error"),
        ):
            mls_scraper.browser_manager = MagicMock()
            mls_scraper.browser_manager.cleanup = AsyncMock()

            with pytest.raises(MLSScraperError):
                await mls_scraper.scrape_matches()

            assert mls_scraper.execution_metrics.errors_encountered == 1


# Phase 2: Browser Initialization Tests
class TestMLSScraperBrowserInit:
    """Test browser initialization with retry logic."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock ScrapingConfig."""
        return ScrapingConfig(
            age_group="U14",
            division="Northeast",
            club="",
            competition="",
            look_back_days=1,
            start_date=datetime.now().date(),
            end_date=datetime.now().date(),
            missing_table_api_url="https://api.test.com",
            missing_table_api_key="test-key",
            log_level="INFO",
        )

    @pytest.fixture
    def mls_scraper(self, mock_config):
        """Create MLSScraper instance."""
        return MLSScraper(mock_config)

    @pytest.mark.asyncio
    async def test_initialize_browser_success(self, mls_scraper):
        """Test successful browser initialization."""
        with patch(
            "src.scraper.mls_scraper.BrowserManager"
        ) as mock_browser_manager_class:
            mock_manager = MagicMock()
            mock_manager.initialize = AsyncMock()
            mock_browser_manager_class.return_value = mock_manager

            await mls_scraper._initialize_browser_with_retry()

            assert mls_scraper.browser_manager is not None
            mock_manager.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_browser_retry_on_failure(self, mls_scraper):
        """Test browser initialization retries on failure."""
        with patch(
            "src.scraper.mls_scraper.BrowserManager"
        ) as mock_browser_manager_class:
            mock_manager = MagicMock()
            # Fail twice, then succeed
            mock_manager.initialize = AsyncMock(
                side_effect=[Exception("Fail 1"), Exception("Fail 2"), None]
            )
            mock_browser_manager_class.return_value = mock_manager

            with patch(
                "asyncio.sleep", new_callable=AsyncMock
            ):  # Mock sleep to speed up test
                await mls_scraper._initialize_browser_with_retry()

            # Should have tried 3 times
            assert mock_manager.initialize.call_count == 3

    @pytest.mark.asyncio
    async def test_initialize_browser_max_retries_exceeded(self, mls_scraper):
        """Test browser init fails after max retries."""
        with patch(
            "src.scraper.mls_scraper.BrowserManager"
        ) as mock_browser_manager_class:
            mock_manager = MagicMock()
            # Always fail
            mock_manager.initialize = AsyncMock(side_effect=Exception("Always fail"))
            mock_browser_manager_class.return_value = mock_manager

            with patch("asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(MLSScraperError) as exc_info:
                    await mls_scraper._initialize_browser_with_retry()

                assert "after" in str(exc_info.value).lower()
                assert "attempts" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_initialize_browser_retry_delay(self, mls_scraper):
        """Test that retry delays use exponential backoff."""
        with patch(
            "src.scraper.mls_scraper.BrowserManager"
        ) as mock_browser_manager_class:
            mock_manager = MagicMock()
            mock_manager.initialize = AsyncMock(side_effect=[Exception("Fail"), None])
            mock_browser_manager_class.return_value = mock_manager

            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                await mls_scraper._initialize_browser_with_retry()

                # Verify sleep was called with calculated delay
                mock_sleep.assert_called_once()
                delay = mock_sleep.call_args[0][0]
                assert delay > 0


# Phase 3: Workflow Execution Tests
class TestMLSScraperWorkflowExecution:
    """Test workflow step execution."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock ScrapingConfig."""
        return ScrapingConfig(
            age_group="U14",
            division="Northeast",
            club="",
            competition="",
            look_back_days=1,
            start_date=datetime.now().date(),
            end_date=datetime.now().date(),
            missing_table_api_url="https://api.test.com",
            missing_table_api_key="test-key",
            log_level="INFO",
        )

    @pytest.fixture
    def mls_scraper(self, mock_config):
        """Create MLSScraper instance with browser manager."""
        scraper = MLSScraper(mock_config)
        # Mock browser manager
        scraper.browser_manager = MagicMock()
        return scraper

    @pytest.mark.asyncio
    async def test_execute_scraping_workflow_success(self, mls_scraper):
        """Test successful workflow execution."""
        mock_page = MagicMock()
        sample_matches = [
            Match(
                match_id="test_1",
                home_team="Team A",
                away_team="Team B",
                match_datetime=datetime.now(),
            )
        ]

        # Mock the async page context manager
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_page
        mock_ctx.__aexit__.return_value = None
        mls_scraper.browser_manager.get_page = MagicMock(return_value=mock_ctx)

        with (
            patch.object(
                mls_scraper, "_navigate_to_mls_website", new_callable=AsyncMock
            ),
            patch.object(
                mls_scraper, "_apply_filters_with_retry", new_callable=AsyncMock
            ),
            patch.object(
                mls_scraper, "_set_date_range_with_retry", new_callable=AsyncMock
            ),
            patch.object(
                mls_scraper,
                "_extract_matches_with_retry",
                new_callable=AsyncMock,
                return_value=sample_matches,
            ),
        ):
            matches = await mls_scraper._execute_scraping_workflow()

            assert len(matches) == 1
            assert matches[0].match_id == "test_1"

    @pytest.mark.asyncio
    async def test_execute_scraping_workflow_browser_not_initialized(self):
        """Test workflow fails if browser not initialized."""
        mock_config = ScrapingConfig(
            age_group="U14",
            division="Northeast",
            club="",
            competition="",
            look_back_days=1,
            start_date=datetime.now().date(),
            end_date=datetime.now().date(),
            missing_table_api_url="https://api.test.com",
            missing_table_api_key="test-key",
            log_level="INFO",
        )
        scraper = MLSScraper(mock_config)
        # Don't set browser_manager

        with pytest.raises(MLSScraperError) as exc_info:
            await scraper._execute_scraping_workflow()

        assert "not initialized" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_execute_scraping_workflow_with_page_context(self, mls_scraper):
        """Test that workflow uses page context manager properly."""
        mock_page = MagicMock()
        sample_matches = []

        # Track context manager calls
        enter_called = False
        exit_called = False

        async def mock_aenter(*args):
            nonlocal enter_called
            enter_called = True
            return mock_page

        async def mock_aexit(*args):
            nonlocal exit_called
            exit_called = True

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = mock_aenter
        mock_ctx.__aexit__ = mock_aexit
        mls_scraper.browser_manager.get_page = MagicMock(return_value=mock_ctx)

        with (
            patch.object(
                mls_scraper, "_navigate_to_mls_website", new_callable=AsyncMock
            ),
            patch.object(
                mls_scraper, "_apply_filters_with_retry", new_callable=AsyncMock
            ),
            patch.object(
                mls_scraper, "_set_date_range_with_retry", new_callable=AsyncMock
            ),
            patch.object(
                mls_scraper,
                "_extract_matches_with_retry",
                new_callable=AsyncMock,
                return_value=sample_matches,
            ),
        ):
            await mls_scraper._execute_scraping_workflow()

            assert enter_called
            assert exit_called


# Phase 4: Navigation & Academy Tab Tests
class TestMLSScraperNavigation:
    """Test navigation and Academy tab logic."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock ScrapingConfig."""
        return ScrapingConfig(
            age_group="U14",
            division="Northeast",
            league="Homegrown",
            club="",
            competition="",
            look_back_days=1,
            start_date=datetime.now().date(),
            end_date=datetime.now().date(),
            missing_table_api_url="https://api.test.com",
            missing_table_api_key="test-key",
            log_level="INFO",
        )

    @pytest.fixture
    def mls_scraper(self, mock_config):
        """Create MLSScraper instance."""
        return MLSScraper(mock_config)

    @pytest.mark.asyncio
    async def test_navigate_to_mls_website(self, mls_scraper):
        """Test navigation to MLS website."""
        mock_page = MagicMock()

        with (
            patch("src.scraper.mls_scraper.PageNavigator") as mock_navigator_class,
            patch(
                "src.scraper.consent_handler.MLSConsentHandler"
            ) as mock_consent_class,
        ):
            mock_navigator = MagicMock()
            mock_navigator.navigate_to = AsyncMock(return_value=True)
            mock_navigator_class.return_value = mock_navigator

            mock_consent = MagicMock()
            mock_consent.handle_consent_banner = AsyncMock(return_value=True)
            mock_consent.wait_for_page_ready = AsyncMock(return_value=True)
            mock_consent_class.return_value = mock_consent

            await mls_scraper._navigate_to_mls_website(mock_page)

            mock_navigator.navigate_to.assert_called_once()
            mock_consent.handle_consent_banner.assert_called_once()

    @pytest.mark.asyncio
    async def test_navigate_consent_handling(self, mls_scraper):
        """Test consent banner handling during navigation."""
        mock_page = MagicMock()

        with (
            patch("src.scraper.mls_scraper.PageNavigator") as mock_navigator_class,
            patch(
                "src.scraper.consent_handler.MLSConsentHandler"
            ) as mock_consent_class,
        ):
            mock_navigator = MagicMock()
            mock_navigator.navigate_to = AsyncMock(return_value=True)
            mock_navigator_class.return_value = mock_navigator

            mock_consent = MagicMock()
            mock_consent.handle_consent_banner = AsyncMock(return_value=False)
            mock_consent.wait_for_page_ready = AsyncMock(return_value=True)
            mock_consent_class.return_value = mock_consent

            # Should not raise error even if consent fails
            await mls_scraper._navigate_to_mls_website(mock_page)

            mock_consent.handle_consent_banner.assert_called_once()

    @pytest.mark.asyncio
    async def test_click_academy_tab_success(self):
        """Test clicking Academy tab successfully."""
        mock_config = ScrapingConfig(
            age_group="U14",
            division="Northeast",
            league="Academy",  # Academy league
            club="",
            competition="",
            look_back_days=1,
            start_date=datetime.now().date(),
            end_date=datetime.now().date(),
            missing_table_api_url="https://api.test.com",
            missing_table_api_key="test-key",
            log_level="INFO",
        )
        scraper = MLSScraper(mock_config)
        mock_page = MagicMock()
        mock_page.wait_for_timeout = AsyncMock()

        with patch("src.scraper.browser.ElementInteractor") as mock_interactor_class:
            mock_interactor = MagicMock()
            mock_interactor.click_element = AsyncMock(return_value=True)
            mock_interactor_class.return_value = mock_interactor

            await scraper._click_academy_tab(mock_page)

            mock_interactor.click_element.assert_called()

    @pytest.mark.asyncio
    async def test_click_academy_tab_not_found(self):
        """Test Academy tab not found (graceful handling)."""
        mock_config = ScrapingConfig(
            age_group="U14",
            division="Northeast",
            league="Academy",
            club="",
            competition="",
            look_back_days=1,
            start_date=datetime.now().date(),
            end_date=datetime.now().date(),
            missing_table_api_url="https://api.test.com",
            missing_table_api_key="test-key",
            log_level="INFO",
        )
        scraper = MLSScraper(mock_config)
        mock_page = MagicMock()

        with patch("src.scraper.browser.ElementInteractor") as mock_interactor_class:
            mock_interactor = MagicMock()
            # All selectors fail
            mock_interactor.click_element = AsyncMock(return_value=False)
            mock_interactor_class.return_value = mock_interactor

            # Should log warning but not raise error
            await scraper._click_academy_tab(mock_page)


# Phase 5: Retry Logic Tests
class TestMLSScraperRetryLogic:
    """Test retry logic for filters, dates, and matches."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock ScrapingConfig."""
        return ScrapingConfig(
            age_group="U14",
            division="Northeast",
            club="",
            competition="",
            look_back_days=1,
            start_date=datetime.now().date(),
            end_date=datetime.now().date(),
            missing_table_api_url="https://api.test.com",
            missing_table_api_key="test-key",
            log_level="INFO",
        )

    @pytest.fixture
    def mls_scraper(self, mock_config):
        """Create MLSScraper instance."""
        return MLSScraper(mock_config)

    @pytest.mark.asyncio
    async def test_apply_filters_with_retry_success(self, mls_scraper):
        """Test filter application succeeds."""
        mock_page = MagicMock()

        with patch(
            "src.scraper.mls_scraper.MLSFilterApplicator"
        ) as mock_applicator_class:
            mock_applicator = MagicMock()
            mock_applicator.apply_all_filters = AsyncMock(return_value=True)
            mock_applicator_class.return_value = mock_applicator

            await mls_scraper._apply_filters_with_retry(mock_page)

            mock_applicator.apply_all_filters.assert_called_once()

    @pytest.mark.asyncio
    async def test_apply_filters_retry_on_failure(self, mls_scraper):
        """Test filter application retries on failure."""
        mock_page = MagicMock()

        with (
            patch(
                "src.scraper.mls_scraper.MLSFilterApplicator"
            ) as mock_applicator_class,
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_applicator = MagicMock()
            # Fail twice, then succeed
            mock_applicator.apply_all_filters = AsyncMock(
                side_effect=[Exception("Fail 1"), Exception("Fail 2"), True]
            )
            mock_applicator_class.return_value = mock_applicator

            await mls_scraper._apply_filters_with_retry(mock_page)

            assert mock_applicator.apply_all_filters.call_count == 3

    @pytest.mark.asyncio
    async def test_set_date_range_with_retry_success(self, mls_scraper):
        """Test date range setting succeeds."""
        mock_page = MagicMock()

        with patch(
            "src.scraper.mls_scraper.MLSCalendarInteractor"
        ) as mock_calendar_class:
            mock_calendar = MagicMock()
            mock_calendar.set_date_range_filter = AsyncMock(return_value=True)
            mock_calendar_class.return_value = mock_calendar

            await mls_scraper._set_date_range_with_retry(mock_page)

            mock_calendar.set_date_range_filter.assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_matches_with_retry_success(self, mls_scraper):
        """Test match extraction succeeds."""
        mock_page = MagicMock()
        sample_matches = [
            Match(
                match_id="test_1",
                home_team="Team A",
                away_team="Team B",
                match_datetime=datetime.now() + timedelta(days=7),
            )
        ]

        with patch("src.scraper.mls_scraper.MLSMatchExtractor") as mock_extractor_class:
            mock_extractor = MagicMock()
            mock_extractor.extract_matches = AsyncMock(return_value=sample_matches)
            mock_extractor_class.return_value = mock_extractor

            matches = await mls_scraper._extract_matches_with_retry(mock_page)

            assert len(matches) == 1
            assert mls_scraper.execution_metrics.games_scheduled == 1

    @pytest.mark.asyncio
    async def test_emit_final_metrics(self, mls_scraper):
        """Test final metrics emission."""
        sample_matches = [
            Match(
                match_id="test_1",
                home_team="Team A",
                away_team="Team B",
                match_datetime=datetime.now(),
            )
        ]

        # Set some metrics
        mls_scraper.execution_metrics.games_scheduled = 1
        mls_scraper.execution_metrics.games_scored = 0

        # Should not raise error
        await mls_scraper._emit_final_metrics(sample_matches)
