"""
Integration tests for MLSScraper complete workflow.

These tests verify the end-to-end scraping workflow including browser management,
filter application, calendar interaction, match extraction, error handling,
and metrics emission.
"""

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.scraper.config import ScrapingConfig
from src.scraper.mls_scraper import MLSScraper, MLSScraperError
from src.scraper.models import Match


class TestMLSScraperIntegration:
    """Integration tests for MLSScraper complete workflow."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock scraping configuration."""
        return ScrapingConfig(
            age_group="U14",
            club="Test Club",
            competition="Test Competition",
            division="Northeast",
            look_back_days=7,
            start_date=date.today() - timedelta(days=7),
            end_date=date.today(),
            missing_table_api_url="https://api.missing-table.com",
            missing_table_api_key="test-api-key",
            log_level="INFO",
        )

    @pytest.fixture
    def sample_matches(self):
        """Create sample match data for testing."""
        return [
            Match(
                match_id="U14_Northeast_0_20241219",
                home_team="Team A",
                away_team="Team B",
                match_date=date.today(),
                age_group="U14",
                division="Northeast",
                status="scheduled",
            ),
            Match(
                match_id="U14_Northeast_1_20241219",
                home_team="Team C",
                away_team="Team D",
                match_date=date.today(),
                age_group="U14",
                division="Northeast",
                status="completed",
                home_score=2,
                away_score=1,
            ),
        ]

    @pytest.mark.asyncio
    async def test_successful_scraping_workflow(self, mock_config, sample_matches):
        """Test successful end-to-end scraping workflow."""
        scraper = MLSScraper(mock_config)

        # Mock browser manager
        mock_browser_manager = MagicMock()
        mock_browser_manager.cleanup = AsyncMock()
        scraper.browser_manager = mock_browser_manager

        with (
            patch.object(scraper, "_initialize_browser_with_retry") as mock_init,
            patch.object(scraper, "_execute_scraping_workflow") as mock_execute,
            patch.object(scraper, "_emit_final_metrics") as mock_emit,
        ):
            # Configure mocks
            mock_init.return_value = None

            # Mock _execute_scraping_workflow to update metrics and return matches
            async def mock_execute_workflow():
                # Update metrics as the real method would
                games_scheduled = len(
                    [m for m in sample_matches if m.status == "scheduled"]
                )
                games_scored = len([m for m in sample_matches if m.has_score()])
                scraper.execution_metrics.games_scheduled = games_scheduled
                scraper.execution_metrics.games_scored = games_scored
                return sample_matches

            mock_execute.side_effect = mock_execute_workflow

            # Execute scraping
            result = await scraper.scrape_matches()

            # Verify results
            assert result == sample_matches
            assert len(result) == 2

            # Verify workflow steps were called
            mock_init.assert_called_once()
            mock_execute.assert_called_once()
            mock_emit.assert_called_once_with(sample_matches)

            # Verify cleanup was called
            mock_browser_manager.cleanup.assert_called_once()

            # Verify metrics were updated
            metrics = scraper.get_execution_metrics()
            assert metrics.games_scheduled == 1  # One scheduled match
            assert metrics.games_scored == 1  # One completed match with score
            assert metrics.execution_duration_ms >= 0  # Duration should be non-negative

    @pytest.mark.asyncio
    async def test_browser_initialization_failure(self, mock_config):
        """Test handling of browser initialization failure."""
        scraper = MLSScraper(mock_config)

        with patch.object(
            scraper,
            "_initialize_browser_with_retry",
            side_effect=MLSScraperError("Browser init failed"),
        ):
            with pytest.raises(MLSScraperError, match="Browser init failed"):
                await scraper.scrape_matches()

            # Verify error metrics
            metrics = scraper.get_execution_metrics()
            assert metrics.errors_encountered == 1

    @pytest.mark.asyncio
    async def test_scraping_workflow_failure(self, mock_config):
        """Test handling of scraping workflow failure."""
        scraper = MLSScraper(mock_config)

        # Mock browser manager
        mock_browser_manager = MagicMock()
        mock_browser_manager.cleanup = AsyncMock()
        scraper.browser_manager = mock_browser_manager

        with (
            patch.object(scraper, "_initialize_browser_with_retry") as mock_init,
            patch.object(
                scraper,
                "_execute_scraping_workflow",
                side_effect=MLSScraperError("Workflow failed"),
            ),
        ):
            mock_init.return_value = None

            with pytest.raises(MLSScraperError, match="Workflow failed"):
                await scraper.scrape_matches()

            # Verify cleanup was called
            mock_browser_manager.cleanup.assert_called_once()

            # Verify error metrics
            metrics = scraper.get_execution_metrics()
            assert metrics.errors_encountered == 1

    @pytest.mark.asyncio
    async def test_browser_initialization_with_retry(self, mock_config):
        """Test browser initialization with retry logic."""
        scraper = MLSScraper(mock_config)

        # Mock browser manager that fails twice then succeeds
        mock_browser_manager = MagicMock()
        mock_browser_manager.initialize = AsyncMock()
        mock_browser_manager.initialize.side_effect = [
            Exception("First failure"),
            Exception("Second failure"),
            None,  # Success on third attempt
        ]

        with (
            patch(
                "src.scraper.mls_scraper.BrowserManager",
                return_value=mock_browser_manager,
            ),
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            await scraper._initialize_browser_with_retry()

            # Verify retries occurred
            assert mock_browser_manager.initialize.call_count == 3
            assert mock_sleep.call_count == 2  # Two retry delays

            # Verify browser manager was set
            assert scraper.browser_manager == mock_browser_manager

    @pytest.mark.asyncio
    async def test_browser_initialization_max_retries_exceeded(self, mock_config):
        """Test browser initialization failure after max retries."""
        scraper = MLSScraper(mock_config)

        # Mock browser manager that always fails
        mock_browser_manager = MagicMock()
        mock_browser_manager.initialize = AsyncMock(
            side_effect=Exception("Always fails")
        )

        with (
            patch(
                "src.scraper.mls_scraper.BrowserManager",
                return_value=mock_browser_manager,
            ),
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            with pytest.raises(
                MLSScraperError, match="Browser initialization failed after .* attempts"
            ):
                await scraper._initialize_browser_with_retry()

            # Verify all retries were attempted
            assert mock_browser_manager.initialize.call_count == scraper.MAX_RETRIES + 1
            assert mock_sleep.call_count == scraper.MAX_RETRIES

    @pytest.mark.asyncio
    async def test_execute_scraping_workflow_steps(self, mock_config):
        """Test individual steps of the scraping workflow."""
        scraper = MLSScraper(mock_config)
        scraper.browser_manager = MagicMock()

        # Mock page context manager
        mock_page = MagicMock()
        mock_page_context = AsyncMock()
        mock_page_context.__aenter__ = AsyncMock(return_value=mock_page)
        mock_page_context.__aexit__ = AsyncMock(return_value=None)
        scraper.browser_manager.get_page.return_value = mock_page_context

        sample_matches = [
            Match(
                match_id="test_match",
                home_team="Team A",
                away_team="Team B",
                match_date=date.today(),
                age_group="U14",
                division="Northeast",
                status="scheduled",
            )
        ]

        with (
            patch.object(scraper, "_navigate_to_mls_website") as mock_navigate,
            patch.object(scraper, "_apply_filters_with_retry") as mock_filters,
            patch.object(scraper, "_set_date_range_with_retry") as mock_date_range,
            patch.object(
                scraper, "_extract_matches_with_retry", return_value=sample_matches
            ) as mock_extract,
        ):
            result = await scraper._execute_scraping_workflow()

            # Verify all workflow steps were called in order
            mock_navigate.assert_called_once_with(mock_page)
            mock_filters.assert_called_once_with(mock_page)
            mock_date_range.assert_called_once_with(mock_page)
            mock_extract.assert_called_once_with(mock_page)

            # Verify result
            assert result == sample_matches

    @pytest.mark.asyncio
    async def test_navigate_to_mls_website(self, mock_config):
        """Test navigation to MLS website."""
        scraper = MLSScraper(mock_config)
        mock_page = MagicMock()

        with patch("src.scraper.mls_scraper.PageNavigator") as mock_navigator_class:
            mock_navigator = MagicMock()
            mock_navigator.navigate_to = AsyncMock(return_value=True)
            mock_navigator_class.return_value = mock_navigator

            await scraper._navigate_to_mls_website(mock_page)

            # Verify navigator was created and called correctly
            mock_navigator_class.assert_called_once_with(
                mock_page, max_retries=scraper.MAX_RETRIES
            )
            mock_navigator.navigate_to.assert_called_once_with(
                scraper.MLS_NEXT_URL, wait_until="networkidle"
            )

    @pytest.mark.asyncio
    async def test_navigate_to_mls_website_failure(self, mock_config):
        """Test navigation failure handling."""
        scraper = MLSScraper(mock_config)
        mock_page = MagicMock()

        with patch("src.scraper.mls_scraper.PageNavigator") as mock_navigator_class:
            mock_navigator = MagicMock()
            mock_navigator.navigate_to = AsyncMock(return_value=False)
            mock_navigator_class.return_value = mock_navigator

            with pytest.raises(MLSScraperError, match="Failed to navigate to"):
                await scraper._navigate_to_mls_website(mock_page)

    @pytest.mark.asyncio
    async def test_apply_filters_with_retry_success(self, mock_config):
        """Test successful filter application."""
        scraper = MLSScraper(mock_config)
        mock_page = MagicMock()

        with patch(
            "src.scraper.mls_scraper.MLSFilterApplicator"
        ) as mock_applicator_class:
            mock_applicator = MagicMock()
            mock_applicator.apply_all_filters = AsyncMock(return_value=True)
            mock_applicator_class.return_value = mock_applicator

            await scraper._apply_filters_with_retry(mock_page)

            # Verify filter applicator was called correctly
            mock_applicator_class.assert_called_once_with(mock_page, timeout=15000)
            mock_applicator.apply_all_filters.assert_called_once_with(mock_config)

    @pytest.mark.asyncio
    async def test_apply_filters_with_retry_failure(self, mock_config):
        """Test filter application with retry and eventual failure."""
        scraper = MLSScraper(mock_config)
        mock_page = MagicMock()

        with (
            patch(
                "src.scraper.mls_scraper.MLSFilterApplicator"
            ) as mock_applicator_class,
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_applicator = MagicMock()
            mock_applicator.apply_all_filters = AsyncMock(return_value=False)
            mock_applicator_class.return_value = mock_applicator

            with pytest.raises(
                MLSScraperError, match="Filter application failed after .* attempts"
            ):
                await scraper._apply_filters_with_retry(mock_page)

            # Verify retries occurred
            assert (
                mock_applicator.apply_all_filters.call_count == scraper.MAX_RETRIES + 1
            )
            assert mock_sleep.call_count == scraper.MAX_RETRIES

            # Verify error metrics
            assert scraper.execution_metrics.errors_encountered == 1

    @pytest.mark.asyncio
    async def test_set_date_range_with_retry_success(self, mock_config):
        """Test successful date range setting."""
        scraper = MLSScraper(mock_config)
        mock_page = MagicMock()

        with patch(
            "src.scraper.mls_scraper.MLSCalendarInteractor"
        ) as mock_interactor_class:
            mock_interactor = MagicMock()
            mock_interactor.set_date_range_filter = AsyncMock(return_value=True)
            mock_interactor_class.return_value = mock_interactor

            await scraper._set_date_range_with_retry(mock_page)

            # Verify calendar interactor was called correctly
            mock_interactor_class.assert_called_once_with(mock_page, timeout=15000)
            mock_interactor.set_date_range_filter.assert_called_once_with(
                mock_config.start_date, mock_config.end_date
            )

    @pytest.mark.asyncio
    async def test_extract_matches_with_retry_success(
        self, mock_config, sample_matches
    ):
        """Test successful match extraction."""
        scraper = MLSScraper(mock_config)
        mock_page = MagicMock()

        with patch("src.scraper.mls_scraper.MLSMatchExtractor") as mock_extractor_class:
            mock_extractor = MagicMock()
            mock_extractor.extract_matches = AsyncMock(return_value=sample_matches)
            mock_extractor_class.return_value = mock_extractor

            result = await scraper._extract_matches_with_retry(mock_page)

            # Verify extractor was called correctly
            mock_extractor_class.assert_called_once_with(mock_page, timeout=15000)
            mock_extractor.extract_matches.assert_called_once_with(
                age_group=mock_config.age_group,
                division=mock_config.division,
                competition=mock_config.competition,
            )

            # Verify result and metrics
            assert result == sample_matches
            assert scraper.execution_metrics.games_scheduled == 1
            assert scraper.execution_metrics.games_scored == 1

    @pytest.mark.asyncio
    async def test_emit_final_metrics(self, mock_config, sample_matches):
        """Test final metrics emission."""
        scraper = MLSScraper(mock_config)
        scraper.execution_metrics.games_scheduled = 1
        scraper.execution_metrics.games_scored = 1
        scraper.execution_metrics.execution_duration_ms = 5000

        with patch("src.scraper.mls_scraper.metrics") as mock_metrics:
            await scraper._emit_final_metrics(sample_matches)

            # Verify metrics were recorded
            mock_metrics.record_games_scheduled.assert_called_once_with(
                count=1,
                labels={
                    "age_group": mock_config.age_group,
                    "division": mock_config.division,
                    "competition": mock_config.competition,
                },
            )

            mock_metrics.record_games_scored.assert_called_once_with(
                count=1,
                labels={
                    "age_group": mock_config.age_group,
                    "division": mock_config.division,
                    "competition": mock_config.competition,
                },
            )

            mock_metrics.record_browser_operation.assert_called_once_with(
                operation="full_scraping_workflow",
                success=True,
                duration_seconds=5.0,
                labels={
                    "age_group": mock_config.age_group,
                    "division": mock_config.division,
                },
            )

    def test_calculate_retry_delay(self, mock_config):
        """Test retry delay calculation with exponential backoff."""
        scraper = MLSScraper(mock_config)

        # Test exponential backoff
        assert scraper._calculate_retry_delay(0) == 1.0  # Base delay
        assert scraper._calculate_retry_delay(1) == 2.0  # 1 * 2^1
        assert scraper._calculate_retry_delay(2) == 4.0  # 1 * 2^2
        assert scraper._calculate_retry_delay(3) == 8.0  # 1 * 2^3

    def test_get_execution_metrics(self, mock_config):
        """Test execution metrics retrieval."""
        scraper = MLSScraper(mock_config)

        # Update some metrics
        scraper.execution_metrics.games_scheduled = 5
        scraper.execution_metrics.games_scored = 3
        scraper.execution_metrics.execution_duration_ms = 10000

        metrics = scraper.get_execution_metrics()

        assert metrics.games_scheduled == 5
        assert metrics.games_scored == 3
        assert metrics.execution_duration_ms == 10000
        assert metrics.errors_encountered == 0

    @pytest.mark.asyncio
    async def test_workflow_with_no_browser_manager(self, mock_config):
        """Test workflow execution without initialized browser manager."""
        scraper = MLSScraper(mock_config)
        # Don't initialize browser_manager

        with pytest.raises(MLSScraperError, match="Browser not initialized"):
            await scraper._execute_scraping_workflow()

    @pytest.mark.asyncio
    async def test_cleanup_on_exception(self, mock_config):
        """Test that browser cleanup occurs even when exceptions are raised."""
        scraper = MLSScraper(mock_config)

        with (
            patch.object(scraper, "_initialize_browser_with_retry") as mock_init,
            patch.object(
                scraper,
                "_execute_scraping_workflow",
                side_effect=Exception("Test error"),
            ),
        ):
            # Mock browser manager
            mock_browser_manager = MagicMock()
            mock_browser_manager.cleanup = AsyncMock()
            scraper.browser_manager = mock_browser_manager

            mock_init.return_value = None

            with pytest.raises(MLSScraperError):
                await scraper.scrape_matches()

            # Verify cleanup was called even though an exception occurred
            mock_browser_manager.cleanup.assert_called_once()


class TestMLSScraperConfiguration:
    """Test MLSScraper configuration and initialization."""

    def test_scraper_initialization(self):
        """Test scraper initialization with configuration."""
        config = ScrapingConfig(
            age_group="U16",
            club="Test Club",
            competition="Test Competition",
            division="Southwest",
            look_back_days=3,
            start_date=date.today() - timedelta(days=3),
            end_date=date.today(),
            missing_table_api_url="https://api.test.com",
            missing_table_api_key="test-key",
            log_level="DEBUG",
        )

        scraper = MLSScraper(config)

        assert scraper.config == config
        assert scraper.browser_manager is None
        assert scraper.execution_metrics.games_scheduled == 0
        assert scraper.execution_metrics.games_scored == 0
        assert scraper.execution_metrics.errors_encountered == 0

    def test_scraper_constants(self):
        """Test scraper constants are properly defined."""
        assert (
            MLSScraper.MLS_NEXT_URL == "https://www.mlssoccer.com/mlsnext/schedule/all/"
        )
        assert MLSScraper.MAX_RETRIES == 3
        assert MLSScraper.RETRY_DELAY_BASE == 1.0
        assert MLSScraper.RETRY_BACKOFF_MULTIPLIER == 2.0


if __name__ == "__main__":
    pytest.main([__file__])
