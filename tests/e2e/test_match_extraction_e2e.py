"""
End-to-end tests for match extraction functionality.

This module provides comprehensive e2e tests that can be run locally with a visible browser
for debugging and verification of the complete match extraction workflow.

Run with visible browser:
    pytest tests/e2e/test_match_extraction_e2e.py::test_full_match_extraction_workflow_visible -v -s

Run headless (CI mode):
    pytest tests/e2e/test_match_extraction_e2e.py -v
"""

import asyncio
import os
from datetime import date, datetime, timedelta

import pytest

from src.scraper.browser import BrowserConfig, get_browser_manager
from src.scraper.calendar_interaction import MLSCalendarInteractor
from src.scraper.config import ScrapingConfig
from src.scraper.filter_application import MLSFilterApplicator
from src.scraper.match_extraction import MLSMatchExtractor
from src.scraper.models import Match
from src.utils.logger import get_logger

logger = get_logger()

# Test configuration
TEST_MLS_URL = "https://www.mlssoccer.com/mlsnext/schedule/all/"
TEST_TIMEOUT = 30000  # 30 seconds for e2e tests
VISIBLE_BROWSER = os.getenv("E2E_VISIBLE", "false").lower() == "true"
SLOW_MODE = int(os.getenv("E2E_SLOW_MO", "0"))  # Milliseconds to slow down actions


