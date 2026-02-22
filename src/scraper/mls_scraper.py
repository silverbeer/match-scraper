"""
Core MLS scraper orchestration module.

This module provides the MLSScraper class that coordinates all scraping operations
including browser management, filter application, calendar interaction, match extraction,
error handling, retry logic, and metrics emission.
"""

import asyncio
import time
from typing import Any, Optional

from ..utils.logger import get_logger
from ..utils.metrics import get_metrics
from .browser import BrowserConfig, BrowserManager, PageNavigator
from .calendar_interaction import CalendarInteractionError, MLSCalendarInteractor
from .config import ScrapingConfig
from .filter_application import FilterApplicationError, MLSFilterApplicator
from .match_extraction import MLSMatchExtractor
from .models import Match, ScrapingMetrics

logger = get_logger()
metrics = get_metrics()


class MLSScraperError(Exception):
    """Custom exception for MLS scraper failures."""

    pass


class MLSScraper:
    """
    Core orchestrator for MLS match scraping operations.

    Coordinates browser management, filter application, calendar interaction,
    and match extraction with comprehensive error handling, retry logic,
    and metrics emission.
    """

    # MLS Next website URL
    MLS_NEXT_URL = "https://www.mlssoccer.com/mlsnext/schedule/all/"

    # Retry configuration
    MAX_RETRIES = 3
    RETRY_DELAY_BASE = 1.0  # Base delay in seconds
    RETRY_BACKOFF_MULTIPLIER = 2.0

    def __init__(
        self,
        config: ScrapingConfig,
        headless: bool = True,
    ):
        """
        Initialize MLS scraper with configuration.

        Args:
            config: Scraping configuration containing filters and settings
            headless: Whether to run browser in headless mode (default: True)
        """
        self.config = config
        self.headless = headless
        self.browser_manager: Optional[BrowserManager] = None
        self.execution_metrics = ScrapingMetrics(
            games_scheduled=0,
            games_scored=0,
            api_calls_successful=0,
            api_calls_failed=0,
            execution_duration_ms=0,
            errors_encountered=0,
        )

    async def scrape_matches(self) -> list[Match]:
        """
        Execute the complete scraping workflow.

        This method orchestrates the entire scraping process:
        1. Initialize browser
        2. Navigate to MLS website
        3. Apply filters
        4. Set date range
        5. Extract match data
        6. Emit metrics

        Returns:
            List of Match objects extracted from the website

        Raises:
            MLSScraperError: If scraping workflow fails
        """
        start_time = time.time()

        try:
            logger.info(
                "Starting MLS match scraping workflow",
                extra={
                    "age_group": self.config.age_group,
                    "division": self.config.division,
                    "date_range": f"{self.config.start_date} to {self.config.end_date}",
                    "club_filter": self.config.club or "All clubs",
                    "competition_filter": self.config.competition or "All competitions",
                },
            )

            # Initialize browser with retry logic
            await self._initialize_browser_with_retry()

            # Execute scraping workflow with metrics timing
            with metrics.time_operation("full_scraping_workflow"):
                matches = await self._execute_scraping_workflow()

            # Update execution metrics
            execution_duration_ms = int((time.time() - start_time) * 1000)
            self.execution_metrics.execution_duration_ms = execution_duration_ms

            # Emit final metrics
            await self._emit_final_metrics(matches)

            logger.info(
                "MLS match scraping workflow completed successfully",
                extra={
                    "matches_found": len(matches),
                    "games_scheduled": self.execution_metrics.games_scheduled,
                    "games_scored": self.execution_metrics.games_scored,
                    "duration_ms": execution_duration_ms,
                },
            )

            return matches

        except Exception as e:
            self.execution_metrics.errors_encountered += 1
            execution_duration_ms = int((time.time() - start_time) * 1000)
            self.execution_metrics.execution_duration_ms = execution_duration_ms

            logger.error(
                "MLS match scraping workflow failed",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "duration_ms": execution_duration_ms,
                    "errors_encountered": self.execution_metrics.errors_encountered,
                },
            )

            # Record error metric
            metrics.record_scraping_error(
                error_type=type(e).__name__,
                labels={
                    "age_group": self.config.age_group,
                    "division": self.config.division,
                },
            )

            raise MLSScraperError(f"Scraping workflow failed: {e}") from e

        finally:
            # Ensure browser cleanup
            if self.browser_manager:
                await self.browser_manager.cleanup()

    async def _initialize_browser_with_retry(self) -> None:
        """
        Initialize browser with retry logic.

        Raises:
            MLSScraperError: If browser initialization fails after all retries
        """
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                logger.info(
                    "Initializing browser",
                    extra={"attempt": attempt + 1, "max_retries": self.MAX_RETRIES + 1},
                )

                # Configure browser for container environment
                browser_config = BrowserConfig(
                    headless=self.headless,
                    timeout=30000,  # 30 seconds
                    viewport_width=1280,
                    viewport_height=720,
                )

                self.browser_manager = BrowserManager(browser_config)

                with metrics.time_operation("browser_initialization"):
                    await self.browser_manager.initialize()

                logger.info("Browser initialized successfully")
                return

            except Exception as e:
                logger.warning(
                    "Browser initialization failed",
                    extra={
                        "attempt": attempt + 1,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )

                if attempt < self.MAX_RETRIES:
                    delay = self._calculate_retry_delay(attempt)
                    logger.info(
                        "Retrying browser initialization",
                        extra={"delay_seconds": delay, "next_attempt": attempt + 2},
                    )
                    await asyncio.sleep(delay)
                else:
                    raise MLSScraperError(
                        f"Browser initialization failed after {self.MAX_RETRIES + 1} attempts: {e}"
                    ) from e

    async def _execute_scraping_workflow(self) -> list[Match]:
        """
        Execute the main scraping workflow steps.

        Returns:
            List of extracted matches

        Raises:
            MLSScraperError: If any workflow step fails
        """
        if not self.browser_manager:
            raise MLSScraperError("Browser not initialized")

        # Create page and navigate to MLS website
        async with self.browser_manager.get_page() as page:
            # Step 1: Navigate to MLS website
            await self._navigate_to_mls_website(page)

            # Step 2: Apply filters
            await self._apply_filters_with_retry(page)

            # Step 3: Set date range
            await self._set_date_range_with_retry(page)

            # Step 4: Extract match data
            matches = await self._extract_matches_with_retry(page)

            return matches

    async def _navigate_to_mls_website(self, page: Any) -> None:
        """
        Navigate to MLS Next website with retry logic and consent handling.

        Args:
            page: Playwright page instance

        Raises:
            MLSScraperError: If navigation fails after all retries
        """
        from .consent_handler import MLSConsentHandler

        navigator = PageNavigator(page, max_retries=self.MAX_RETRIES)

        logger.info("Navigating to MLS Next website", extra={"url": self.MLS_NEXT_URL})

        with metrics.time_operation("page_navigation"):
            success = await navigator.navigate_to(self.MLS_NEXT_URL, wait_until="load")

        if not success:
            raise MLSScraperError(f"Failed to navigate to {self.MLS_NEXT_URL}")

        logger.info("Successfully navigated to MLS Next website")

        # Handle cookie consent banner
        logger.info("Handling cookie consent banner")
        consent_handler = MLSConsentHandler(page)

        consent_handled = await consent_handler.handle_consent_banner()
        if not consent_handled:
            logger.warning("Cookie consent handling failed, continuing anyway")

        # Wait for page to be ready after consent
        page_ready = await consent_handler.wait_for_page_ready()
        if not page_ready:
            logger.warning("Page readiness check failed, continuing anyway")

        # Click Academy Division tab if needed
        if self.config.league == "Academy":
            await self._click_academy_tab(page)

        logger.info("Navigation and consent handling completed")

    async def _click_academy_tab(self, page: Any) -> None:
        """
        Click the Academy Division tab on the MLS Next schedule page.

        Args:
            page: Playwright page instance

        Raises:
            MLSScraperError: If clicking the Academy Division tab fails
        """
        from .browser import ElementInteractor

        logger.info("Clicking Academy Division tab")

        try:
            interactor = ElementInteractor(page)

            # Look for the Academy Division tab link
            # Based on Playwright MCP inspection, the link is: "MLS NEXT Academy Division Schedule"
            academy_tab_selectors = [
                "a:has-text('MLS NEXT Academy Division Schedule')",
                "text='MLS NEXT Academy Division Schedule'",
                "[href*='academy_division']",
                "[href*='/mlsnext/schedule/academy']",
            ]

            tab_clicked = False
            for selector in academy_tab_selectors:
                logger.info(
                    f"Trying to click Academy Division tab with selector: {selector}"
                )

                # Use click_element which handles waiting and clicking
                clicked = await interactor.click_element(selector, timeout=5000)

                if clicked:
                    logger.info(
                        f"Successfully clicked Academy Division tab with selector: {selector}"
                    )
                    # Wait for the page to navigate
                    await page.wait_for_timeout(2000)
                    tab_clicked = True
                    break

            if not tab_clicked:
                logger.warning(
                    "Could not find or click Academy Division tab - page structure may have changed"
                )

        except Exception as e:
            logger.error(
                f"Failed to click Academy Division tab: {e}",
                extra={"error": str(e), "error_type": type(e).__name__},
            )
            raise MLSScraperError(f"Failed to click Academy Division tab: {e}") from e

    async def _apply_filters_with_retry(self, page: Any) -> None:
        """
        Apply filters with retry logic.

        Args:
            page: Playwright page instance

        Raises:
            MLSScraperError: If filter application fails after all retries
        """
        filter_applicator = MLSFilterApplicator(page, timeout=15000)

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                logger.info(
                    "Applying filters",
                    extra={
                        "attempt": attempt + 1,
                        "age_group": self.config.age_group,
                        "club": self.config.club,
                        "competition": self.config.competition,
                        "division": self.config.division,
                    },
                )

                with metrics.time_operation("filter_application"):
                    success = await filter_applicator.apply_all_filters(self.config)

                if success:
                    logger.info("Filters applied successfully")
                    return
                else:
                    raise FilterApplicationError("Filter application returned False")

            except Exception as e:
                logger.warning(
                    "Filter application failed",
                    extra={
                        "attempt": attempt + 1,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )

                if attempt < self.MAX_RETRIES:
                    delay = self._calculate_retry_delay(attempt)
                    logger.info(
                        "Retrying filter application",
                        extra={"delay_seconds": delay, "next_attempt": attempt + 2},
                    )
                    await asyncio.sleep(delay)
                else:
                    self.execution_metrics.errors_encountered += 1
                    raise MLSScraperError(
                        f"Filter application failed after {self.MAX_RETRIES + 1} attempts: {e}"
                    ) from e

    async def _set_date_range_with_retry(self, page: Any) -> None:
        """
        Set date range filter with retry logic.

        Args:
            page: Playwright page instance

        Raises:
            MLSScraperError: If date range setting fails after all retries
        """
        calendar_interactor = MLSCalendarInteractor(page, timeout=15000)

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                logger.info(
                    "Setting date range filter",
                    extra={
                        "attempt": attempt + 1,
                        "start_date": str(self.config.start_date),
                        "end_date": str(self.config.end_date),
                    },
                )

                with metrics.time_operation("date_range_setting"):
                    success = await calendar_interactor.set_date_range_filter(
                        self.config.start_date, self.config.end_date
                    )

                if success:
                    logger.info("Date range filter set successfully")
                    return
                else:
                    raise CalendarInteractionError("Date range setting returned False")

            except Exception as e:
                logger.warning(
                    "Date range setting failed",
                    extra={
                        "attempt": attempt + 1,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )

                if attempt < self.MAX_RETRIES:
                    delay = self._calculate_retry_delay(attempt)
                    logger.info(
                        "Retrying date range setting",
                        extra={"delay_seconds": delay, "next_attempt": attempt + 2},
                    )
                    await asyncio.sleep(delay)
                else:
                    self.execution_metrics.errors_encountered += 1
                    raise MLSScraperError(
                        f"Date range setting failed after {self.MAX_RETRIES + 1} attempts: {e}"
                    ) from e

    async def _extract_matches_with_retry(self, page: Any) -> list[Match]:
        """
        Extract matches with retry logic.

        Args:
            page: Playwright page instance

        Returns:
            List of extracted matches

        Raises:
            MLSScraperError: If match extraction fails after all retries
        """
        match_extractor = MLSMatchExtractor(page, timeout=15000)

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                logger.info(
                    "Extracting matches",
                    extra={
                        "attempt": attempt + 1,
                        "age_group": self.config.age_group,
                        "division": self.config.division,
                    },
                )

                with metrics.time_operation("match_extraction"):
                    matches = await match_extractor.extract_matches(
                        age_group=self.config.age_group,
                        division=self.config.division,
                        competition=self.config.competition,
                    )

                # Apply client-side club filtering if specified
                # This serves as a fallback when website-side filtering fails
                if self.config.club:
                    total_before_filter = len(matches)
                    matches = [
                        m
                        for m in matches
                        if m.home_team == self.config.club
                        or m.away_team == self.config.club
                    ]
                    logger.info(
                        "Applied client-side club filter",
                        extra={
                            "club": self.config.club,
                            "matches_before": total_before_filter,
                            "matches_after": len(matches),
                            "filtered_out": total_before_filter - len(matches),
                        },
                    )

                # Update metrics based on extracted matches
                games_scheduled = len(
                    [m for m in matches if m.match_status == "scheduled"]
                )
                games_scored = len([m for m in matches if m.has_score()])

                self.execution_metrics.games_scheduled = games_scheduled
                self.execution_metrics.games_scored = games_scored

                # Log detailed match information for manual verification
                self._log_discovered_matches(matches)

                logger.info(
                    "Match extraction completed",
                    extra={
                        "total_matches": len(matches),
                        "games_scheduled": games_scheduled,
                        "games_scored": games_scored,
                    },
                )

                return matches

            except Exception as e:
                logger.warning(
                    "Match extraction failed",
                    extra={
                        "attempt": attempt + 1,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )

                if attempt < self.MAX_RETRIES:
                    delay = self._calculate_retry_delay(attempt)
                    logger.info(
                        "Retrying match extraction",
                        extra={"delay_seconds": delay, "next_attempt": attempt + 2},
                    )
                    await asyncio.sleep(delay)
                else:
                    self.execution_metrics.errors_encountered += 1
                    raise MLSScraperError(
                        f"Match extraction failed after {self.MAX_RETRIES + 1} attempts: {e}"
                    ) from e

        return []  # unreachable, but satisfies mypy

    async def _emit_final_metrics(self, matches: list[Match]) -> None:
        """
        Emit final metrics for the scraping operation.

        Args:
            matches: List of extracted matches
        """
        try:
            logger.info("Emitting final metrics")

            # Record games scheduled and scored metrics
            metrics.record_games_scheduled(
                count=self.execution_metrics.games_scheduled,
                labels={
                    "age_group": self.config.age_group,
                    "division": self.config.division,
                    "competition": self.config.competition or "none",
                },
            )

            metrics.record_games_scored(
                count=self.execution_metrics.games_scored,
                labels={
                    "age_group": self.config.age_group,
                    "division": self.config.division,
                    "competition": self.config.competition or "none",
                },
            )

            # Record browser operations
            metrics.record_browser_operation(
                operation="full_scraping_workflow",
                success=True,
                duration_seconds=self.execution_metrics.execution_duration_ms / 1000.0,
                labels={
                    "age_group": self.config.age_group,
                    "division": self.config.division,
                },
            )

            logger.info(
                "Final metrics emitted successfully",
                extra={
                    "games_scheduled": self.execution_metrics.games_scheduled,
                    "games_scored": self.execution_metrics.games_scored,
                    "execution_duration_ms": self.execution_metrics.execution_duration_ms,
                },
            )

        except Exception as e:
            logger.warning(
                "Failed to emit final metrics",
                extra={"error": str(e), "error_type": type(e).__name__},
            )

    def _log_discovered_matches(self, matches: list[Match]) -> None:
        """
        Log detailed information about discovered matches for manual verification.

        Args:
            matches: List of discovered matches
        """
        try:
            if not matches:
                logger.info("No matches discovered during scraping")
                return

            logger.info(
                "=== DISCOVERED MATCHES SUMMARY ===",
                extra={
                    "total_matches": len(matches),
                    "age_group": self.config.age_group,
                    "division": self.config.division,
                    "date_range": f"{self.config.start_date} to {self.config.end_date}",
                },
            )

            # Group matches by status for better organization
            scheduled_matches = [m for m in matches if m.match_status == "scheduled"]
            played_matches = [m for m in matches if m.match_status == "completed"]
            tbd_matches = [m for m in matches if m.match_status == "tbd"]
            in_progress_matches: list[Match] = []

            # Log scheduled matches
            if scheduled_matches:
                logger.info(f"=== SCHEDULED MATCHES ({len(scheduled_matches)}) ===")
                for i, match in enumerate(scheduled_matches, 1):
                    logger.info(
                        f"SCHEDULED #{i}: {match.home_team} vs {match.away_team}",
                        extra={
                            "match_id": match.match_id,
                            "date": str(match.match_datetime.date())
                            if match.match_datetime
                            else "Unknown",
                            "time": match.match_datetime.strftime("%I:%M %p")
                            if match.match_datetime
                            else "Unknown",
                            "venue": match.location or "Unknown",
                            "competition": match.competition or "Unknown",
                        },
                    )

            # Log played matches with scores
            if played_matches:
                logger.info(f"=== PLAYED MATCHES ({len(played_matches)}) ===")
                for i, match in enumerate(played_matches, 1):
                    score_info = match.get_score_string() or "Score unknown"
                    logger.info(
                        f"PLAYED #{i}: {match.home_team} vs {match.away_team} - {score_info}",
                        extra={
                            "match_id": match.match_id,
                            "date": str(match.match_datetime.date())
                            if match.match_datetime
                            else "Unknown",
                            "time": match.match_datetime.strftime("%I:%M %p")
                            if match.match_datetime
                            else "Unknown",
                            "venue": match.location or "Unknown",
                            "competition": match.competition or "Unknown",
                            "home_score": match.home_score,
                            "away_score": match.away_score,
                        },
                    )

            # Log TBD matches
            if tbd_matches:
                logger.info(f"=== TBD MATCHES ({len(tbd_matches)}) ===")
                for i, match in enumerate(tbd_matches, 1):
                    logger.info(
                        f"TBD #{i}: {match.home_team} vs {match.away_team} - TBD",
                        extra={
                            "match_id": match.match_id,
                            "date": str(match.match_datetime.date())
                            if match.match_datetime
                            else "Unknown",
                            "time": match.match_datetime.strftime("%I:%M %p")
                            if match.match_datetime
                            else "Unknown",
                            "venue": match.location or "Unknown",
                            "competition": match.competition or "Unknown",
                            "home_score": match.home_score,
                            "away_score": match.away_score,
                        },
                    )

            # Log in-progress matches
            if in_progress_matches:
                logger.info(f"=== IN-PROGRESS MATCHES ({len(in_progress_matches)}) ===")
                for i, match in enumerate(in_progress_matches, 1):
                    score_info = match.get_score_string() or "Score unknown"
                    logger.info(
                        f"IN-PROGRESS #{i}: {match.home_team} vs {match.away_team} - {score_info}",
                        extra={
                            "match_id": match.match_id,
                            "date": str(match.match_datetime.date())
                            if match.match_datetime
                            else "Unknown",
                            "time": match.match_datetime.strftime("%I:%M %p")
                            if match.match_datetime
                            else "Unknown",
                            "venue": match.location or "Unknown",
                            "competition": match.competition or "Unknown",
                            "home_score": match.home_score,
                            "away_score": match.away_score,
                        },
                    )

            # Summary statistics
            logger.info(
                "=== MATCH DISCOVERY STATISTICS ===",
                extra={
                    "total_matches": len(matches),
                    "scheduled_matches": len(scheduled_matches),
                    "played_matches": len(played_matches),
                    "tbd_matches": len(tbd_matches),
                    "in_progress_matches": len(in_progress_matches),
                    "matches_with_scores": len([m for m in matches if m.has_score()]),
                    "matches_with_venues": len([m for m in matches if m.location]),
                    "matches_with_times": len([m for m in matches if m.match_datetime]),
                    "unique_teams": len(
                        set(
                            [m.home_team for m in matches]
                            + [m.away_team for m in matches]
                        )
                    ),
                },
            )

        except Exception as e:
            logger.warning(
                "Error logging discovered matches",
                extra={"error": str(e), "error_type": type(e).__name__},
            )

    def _calculate_retry_delay(self, attempt: int) -> float:
        """
        Calculate retry delay with exponential backoff.

        Args:
            attempt: Current attempt number (0-based)

        Returns:
            Delay in seconds
        """
        return self.RETRY_DELAY_BASE * (self.RETRY_BACKOFF_MULTIPLIER**attempt)

    def get_execution_metrics(self) -> ScrapingMetrics:
        """
        Get the current execution metrics.

        Returns:
            ScrapingMetrics object with current metrics
        """
        return self.execution_metrics


# Example usage and testing function
async def example_scraper_usage() -> None:
    """
    Example demonstrating how to use the MLSScraper.

    This example shows the complete workflow for scraping MLS matches
    with configuration and error handling.
    """
    from .config import load_config

    try:
        # Load configuration from environment
        config = load_config()

        # Create and run scraper
        scraper = MLSScraper(config)
        matches = await scraper.scrape_matches()

        print("Scraping completed successfully!")
        print(f"Found {len(matches)} matches:")

        for match in matches[:5]:  # Show first 5 matches
            print(f"  {match.home_team} vs {match.away_team}")
            print(f"    Date: {match.match_datetime}")
            print(f"    Status: {match.match_status}")
            if match.has_score():
                print(f"    Score: {match.get_score_string()}")
            print()

        # Show execution metrics
        metrics = scraper.get_execution_metrics()
        print("Execution Metrics:")
        print(f"  Games Scheduled: {metrics.games_scheduled}")
        print(f"  Games Scored: {metrics.games_scored}")
        print(f"  Duration: {metrics.execution_duration_ms}ms")
        print(f"  Errors: {metrics.errors_encountered}")

    except MLSScraperError as e:
        print(f"Scraper error: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")


if __name__ == "__main__":
    asyncio.run(example_scraper_usage())
