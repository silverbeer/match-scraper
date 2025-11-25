"""
Match data extraction utilities for MLS website scraping.

This module provides functionality to extract match information from the MLS website
results table, including parsing HTML elements, mapping data to Match objects,
and handling different match statuses with comprehensive error handling.
"""

import re
from datetime import datetime
from typing import Any, Optional

from playwright.async_api import Frame, Page

from ..utils.logger import get_logger
from .browser import ElementInteractor
from .models import Match

logger = get_logger()


class MatchExtractionError(Exception):
    """Custom exception for match extraction failures."""

    pass


class MLSMatchExtractor:
    """
    Handles extraction of match data from the MLS website results table.

    Provides methods to parse HTML elements, extract match information,
    and convert data to Match objects with validation and error handling.
    """

    # CSS selectors for MLS website match elements (iframe-based Bootstrap grid)
    IFRAME_SELECTOR = 'main[role="main"] iframe, [aria-label*="main"] iframe, iframe[src*="modular11"]'

    # Try multiple container selectors - the exact class names may vary
    MATCHES_CONTAINER_SELECTORS = [
        ".container-fluid.container-table-matches",  # Original from user HTML
        ".container-fluid",  # Broader search
        "[class*='container-table']",  # Any class containing 'container-table'
        "[class*='container-matches']",  # Any class containing 'container-matches'
        ".container-row",  # Look for the row container directly
    ]

    # Try multiple row selectors
    MATCH_ROW_SELECTORS = [
        ".container-row .row.table-content-row.hidden-xs",  # Original from user HTML
        ".row.table-content-row.hidden-xs",  # Without container-row wrapper
        ".table-content-row.hidden-xs",  # Without row class
        ".table-content-row",  # Without hidden-xs
        "[class*='table-content-row']",  # Any class containing table-content-row
    ]

    # Bootstrap grid column selectors for match data
    MATCH_COLUMN_SELECTORS = {
        "match_id": ".col-sm-1.pad-0:first-child",  # First column: Match ID + Gender
        "details": ".col-sm-2:nth-child(2)",  # Second column: Date/Time + Venue
        "age": ".col-sm-1.pad-0:nth-child(3)",  # Third column: Age
        "competition": ".col-sm-2:nth-child(4)",  # Fourth column: Competition + Division
        "teams": ".col-sm-6.pad-0 .container-teams-info",  # Fifth column: Teams + Score
    }

    # Team and score selectors within the teams column
    TEAM_SELECTORS = {
        "home_team": ".container-first-team p",
        "score": ".container-score .score-match-table",
        "away_team": ".container-second-team p",
    }

    # Alternative selectors for different page layouts
    MATCH_CARD_SELECTOR = ".match-card, .game-card, .fixture-card"
    NO_RESULTS_SELECTOR = ".no-results, .no-matches, .empty-results"

    # Regex patterns for data extraction
    SCORE_PATTERN = re.compile(r"(\d+)\s*[-–—:]\s*(\d+)")
    TIME_PATTERN = re.compile(r"(\d{1,2}):(\d{2})\s*(AM|PM)", re.IGNORECASE)
    DATE_PATTERNS = [
        re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})"),  # MM/DD/YYYY
        re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})"),  # YYYY-MM-DD
        re.compile(r"(\w+)\s+(\d{1,2}),?\s+(\d{4})"),  # Month DD, YYYY
    ]

    def __init__(self, page: Page, timeout: int = 15000):
        """
        Initialize match extractor.

        Args:
            page: Playwright page instance
            timeout: Default timeout for operations in milliseconds
        """
        self.page = page
        self.timeout = timeout
        self.interactor = ElementInteractor(page, timeout)
        self.iframe_content: Optional[Frame] = None

    async def extract_matches(
        self, age_group: str, division: str, competition: Optional[str] = None
    ) -> list[Match]:
        """
        Extract all matches from all paginated pages.

        This method handles pagination automatically, extracting matches from
        all available pages and returning the complete list.

        Args:
            age_group: Age group for the matches (e.g., "U14")
            division: Division for the matches
            competition: Optional competition name

        Returns:
            List of Match objects extracted from all pages
        """
        try:
            logger.info(
                "Starting paginated match extraction",
                extra={
                    "age_group": age_group,
                    "division": division,
                    "competition": competition,
                },
            )

            # Extract matches from all pages with pagination
            all_matches = await self._extract_all_pages(
                age_group, division, competition
            )

            logger.info(
                "Paginated match extraction completed",
                extra={
                    "total_matches": len(all_matches),
                    "age_group": age_group,
                    "division": division,
                },
            )

            return all_matches

        except Exception as e:
            logger.error(
                "Error in paginated match extraction",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "age_group": age_group,
                    "division": division,
                },
            )
            raise MatchExtractionError(f"Failed to extract matches: {e}") from e

    async def _extract_all_pages(
        self, age_group: str, division: str, competition: Optional[str] = None
    ) -> list[Match]:
        """
        Extract matches from all paginated pages.

        Strategy:
        1. Initialize iframe access
        2. Detect total number of pages by looking for page number buttons
        3. Extract matches from page 1
        4. For each additional page: click Next, wait, extract matches
        5. Return all matches from all pages

        Args:
            age_group: Age group for the matches
            division: Division for the matches
            competition: Optional competition name

        Returns:
            List of all matches from all pages
        """
        all_matches = []

        # CRITICAL: Access iframe content first before pagination detection
        logger.info("Initializing iframe access for pagination detection...")
        if not await self._access_iframe_content():
            logger.warning(
                "Cannot access iframe content - pagination detection will fail"
            )
            # Fall back to single page extraction
            return await self._extract_from_current_page(
                age_group, division, competition
            )

        # Wait for results to load
        logger.info("Waiting for results to load...")
        if not await self._wait_for_results():
            logger.warning(
                "Results not loaded - pagination detection may not work correctly"
            )

        # Now determine how many pages exist
        total_pages = await self._get_total_pages()

        if total_pages == 0:
            logger.warning(
                "Could not determine number of pages, will try single page extraction"
            )
            total_pages = 1

        logger.info(f"Detected {total_pages} page(s) of results")

        # Extract matches from each page
        for current_page in range(1, total_pages + 1):
            logger.info(f"Extracting matches from page {current_page} of {total_pages}")

            # Extract matches from current page
            page_matches = await self._extract_from_current_page(
                age_group, division, competition
            )

            if page_matches:
                all_matches.extend(page_matches)
                logger.info(
                    f"Page {current_page}/{total_pages}: Found {len(page_matches)} matches "
                    f"(total so far: {len(all_matches)})"
                )
            else:
                logger.info(f"Page {current_page}/{total_pages}: No matches found")

            # If there are more pages, navigate to the next one
            if current_page < total_pages:
                logger.info(f"Navigating to page {current_page + 1}")

                if not await self._navigate_to_next_page():
                    logger.warning(
                        f"Failed to navigate to page {current_page + 1}, stopping pagination"
                    )
                    break

                # Wait for new results to load
                import asyncio

                await asyncio.sleep(2)

        logger.info(
            f"Pagination complete: Extracted {len(all_matches)} total matches from {current_page} page(s)"
        )
        return all_matches

    async def _get_total_pages(self) -> int:
        """
        Determine the total number of pages by looking for pagination controls.

        Uses a more reliable approach: checks for "Next" button presence and
        looks for pagination buttons within proper pagination containers.

        Returns:
            Total number of pages, or 1 if cannot determine (default to single page)
        """
        try:
            if not self.iframe_content:
                logger.warning("No iframe content available to detect pages")
                logger.info(
                    "⚠️  WARNING: No iframe content available - cannot detect pagination"
                )
                return 1  # Default to 1 page instead of 0

            logger.info("🔍 Scanning for pagination controls in results...")

            # First, check if pagination exists at all by looking for common pagination containers
            pagination_selectors = [
                ".pagination",
                "nav[aria-label*='pagination']",
                "[class*='pagination']",
                ".pager",
                "[class*='pager']",
            ]

            pagination_container = None
            for selector in pagination_selectors:
                try:
                    container = await self.iframe_content.query_selector(selector)
                    if container:
                        pagination_container = container
                        logger.info(f"  ✓ Found pagination container: {selector}")
                        break
                except Exception:
                    continue

            if not pagination_container:
                # No pagination container found - check for Next button as fallback
                try:
                    next_button = self.iframe_content.get_by_text("Next", exact=True)
                    next_count = await next_button.count()
                    if next_count == 0:
                        logger.info(
                            "📄 No pagination controls found - single page of results"
                        )
                        return 1
                except Exception:
                    logger.info(
                        "📄 No pagination controls found - single page of results"
                    )
                    return 1

            # If we have a pagination container, look for page numbers within it
            max_page = 1

            # Look for page number buttons within the pagination container
            for page_num in range(2, 21):  # Start from 2, we already know page 1 exists
                try:
                    # Use locator within the pagination container only
                    if pagination_container:
                        page_button = pagination_container.get_by_text(
                            str(page_num), exact=True
                        )
                    else:
                        # Fallback: look for Next button and estimate pages
                        break

                    count = await page_button.count()

                    if count > 0:
                        max_page = page_num
                        logger.debug(f"  ✓ Found pagination button for page {page_num}")
                    else:
                        # If we don't find a sequential number, stop checking
                        logger.debug(
                            f"Stopping scan at page {page_num} (no more buttons found)"
                        )
                        break
                except Exception as e:
                    logger.debug(f"Error checking for page {page_num}: {e}")
                    break

            if max_page > 1:
                logger.info(
                    f"📄 PAGINATION DETECTED: {max_page} page(s) of results found"
                )
            else:
                logger.info("📄 Single page of results")

            return max_page

        except Exception as e:
            logger.error(f"Error detecting total pages: {e}")
            logger.info(f"❌ ERROR detecting pages: {e}")
            return 1  # Default to 1 page on error

    async def _extract_from_current_page(
        self, age_group: str, division: str, competition: Optional[str] = None
    ) -> list[Match]:
        """
        Extract all matches from the current page (without pagination handling).

        Args:
            age_group: Age group for the matches (e.g., "U14")
            division: Division for the matches
            competition: Optional competition name

        Returns:
            List of Match objects extracted from the current page
        """
        try:
            logger.debug(
                "Extracting matches from current page",
                extra={
                    "age_group": age_group,
                    "division": division,
                    "competition": competition,
                },
            )

            # Access iframe content first
            if not await self._access_iframe_content():
                logger.warning("Cannot access iframe content")
                return []

            # Wait for results to load
            if not await self._wait_for_results():
                logger.warning("No results found on page")
                return []

            # Check for no results message
            if await self._check_no_results():
                logger.info("No matches found - empty results")
                return []

            # Try table-based extraction first
            matches = await self._extract_from_table(age_group, division, competition)

            # If table extraction fails, try card-based extraction
            if not matches:
                logger.debug(
                    "Table extraction found no matches, trying card-based extraction"
                )
                matches = await self._extract_from_cards(
                    age_group, division, competition
                )
            else:
                logger.debug(f"Table extraction found {len(matches)} matches")

            return matches

        except Exception as e:
            logger.error(
                "Error extracting matches from current page",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "age_group": age_group,
                    "division": division,
                },
            )
            raise MatchExtractionError(f"Failed to extract matches: {e}") from e

    async def _has_next_page(self) -> bool:
        """
        Check if there's a next page available in pagination.

        Returns:
            True if next page exists, False otherwise
        """
        try:
            if not self.iframe_content:
                return False

            # Check if "Next" button exists and is enabled
            next_button = self.iframe_content.get_by_text("Next", exact=True)
            button_count = await next_button.count()

            if button_count == 0:
                logger.debug("Next button not found - no pagination")
                return False

            # Check if the button is disabled
            first_button = next_button.first
            is_disabled = await first_button.evaluate(
                "el => el.classList.contains('disabled') || el.disabled || el.getAttribute('aria-disabled') === 'true'"
            )

            if is_disabled:
                logger.debug("Next button is disabled - last page reached")
                return False

            logger.debug("Next button available - more pages exist")
            return True

        except Exception as e:
            logger.debug(f"Error checking for next page: {e}")
            return False

    async def _navigate_to_next_page(self) -> bool:
        """
        Navigate to the next page of results.

        Returns:
            True if navigation successful, False otherwise
        """
        try:
            if not self.iframe_content:
                logger.warning("No iframe content available for pagination")
                return False

            logger.debug("Clicking Next button to navigate to next page")

            # Click the "Next" button
            next_button = self.iframe_content.get_by_text("Next", exact=True)
            await next_button.first.click()

            logger.debug("Successfully clicked Next button")
            return True

        except Exception as e:
            logger.error(
                f"Failed to navigate to next page: {e}",
                extra={"error": str(e), "error_type": type(e).__name__},
            )
            return False

    async def _access_iframe_content(self) -> bool:
        """
        Access the iframe content where match data is located.

        Returns:
            True if iframe accessed successfully, False otherwise
        """
        try:
            logger.debug("Accessing iframe content")

            # Wait for iframe to be available
            iframe_element = await self.page.wait_for_selector(
                self.IFRAME_SELECTOR, timeout=self.timeout
            )

            if not iframe_element:
                logger.debug("No iframe found")
                return False

            # Get iframe content frame
            self.iframe_content = await iframe_element.content_frame()

            if not self.iframe_content:
                logger.debug("Cannot access iframe content frame")
                return False

            logger.debug("Successfully accessed iframe content")
            return True

        except Exception as e:
            logger.debug("Error accessing iframe content", extra={"error": str(e)})
            return False

    async def _wait_for_results(self) -> bool:
        """
        Wait for results to appear on the page.

        Returns:
            True if results found, False otherwise
        """
        try:
            logger.debug("Waiting for results to appear")

            if not self.iframe_content:
                logger.debug("No iframe content available")
                return False

            # Try multiple selectors for results container within iframe
            result_selectors = self.MATCHES_CONTAINER_SELECTORS + [
                self.MATCH_CARD_SELECTOR,
                ".results-container",
                ".matches-container",
                ".schedule-results",
            ]

            for selector in result_selectors:
                try:
                    element = await self.iframe_content.wait_for_selector(
                        selector, timeout=10000
                    )
                    if element:
                        logger.debug(
                            "Results found in iframe", extra={"selector": selector}
                        )
                        return True
                except Exception:
                    continue

            logger.debug("No results container found in iframe")
            return False

        except Exception as e:
            logger.debug("Error waiting for results", extra={"error": str(e)})
            return False

    async def _check_no_results(self) -> bool:
        """
        Check if iframe shows no results message.

        Returns:
            True if no results message found, False otherwise
        """
        try:
            if not self.iframe_content:
                logger.debug("No iframe content available for no results check")
                return False

            no_results_selectors = [
                self.NO_RESULTS_SELECTOR,
                ".no-results",
                ".no-matches",
                ".empty-results",
                ':has-text("No matches found")',
                ':has-text("No results")',
            ]

            for selector in no_results_selectors:
                try:
                    element = await self.iframe_content.wait_for_selector(
                        selector, timeout=2000
                    )
                    if element:
                        logger.debug(
                            "No results message found in iframe",
                            extra={"selector": selector},
                        )
                        return True
                except Exception:
                    continue

            return False

        except Exception as e:
            logger.debug("Error checking no results", extra={"error": str(e)})
            return False

    async def _extract_from_table(
        self, age_group: str, division: str, competition: Optional[str]
    ) -> list[Match]:
        """
        Extract matches from Bootstrap grid layout.

        Args:
            age_group: Age group for the matches
            division: Division for the matches
            competition: Optional competition name

        Returns:
            List of Match objects
        """
        try:
            logger.debug("Attempting Bootstrap grid extraction from iframe")

            if not self.iframe_content:
                logger.debug("No iframe content available for grid extraction")
                return []

            # Try to find matches container using multiple selectors
            matches_container = None
            container_selector_used = None

            for selector in self.MATCHES_CONTAINER_SELECTORS:
                matches_container = await self.iframe_content.query_selector(selector)
                if matches_container:
                    container_selector_used = selector
                    logger.info("Found matches container", extra={"selector": selector})
                    break

            if not matches_container:
                logger.debug(
                    "No matches container found with any selector",
                    extra={"selectors": self.MATCHES_CONTAINER_SELECTORS},
                )
                return []

            # Try to find match rows using multiple selectors
            match_rows = None
            row_selector_used = None

            for selector in self.MATCH_ROW_SELECTORS:
                match_rows = await matches_container.query_selector_all(selector)
                if match_rows:
                    row_selector_used = selector
                    logger.info(
                        "Found match rows",
                        extra={"selector": selector, "count": len(match_rows)},
                    )
                    break

            if not match_rows:
                logger.debug(
                    "No match rows found with any selector",
                    extra={"selectors": self.MATCH_ROW_SELECTORS},
                )

                # If we can't find rows with our selectors, try to find ANY divs that might be matches
                fallback_selectors = [
                    "div[class*='row']",
                    "div[class*='match']",
                    "div[class*='game']",
                    ".row",
                    "tr",  # In case it's still a table
                ]

                for selector in fallback_selectors:
                    fallback_rows = await matches_container.query_selector_all(selector)
                    if fallback_rows:
                        logger.info(
                            "Found fallback rows",
                            extra={"selector": selector, "count": len(fallback_rows)},
                        )
                        # Use first few for testing
                        match_rows = fallback_rows[
                            :10
                        ]  # Limit to first 10 for performance
                        row_selector_used = selector + " (fallback)"
                        break

                if not match_rows:
                    return []

            logger.info(
                "Using container selector: %s, row selector: %s",
                container_selector_used,
                row_selector_used,
            )

            # Extract matches from rows
            matches = []
            for i, row in enumerate(match_rows):
                try:
                    match = await self._extract_match_from_row(
                        row, i, age_group, division, competition
                    )
                    if match:
                        matches.append(match)
                except Exception as e:
                    logger.warning(
                        "Failed to extract match from row",
                        extra={"row_index": i, "error": str(e)},
                    )
                    continue

            logger.debug("Grid extraction completed", extra={"matches": len(matches)})
            return matches

        except Exception as e:
            logger.debug("Error in grid extraction", extra={"error": str(e)})
            return []

    async def _extract_from_cards(
        self, age_group: str, division: str, competition: Optional[str]
    ) -> list[Match]:
        """
        Extract matches from card-based layout.

        Args:
            age_group: Age group for the matches
            division: Division for the matches
            competition: Optional competition name

        Returns:
            List of Match objects
        """
        try:
            logger.debug("Attempting card-based extraction")

            # Find match cards
            card_selectors = [
                self.MATCH_CARD_SELECTOR,
                ".match-card",
                ".game-card",
                ".fixture-card",
                ".match-item",
            ]

            match_cards = []
            for selector in card_selectors:
                cards = await self.page.query_selector_all(selector)
                if cards:
                    match_cards = cards
                    logger.debug(
                        "Found match cards",
                        extra={"count": len(cards), "selector": selector},
                    )
                    break

            if not match_cards:
                logger.debug("No match cards found")
                return []

            # Extract matches from cards
            matches = []
            for i, card in enumerate(match_cards):
                try:
                    match = await self._extract_match_from_card(
                        card, i, age_group, division, competition
                    )
                    if match:
                        matches.append(match)
                except Exception as e:
                    logger.warning(
                        "Failed to extract match from card",
                        extra={"card_index": i, "error": str(e)},
                    )
                    continue

            logger.debug("Card extraction completed", extra={"matches": len(matches)})
            return matches

        except Exception as e:
            logger.debug("Error in card extraction", extra={"error": str(e)})
            return []

    async def _extract_match_from_row(
        self,
        row_element: Any,
        row_index: int,
        age_group: str,
        division: str,
        competition: Optional[str],
    ) -> Optional[Match]:
        """
        Extract match data from a Bootstrap grid row element.

        Args:
            row_element: Playwright element for the grid row
            row_index: Index of the row for ID generation
            age_group: Age group for the match
            division: Division for the match
            competition: Optional competition name

        Returns:
            Match object or None if extraction fails
        """
        try:
            logger.info(
                "Extracting match from grid row", extra={"row_index": row_index}
            )

            # Extract data from Bootstrap grid columns
            match_data = {}

            # Extract match ID and gender from first column
            match_id_col = await row_element.query_selector(
                self.MATCH_COLUMN_SELECTORS["match_id"]
            )
            if match_id_col:
                match_id_text = await match_id_col.text_content()
                if match_id_text:
                    match_data["match_id_raw"] = match_id_text.strip()
                    logger.info(
                        "Extracted match ID",
                        extra={
                            "row_index": row_index,
                            "match_id": match_data["match_id_raw"],
                        },
                    )

            # Extract date/time and venue from second column
            details_col = await row_element.query_selector(
                self.MATCH_COLUMN_SELECTORS["details"]
            )
            if details_col:
                details_text = await details_col.text_content()
                if details_text:
                    logger.info(
                        "Raw details text",
                        extra={
                            "row_index": row_index,
                            "details_text": repr(details_text),
                        },
                    )

                    # Parse date, time, and venue from the details column
                    details_parts = details_text.strip().split("\n")
                    logger.info(
                        "Details parts",
                        extra={"row_index": row_index, "parts": details_parts},
                    )

                    for i, part in enumerate(details_parts):
                        part = part.strip()
                        if not part:
                            continue
                        logger.info(
                            "Processing details part",
                            extra={
                                "row_index": row_index,
                                "part_index": i,
                                "part": repr(part),
                            },
                        )

                        # Look for date patterns
                        date_found = False
                        for pattern in self.DATE_PATTERNS:
                            if pattern.search(part):
                                match_data["date"] = part
                                logger.info(
                                    "Found date",
                                    extra={"row_index": row_index, "date": part},
                                )
                                date_found = True
                                break

                        # Look for time patterns (including combined date/time)
                        if not date_found and self.TIME_PATTERN.search(part):
                            match_data["time"] = part
                            logger.info(
                                "Found time",
                                extra={"row_index": row_index, "time": part},
                            )
                        # Check if this might be venue (everything else that's not date/time and not empty)
                        elif (
                            not date_found
                            and not self.TIME_PATTERN.search(part)
                            and len(part) > 3
                        ):
                            match_data["venue"] = part
                            logger.info(
                                "Found venue",
                                extra={"row_index": row_index, "venue": part},
                            )

            # Extract age from third column
            age_col = await row_element.query_selector(
                self.MATCH_COLUMN_SELECTORS["age"]
            )
            if age_col:
                age_text = await age_col.text_content()
                if age_text:
                    match_data["age_raw"] = age_text.strip()

            # Extract competition and division from fourth column
            competition_col = await row_element.query_selector(
                self.MATCH_COLUMN_SELECTORS["competition"]
            )
            if competition_col:
                comp_text = await competition_col.text_content()
                if comp_text:
                    match_data["competition_raw"] = comp_text.strip()
                    logger.info(
                        "Found competition",
                        extra={
                            "row_index": row_index,
                            "competition": comp_text.strip(),
                        },
                    )

            # Extract teams and score from fifth column
            teams_col = await row_element.query_selector(
                self.MATCH_COLUMN_SELECTORS["teams"]
            )
            if teams_col:
                logger.info("Found teams column", extra={"row_index": row_index})

                # Extract home team
                home_team_elem = await teams_col.query_selector(
                    self.TEAM_SELECTORS["home_team"]
                )
                if home_team_elem:
                    home_team_text = await home_team_elem.text_content()
                    if home_team_text:
                        match_data["home_team"] = home_team_text.strip()
                        logger.info(
                            "Extracted home team",
                            extra={
                                "row_index": row_index,
                                "home_team": match_data["home_team"],
                            },
                        )

                # Extract away team
                away_team_elem = await teams_col.query_selector(
                    self.TEAM_SELECTORS["away_team"]
                )
                if away_team_elem:
                    away_team_text = await away_team_elem.text_content()
                    if away_team_text:
                        match_data["away_team"] = away_team_text.strip()
                        logger.info(
                            "Extracted away team",
                            extra={
                                "row_index": row_index,
                                "away_team": match_data["away_team"],
                            },
                        )

                # Extract score
                score_elem = await teams_col.query_selector(
                    self.TEAM_SELECTORS["score"]
                )
                if score_elem:
                    score_text = await score_elem.text_content()
                    if score_text:
                        match_data["score"] = score_text.strip()
                        logger.info(
                            "Extracted score",
                            extra={
                                "row_index": row_index,
                                "score": match_data["score"],
                            },
                        )
            else:
                logger.info(
                    "Teams column not found",
                    extra={
                        "row_index": row_index,
                        "selector": self.MATCH_COLUMN_SELECTORS["teams"],
                    },
                )

            # Fallback: if specific selectors fail, try to parse row text
            if not match_data.get("home_team") or not match_data.get("away_team"):
                row_text = await row_element.text_content()
                if row_text:
                    fallback_data = self._parse_row_text(row_text.strip())
                    match_data.update(fallback_data)

            if not match_data:
                logger.info(
                    "No data extracted from grid row", extra={"row_index": row_index}
                )
                return None

            logger.info(
                "Row extraction summary",
                extra={
                    "row_index": row_index,
                    "extracted_fields": list(match_data.keys()),
                    "has_teams": bool(
                        match_data.get("home_team") and match_data.get("away_team")
                    ),
                },
            )

            # Convert to Match object
            match = await self._create_match_from_data(
                match_data, row_index, age_group, division, competition
            )

            if match:
                logger.info(
                    "Successfully created match object",
                    extra={
                        "row_index": row_index,
                        "match_id": match.match_id,
                        "home_team": match.home_team,
                        "away_team": match.away_team,
                    },
                )
            else:
                logger.info(
                    "Failed to create match object",
                    extra={"row_index": row_index, "data": match_data},
                )

            return match

        except Exception as e:
            logger.debug(
                "Error extracting match from grid row",
                extra={"row_index": row_index, "error": str(e)},
            )
            return None

    async def _extract_match_from_card(
        self,
        card_element: Any,
        card_index: int,
        age_group: str,
        division: str,
        competition: Optional[str],
    ) -> Optional[Match]:
        """
        Extract match data from a card element.

        Args:
            card_element: Playwright element for the match card
            card_index: Index of the card for ID generation
            age_group: Age group for the match
            division: Division for the match
            competition: Optional competition name

        Returns:
            Match object or None if extraction fails
        """
        try:
            logger.debug("Extracting match from card", extra={"card_index": card_index})

            # Extract data from card elements
            match_data = {}

            # Common card selectors
            card_selectors = {
                "date": [".date", ".match-date", ".game-date"],
                "time": [".time", ".match-time", ".game-time"],
                "home_team": [".home-team", ".home", ".team-home"],
                "away_team": [".away-team", ".away", ".team-away"],
                "score": [".score", ".result", ".final-score"],
                "venue": [".venue", ".location", ".stadium"],
                "status": [".status", ".match-status", ".game-status"],
            }

            for field, selectors in card_selectors.items():
                for selector in selectors:
                    element = await card_element.query_selector(selector)
                    if element:
                        text = await element.text_content()
                        if text and text.strip():
                            match_data[field] = text.strip()
                            break

            # If specific selectors fail, try to parse card text
            if not match_data:
                card_text = await card_element.text_content()
                if card_text:
                    match_data = self._parse_card_text(card_text.strip())

            if not match_data:
                logger.debug("No data extracted from card")
                return None

            # Convert to Match object
            match = await self._create_match_from_data(
                match_data, card_index, age_group, division, competition
            )

            logger.debug(
                "Successfully extracted match from card",
                extra={"match_id": match.match_id if match else None},
            )
            return match

        except Exception as e:
            logger.debug(
                "Error extracting match from card",
                extra={"card_index": card_index, "error": str(e)},
            )
            return None

    async def _extract_from_cell_positions(self, cells: Any) -> dict:
        """
        Extract match data based on cell positions.

        Args:
            cells: List of cell elements

        Returns:
            Dictionary of extracted data
        """
        try:
            data = {}

            # Common cell position mappings
            if len(cells) >= 5:
                # Typical layout: Date, Time, Home, Away, Score
                data["date"] = await cells[0].text_content()
                data["time"] = await cells[1].text_content()
                data["home_team"] = await cells[2].text_content()
                data["away_team"] = await cells[3].text_content()
                data["score"] = await cells[4].text_content()

                if len(cells) >= 6:
                    data["venue"] = await cells[5].text_content()
                if len(cells) >= 7:
                    data["status"] = await cells[6].text_content()

            elif len(cells) >= 3:
                # Minimal layout: Home, Away, Score/Status
                data["home_team"] = await cells[0].text_content()
                data["away_team"] = await cells[1].text_content()
                data["score"] = await cells[2].text_content()

            # Clean up the data
            return {k: v.strip() for k, v in data.items() if v and v.strip()}

        except Exception as e:
            logger.debug(
                "Error extracting from cell positions", extra={"error": str(e)}
            )
            return {}

    def _parse_row_text(self, text: str) -> dict:
        """
        Parse match data from row text content.

        Args:
            text: Raw text content from the row

        Returns:
            Dictionary of parsed data
        """
        try:
            data = {}

            # Split text into parts
            parts = [part.strip() for part in text.split() if part.strip()]

            if len(parts) < 3:
                return {}

            # Look for date patterns
            for _i, part in enumerate(parts):
                for pattern in self.DATE_PATTERNS:
                    if pattern.search(part):
                        data["date"] = part
                        break

            # Look for time patterns
            for part in parts:
                if self.TIME_PATTERN.search(part):
                    data["time"] = part
                    break

            # Look for score patterns
            for part in parts:
                if self.SCORE_PATTERN.search(part):
                    data["score"] = part
                    break

            # Try to identify teams (usually the longest text parts)
            text_parts = [
                p for p in parts if len(p) > 3 and not any(c.isdigit() for c in p)
            ]
            if len(text_parts) >= 2:
                data["home_team"] = text_parts[0]
                data["away_team"] = text_parts[1]

            return data

        except Exception as e:
            logger.debug("Error parsing row text", extra={"error": str(e)})
            return {}

    def _parse_card_text(self, text: str) -> dict:
        """
        Parse match data from card text content.

        Args:
            text: Raw text content from the card

        Returns:
            Dictionary of parsed data
        """
        # Similar to _parse_row_text but adapted for card layout
        return self._parse_row_text(text)

    async def _create_match_from_data(
        self,
        data: dict,
        index: int,
        age_group: str,
        division: str,
        competition: Optional[str],
    ) -> Optional[Match]:
        """
        Create Match object from extracted data.

        Args:
            data: Dictionary of extracted match data
            index: Index for ID generation
            age_group: Age group for the match
            division: Division for the match
            competition: Optional competition name

        Returns:
            Match object or None if creation fails
        """
        try:
            # Extract actual match ID from raw data
            match_id_raw = data.get("match_id_raw", "")
            if match_id_raw:
                # Extract numeric match ID from raw text (format: "99963\t\t\t\n\t\t\tMALE")
                import re

                match_id_match = re.search(r"(\d+)", match_id_raw.strip())
                if match_id_match:
                    match_id = match_id_match.group(1)
                else:
                    # Fallback to generated ID if extraction fails
                    match_id = f"{age_group}_{division}_{index}_{datetime.now().strftime('%Y%m%d')}"
            else:
                # Generate fallback match ID if no raw ID available
                match_id = f"{age_group}_{division}_{index}_{datetime.now().strftime('%Y%m%d')}"

            # Parse date and time
            # Handle combined date/time format like "09/20/25 03:45pm"
            time_str = data.get("time", "")
            date_str = data.get("date", "")

            if time_str and not date_str:
                # Combined format: split date and time
                parts = time_str.split(" ", 1)
                if len(parts) == 2:
                    date_str = parts[0]
                    time_part = parts[1]
                else:
                    date_str = time_str
                    time_part = ""
            else:
                time_part = time_str

            match_date = self._parse_match_datetime(date_str, time_part)
            if not match_date:
                logger.info(
                    "Could not parse match date/time",
                    extra={
                        "time_str": time_str,
                        "date_str": date_str,
                        "time_part": time_part,
                        "data": data,
                    },
                )
                return None

            logger.info(
                "Successfully parsed match date/time",
                extra={
                    "match_date": match_date.isoformat(),
                    "date_str": date_str,
                    "time_part": time_part,
                },
            )

            # Extract team names
            home_team = data.get("home_team", "").strip()
            away_team = data.get("away_team", "").strip()

            if not home_team or not away_team:
                logger.info(
                    "Missing team names", extra={"home": home_team, "away": away_team}
                )
                return None

            # Clean up competition data
            competition_raw = data.get("competition_raw", "").strip()
            if competition_raw:
                # Clean up whitespace and tabs/newlines
                competition_clean = " ".join(competition_raw.split())
                logger.info(
                    "Cleaned competition",
                    extra={"raw": repr(competition_raw), "clean": competition_clean},
                )
                competition = competition_clean
            else:
                competition = competition or "Unknown"

            # Parse score and determine status
            score_text = data.get("score", "").strip()
            status_text = data.get("status", "").strip().lower()

            home_score, away_score, status = self._parse_score_and_status(
                score_text, status_text, match_date
            )

            logger.info(
                "About to create Match object",
                extra={
                    "match_id": match_id,
                    "home_team": home_team,
                    "away_team": away_team,
                    "match_date": match_date.isoformat(),
                    "status": status,
                    "home_score": home_score,
                    "away_score": away_score,
                },
            )

            # Create Match object using new model structure
            match = Match(
                match_id=match_id,
                match_datetime=match_date,
                location=data.get("venue"),
                competition=competition,
                home_team=home_team,
                away_team=away_team,
                home_score=home_score,
                away_score=away_score,
            )

            logger.info(
                "Successfully created match object",
                extra={"match_id": match_id, "status": match.match_status},
            )
            return match

        except Exception as e:
            logger.info(
                "Error creating match from data",
                extra={"error": str(e), "data": data},
            )
            return None

    def _parse_match_datetime(self, date_str: str, time_str: str) -> Optional[datetime]:
        """
        Parse match date and time strings into datetime object.

        Args:
            date_str: Date string
            time_str: Time string

        Returns:
            datetime object or None if parsing fails
        """
        try:
            if not date_str:
                return None

            # Try different date formats
            parsed_date = None

            # MM/DD/YY (2-digit year)
            match = re.match(r"(\d{1,2})/(\d{1,2})/(\d{2})$", date_str)
            if match:
                month, day, year = map(int, match.groups())
                # Convert 2-digit year to 4-digit (assuming 2000s)
                if year < 50:  # 00-49 = 2000-2049
                    year += 2000
                else:  # 50-99 = 1950-1999
                    year += 1900
                parsed_date = datetime(year, month, day)

            # MM/DD/YYYY (4-digit year)
            if not parsed_date:
                match = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", date_str)
                if match:
                    month, day, year = map(int, match.groups())
                    parsed_date = datetime(year, month, day)

            # YYYY-MM-DD
            if not parsed_date:
                match = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", date_str)
                if match:
                    year, month, day = map(int, match.groups())
                    parsed_date = datetime(year, month, day)

            # Month DD, YYYY
            if not parsed_date:
                match = re.match(r"(\w+)\s+(\d{1,2}),?\s+(\d{4})", date_str)
                if match:
                    month_name, day_str, year_str = match.groups()
                    day = int(day_str)
                    year = int(year_str)
                    month_map = {
                        "january": 1,
                        "jan": 1,
                        "february": 2,
                        "feb": 2,
                        "march": 3,
                        "mar": 3,
                        "april": 4,
                        "apr": 4,
                        "may": 5,
                        "june": 6,
                        "jun": 6,
                        "july": 7,
                        "jul": 7,
                        "august": 8,
                        "aug": 8,
                        "september": 9,
                        "sep": 9,
                        "october": 10,
                        "oct": 10,
                        "november": 11,
                        "nov": 11,
                        "december": 12,
                        "dec": 12,
                    }
                    month_from_map: Optional[int] = month_map.get(month_name.lower())
                    if month_from_map:
                        month = month_from_map
                        parsed_date = datetime(int(year), month, int(day))

            if not parsed_date:
                logger.debug("Could not parse date", extra={"date_str": date_str})
                return None

            # Add time if provided
            if time_str:
                time_match = self.TIME_PATTERN.search(time_str)
                if time_match:
                    hour, minute, ampm = time_match.groups()
                    hour = int(hour)
                    minute = int(minute)

                    if ampm.upper() == "PM" and hour != 12:
                        hour += 12
                    elif ampm.upper() == "AM" and hour == 12:
                        hour = 0

                    parsed_date = parsed_date.replace(hour=hour, minute=minute)

            return parsed_date

        except Exception as e:
            logger.debug(
                "Error parsing datetime",
                extra={"error": str(e), "date_str": date_str, "time_str": time_str},
            )
            return None

    def _parse_score_and_status(
        self, score_text: str, status_text: str, match_date: Optional[datetime] = None
    ) -> tuple[Optional[int], Optional[int], str]:
        """
        Parse score and status information.

        Args:
            score_text: Score text from the page
            status_text: Status text from the page
            match_date: Date of the match (used to determine if TBD games are past or future)

        Returns:
            Tuple of (home_score, away_score, status)
        """
        try:
            home_score: Optional[str | int] = None
            away_score: Optional[str | int] = None
            status = "scheduled"

            # Check for explicit status indicators
            if any(word in status_text for word in ["completed", "final", "finished"]):
                status = "completed"
            elif any(
                word in status_text for word in ["live", "playing", "in progress"]
            ):
                status = "in_progress"
            elif any(word in status_text for word in ["scheduled", "upcoming"]):
                status = "scheduled"

            # Try to parse score
            if score_text:
                # Clean the score text (remove non-breaking spaces and normalize)
                cleaned_score = score_text.replace("\xa0", " ").strip()

                # Check if it's TBD/not yet played
                if cleaned_score.upper() in [
                    "TBD",
                    "VS",
                    "V",
                    "@",
                    "NOT STARTED",
                    "PENDING",
                ]:
                    # Return TBD for scores - the model will calculate the status automatically
                    home_score = "TBD"
                    away_score = "TBD"
                else:
                    # Try to parse actual scores
                    score_match = self.SCORE_PATTERN.search(cleaned_score)
                    if score_match:
                        home_score_val = int(score_match.group(1))
                        away_score_val = int(score_match.group(2))

                        # All numeric scores (including 0-0 draws) are real scores
                        # The MLS website shows actual scores, not placeholders
                        home_score = home_score_val
                        away_score = away_score_val
                        logger.info(
                            "Parsed score",
                            extra={
                                "match_date": match_date.isoformat()
                                if match_date
                                else None,
                                "original_score": cleaned_score,
                                "parsed_score": f"{home_score_val}-{away_score_val}",
                                "status_text": status_text,
                            },
                        )

            return home_score, away_score, status

        except Exception as e:
            logger.debug(
                "Error parsing score and status",
                extra={
                    "error": str(e),
                    "score_text": score_text,
                    "status_text": status_text,
                },
            )
            return None, None, "scheduled"