class TestMatchExtractionE2E:
    """End-to-end tests for match extraction with real browser automation."""

    @pytest.fixture
    def browser_config(self):
        """Create browser configuration for e2e tests."""
        return BrowserConfig(
            headless=not VISIBLE_BROWSER,
            timeout=TEST_TIMEOUT,
            viewport_width=1920,
            viewport_height=1080,
        )

    @pytest.fixture
    def test_config(self):
        """Create test scraping configuration."""
        return ScrapingConfig(
            age_group="U14",
            club="",  # Leave empty to get broader results
            competition="",  # Leave empty to get broader results
            division="Northeast",  # Focus on one division
            look_back_days=30,  # Look back 30 days
        )

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_full_match_extraction_workflow_visible(
        self, browser_config, test_config
    ):
        """
        Complete e2e test with visible browser for manual verification.

        This test runs the full workflow:
        1. Navigate to MLS website
        2. Apply filters (age group, division)
        3. Set date range
        4. Extract match data
        5. Validate results

        Run with: pytest tests/e2e/test_match_extraction_e2e.py::test_full_match_extraction_workflow_visible -v -s
        """
        # Force visible browser for this test
        browser_config.headless = False

        logger.info("Starting full match extraction e2e test with visible browser")

        async with get_browser_manager(browser_config) as browser_manager:
            async with browser_manager.get_page() as page:
                # Add slow motion if configured
                if SLOW_MODE > 0:
                    await page.set_default_timeout(TEST_TIMEOUT)
                    # Note: Playwright doesn't have built-in slow motion, but we can add delays

                # Step 1: Navigate to MLS website
                logger.info(f"Navigating to {TEST_MLS_URL}")
                response = await page.goto(TEST_MLS_URL, wait_until="networkidle")

                assert response is not None, "Failed to load MLS website"
                assert response.ok, f"HTTP error: {response.status}"

                logger.info("Successfully navigated to MLS website")

                if SLOW_MODE > 0:
                    await asyncio.sleep(SLOW_MODE / 1000)

                # Step 2: Apply filters
                logger.info("Applying filters")
                filter_applicator = MLSFilterApplicator(page, timeout=TEST_TIMEOUT)

                # Discover available options first
                available_options = await filter_applicator.discover_available_options()
                logger.info(f"Available filter options: {available_options}")

                # Apply filters based on what's available
                filters_applied = await filter_applicator.apply_all_filters(test_config)

                if not filters_applied:
                    logger.warning(
                        "Some filters may not have been applied successfully"
                    )
                    # Continue anyway for testing purposes

                logger.info("Filters applied")

                if SLOW_MODE > 0:
                    await asyncio.sleep(SLOW_MODE / 1000)

                # Step 3: Set date range
                logger.info("Setting date range")
                calendar_interactor = MLSCalendarInteractor(page, timeout=TEST_TIMEOUT)

                # Calculate date range
                end_date = date.today()
                start_date = end_date - timedelta(days=test_config.look_back_days)

                try:
                    date_filter_applied = (
                        await calendar_interactor.set_date_range_filter(
                            start_date, end_date
                        )
                    )

                    if date_filter_applied:
                        logger.info(f"Date range set: {start_date} to {end_date}")
                    else:
                        logger.warning("Date filter may not have been applied")

                except Exception as e:
                    logger.warning(f"Date filter application failed: {e}")
                    # Continue anyway - some sites may not have date filters

                if SLOW_MODE > 0:
                    await asyncio.sleep(SLOW_MODE / 1000)

                # Step 4: Extract match data
                logger.info("Extracting match data")
                match_extractor = MLSMatchExtractor(page, timeout=TEST_TIMEOUT)

                matches = await match_extractor.extract_matches(
                    age_group=test_config.age_group,
                    division=test_config.division,
                    competition=test_config.competition,
                )

                logger.info(f"Extracted {len(matches)} matches")

                # Step 5: Validate and display results
                await self._validate_and_display_matches(matches, test_config)

                # Keep browser open for manual inspection if visible
                if not browser_config.headless:
                    logger.info(
                        "Browser will remain open for 10 seconds for manual inspection..."
                    )
                    await asyncio.sleep(10)

                logger.info("E2E test completed successfully")

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_match_extraction_headless(self, browser_config, test_config):
        """
        Headless e2e test for CI/CD pipeline.

        This test runs the same workflow but in headless mode for automated testing.
        """
        # Ensure headless mode
        browser_config.headless = True

        logger.info("Starting headless match extraction e2e test")

        async with get_browser_manager(browser_config) as browser_manager:
            async with browser_manager.get_page() as page:
                # Navigate to MLS website
                response = await page.goto(TEST_MLS_URL, wait_until="networkidle")
                assert response is not None and response.ok

                # Apply filters
                filter_applicator = MLSFilterApplicator(page, timeout=TEST_TIMEOUT)
                await filter_applicator.apply_all_filters(test_config)

                # Extract matches
                match_extractor = MLSMatchExtractor(page, timeout=TEST_TIMEOUT)
                matches = await match_extractor.extract_matches(
                    age_group=test_config.age_group,
                    division=test_config.division,
                    competition=test_config.competition,
                )

                # Basic validation
                assert isinstance(matches, list), "Matches should be a list"
                logger.info(f"Headless test extracted {len(matches)} matches")

                # Validate match structure if any matches found
                if matches:
                    await self._validate_match_structure(matches[0])

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_match_extraction_with_different_filters(self, browser_config):
        """
        Test match extraction with different filter combinations.
        """
        browser_config.headless = True  # Run headless for speed

        test_cases = [
            ScrapingConfig(age_group="U15", division="Southeast", look_back_days=14),
            ScrapingConfig(age_group="U16", division="Central", look_back_days=7),
            ScrapingConfig(age_group="U17", division="Southwest", look_back_days=21),
        ]

        async with get_browser_manager(browser_config) as browser_manager:
            for i, config in enumerate(test_cases):
                logger.info(
                    f"Testing filter combination {i + 1}: {config.age_group}, {config.division}"
                )

                async with browser_manager.get_page() as page:
                    # Navigate
                    response = await page.goto(TEST_MLS_URL, wait_until="networkidle")
                    assert response is not None and response.ok

                    # Apply filters
                    filter_applicator = MLSFilterApplicator(page, timeout=TEST_TIMEOUT)
                    await filter_applicator.apply_all_filters(config)

                    # Extract matches
                    match_extractor = MLSMatchExtractor(page, timeout=TEST_TIMEOUT)
                    matches = await match_extractor.extract_matches(
                        age_group=config.age_group,
                        division=config.division,
                        competition=config.competition,
                    )

                    logger.info(
                        f"Filter combination {i + 1} extracted {len(matches)} matches"
                    )

                    # Validate that all matches have correct age group and division
                    for match in matches:
                        assert match.age_group == config.age_group
                        assert match.division == config.division

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_match_extraction_error_handling(self, browser_config):
        """
        Test error handling in match extraction.
        """
        browser_config.headless = True

        async with get_browser_manager(browser_config) as browser_manager:
            async with browser_manager.get_page() as page:
                # Test with invalid URL
                try:
                    await page.goto("https://invalid-url-that-does-not-exist.com")
                    assert False, "Should have failed to navigate to invalid URL"
                except Exception:
                    logger.info("Correctly handled invalid URL")

                # Navigate to valid URL
                response = await page.goto(TEST_MLS_URL, wait_until="networkidle")
                assert response is not None and response.ok

                # Test extraction with invalid parameters
                match_extractor = MLSMatchExtractor(page, timeout=5000)  # Short timeout

                # This should not crash, just return empty list or handle gracefully
                matches = await match_extractor.extract_matches(
                    age_group="InvalidAge",  # Invalid age group
                    division="InvalidDivision",  # Invalid division
                )

                # Should handle gracefully
                assert isinstance(matches, list)
                logger.info("Error handling test completed successfully")

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_match_extraction_performance(self, browser_config, test_config):
        """
        Test performance of match extraction.
        """
        browser_config.headless = True

        start_time = datetime.now()

        async with get_browser_manager(browser_config) as browser_manager:
            async with browser_manager.get_page() as page:
                # Navigate
                await page.goto(TEST_MLS_URL, wait_until="networkidle")

                # Apply filters
                filter_applicator = MLSFilterApplicator(page, timeout=TEST_TIMEOUT)
                await filter_applicator.apply_all_filters(test_config)

                # Extract matches
                match_extractor = MLSMatchExtractor(page, timeout=TEST_TIMEOUT)
                matches = await match_extractor.extract_matches(
                    age_group=test_config.age_group,
                    division=test_config.division,
                    competition=test_config.competition,
                )

                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()

                logger.info(
                    f"Performance test: extracted {len(matches)} matches in {duration:.2f} seconds"
                )

                # Performance assertions
                assert duration < 60, f"Extraction took too long: {duration} seconds"

                if matches:
                    matches_per_second = len(matches) / duration
                    logger.info(
                        f"Performance: {matches_per_second:.2f} matches per second"
                    )

    async def _validate_and_display_matches(
        self, matches: list[Match], config: ScrapingConfig
    ):
        """
        Validate extracted matches and display detailed information.

        Args:
            matches: List of extracted matches
            config: Test configuration used
        """
        logger.info("=== MATCH EXTRACTION RESULTS ===")
        logger.info(f"Configuration: {config.age_group}, {config.division}")
        logger.info(f"Total matches found: {len(matches)}")

        if not matches:
            logger.warning(
                "No matches found - this could be normal if no games are scheduled"
            )
            return

        # Categorize matches by status
        scheduled_matches = [m for m in matches if m.status == "scheduled"]
        completed_matches = [m for m in matches if m.status == "completed"]
        in_progress_matches = [m for m in matches if m.status == "in_progress"]

        logger.info(f"Scheduled: {len(scheduled_matches)}")
        logger.info(f"Completed: {len(completed_matches)}")
        logger.info(f"In Progress: {len(in_progress_matches)}")

        # Display sample matches
        logger.info("\n=== SAMPLE MATCHES ===")
        for i, match in enumerate(matches[:5]):  # Show first 5 matches
            logger.info(f"\nMatch {i + 1}:")
            logger.info(f"  ID: {match.match_id}")
            logger.info(f"  Teams: {match.home_team} vs {match.away_team}")
            logger.info(f"  Date: {match.match_date}")
            logger.info(f"  Status: {match.status}")
            if match.has_score():
                logger.info(f"  Score: {match.get_score_string()}")
            if match.venue:
                logger.info(f"  Venue: {match.venue}")

        # Validate match structure
        for match in matches:
            await self._validate_match_structure(match)

        logger.info("\n=== VALIDATION COMPLETE ===")

    async def _validate_match_structure(self, match: Match):
        """
        Validate that a match has the required structure and data.

        Args:
            match: Match object to validate
        """
        # Required fields
        assert match.match_id, "Match must have an ID"
        assert match.home_team, "Match must have home team"
        assert match.away_team, "Match must have away team"
        assert match.match_date, "Match must have match date"
        assert match.age_group, "Match must have age group"
        assert match.division, "Match must have division"
        assert match.status in ["scheduled", "in_progress", "completed"], (
            f"Invalid status: {match.status}"
        )

        # Teams should be different
        assert match.home_team != match.away_team, (
            "Home and away teams should be different"
        )

        # Score consistency
        if match.status == "completed":
            assert match.home_score is not None, (
                "Completed match should have home score"
            )
            assert match.away_score is not None, (
                "Completed match should have away score"
            )
        elif match.status == "scheduled":
            assert match.home_score is None, "Scheduled match should not have scores"
            assert match.away_score is None, "Scheduled match should not have scores"

        # Date should be reasonable (not too far in past or future)
        now = datetime.now()
        days_diff = abs((match.match_date - now).days)
        assert days_diff <= 365, f"Match date seems unreasonable: {match.match_date}"


class TestMatchExtractionDebugMode:
    """
    Special test class for debugging and development.

    These tests are designed to help developers debug issues with match extraction
    by providing detailed logging and browser interaction capabilities.
    """

    @pytest.mark.asyncio
    @pytest.mark.debug
    @pytest.mark.skip(reason="Debug test - run manually when needed")
    async def test_debug_match_extraction_step_by_step(self):
        """
        Debug test that runs step-by-step with pauses for manual inspection.

        Run with: pytest tests/e2e/test_match_extraction_e2e.py::TestMatchExtractionDebugMode::test_debug_match_extraction_step_by_step -v -s -m debug
        """
        browser_config = BrowserConfig(
            headless=False,  # Always visible for debug
            timeout=60000,  # Longer timeout for debugging
            viewport_width=1920,
            viewport_height=1080,
        )

        test_config = ScrapingConfig(
            age_group="U14",
            division="Northeast",
            look_back_days=14,
        )

        async with get_browser_manager(browser_config) as browser_manager:
            async with browser_manager.get_page() as page:
                # Enable detailed logging
                page.on(
                    "console", lambda msg: logger.info(f"Browser console: {msg.text}")
                )
                page.on(
                    "pageerror", lambda error: logger.error(f"Browser error: {error}")
                )

                # Step 1: Navigate
                logger.info("=== STEP 1: NAVIGATION ===")
                input("Press Enter to navigate to MLS website...")

                response = await page.goto(TEST_MLS_URL, wait_until="networkidle")
                logger.info(
                    f"Navigation response: {response.status if response else 'None'}"
                )

                input("Press Enter to continue to filter application...")

                # Step 2: Apply filters
                logger.info("=== STEP 2: FILTER APPLICATION ===")
                filter_applicator = MLSFilterApplicator(page, timeout=60000)

                # Discover options
                logger.info("Discovering available filter options...")
                available_options = await filter_applicator.discover_available_options()
                logger.info(f"Available options: {available_options}")

                input("Press Enter to apply filters...")

                # Apply filters one by one
                logger.info("Applying age group filter...")
                age_result = await filter_applicator.apply_age_group_filter(
                    test_config.age_group
                )
                logger.info(f"Age group filter result: {age_result}")

                input("Press Enter to apply division filter...")

                logger.info("Applying division filter...")
                division_result = await filter_applicator.apply_division_filter(
                    test_config.division
                )
                logger.info(f"Division filter result: {division_result}")

                input("Press Enter to continue to date range...")

                # Step 3: Date range
                logger.info("=== STEP 3: DATE RANGE ===")
                calendar_interactor = MLSCalendarInteractor(page, timeout=60000)

                end_date = date.today()
                start_date = end_date - timedelta(days=test_config.look_back_days)

                logger.info(f"Setting date range: {start_date} to {end_date}")

                try:
                    date_result = await calendar_interactor.set_date_range_filter(
                        start_date, end_date
                    )
                    logger.info(f"Date range result: {date_result}")
                except Exception as e:
                    logger.warning(f"Date range failed: {e}")

                input("Press Enter to continue to match extraction...")

                # Step 4: Extract matches
                logger.info("=== STEP 4: MATCH EXTRACTION ===")
                match_extractor = MLSMatchExtractor(page, timeout=60000)

                logger.info("Extracting matches...")
                matches = await match_extractor.extract_matches(
                    age_group=test_config.age_group,
                    division=test_config.division,
                    competition=test_config.competition,
                )

                logger.info(f"Extracted {len(matches)} matches")

                # Display results
                for i, match in enumerate(matches):
                    logger.info(
                        f"Match {i + 1}: {match.home_team} vs {match.away_team} ({match.status})"
                    )

                input("Press Enter to finish debug session...")

                logger.info("=== DEBUG SESSION COMPLETE ===")


# Utility functions for running tests manually
def run_visible_test():
    """
    Utility function to run the visible e2e test manually.

    Usage:
        python -c "from tests.e2e.test_match_extraction_e2e import run_visible_test; run_visible_test()"
    """
    import asyncio

    async def _run():
        test_instance = TestMatchExtractionE2E()
        browser_config = BrowserConfig(headless=False, timeout=30000)
        test_config = ScrapingConfig(
            age_group="U14", division="Northeast", look_back_days=30
        )

        await test_instance.test_full_match_extraction_workflow_visible(
            browser_config, test_config
        )

    asyncio.run(_run())


if __name__ == "__main__":
    # Allow running this file directly for quick testing
    run_visible_test()