# Example usage
async def example_match_extraction() -> None:
    """
    Example demonstrating how to use the MLSMatchExtractor.

    This example shows the complete workflow for extracting match data
    from the MLS website after applying filters.
    """
    from .browser import PageNavigator, get_browser_manager

    # Use browser manager to create a page
    async with get_browser_manager() as browser_manager:
        async with browser_manager.get_page() as page:
            # Navigate to MLS website
            navigator = PageNavigator(page)
            success = await navigator.navigate_to(
                "https://www.mlssoccer.com/mlsnext/schedule/all/"
            )

            if not success:
                print("Failed to navigate to MLS website")
                return

            # Create match extractor
            extractor = MLSMatchExtractor(page)

            try:
                # Extract matches (assuming filters have been applied)
                matches = await extractor.extract_matches(
                    age_group="U14", division="Northeast", competition="MLS Next"
                )

                print(f"Extracted {len(matches)} matches:")
                for match in matches:
                    print(
                        f"  {match.home_team} vs {match.away_team} - {match.match_status}"
                    )
                    if match.has_score():
                        print(f"    Score: {match.get_score_string()}")

            except MatchExtractionError as e:
                print(f"Match extraction failed: {e}")
            except Exception as e:
                print(f"Unexpected error: {e}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(example_match_extraction())
