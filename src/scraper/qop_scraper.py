"""
MLS Next QoP (Quality of Play) standings scraper.

This module provides the MLSQoPScraper class that navigates to the MLS Next
standings page, selects the appropriate division filter, and extracts team
rankings from the standings table.
"""

import asyncio
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from ..models.qop_ranking import QoPRanking, QoPSnapshot
from ..utils.logger import get_logger
from .browser import BrowserConfig, BrowserManager, PageNavigator
from .consent_handler import MLSConsentHandler

logger = get_logger()


class QoPScraperError(Exception):
    """Custom exception for QoP scraper failures."""

    pass


# Qualification status substrings that appear inline with team names on the page
_QUALIFICATION_PATTERNS = re.compile(
    r"(Championship Qualification|Premier Qualification|Qualification|Qualified)",
    re.IGNORECASE,
)


def strip_qualification_text(raw: str) -> str:
    """
    Remove qualification status text from a raw team name string.

    MLS Next standings pages render qualification labels (e.g. "Championship
    Qualification", "Premier Qualification") as inline text adjacent to the
    team name.  This function strips those substrings so only the club name
    remains.

    Args:
        raw: Raw text extracted from the standings table team cell.

    Returns:
        Cleaned team name with leading/trailing whitespace removed.
    """
    cleaned = _QUALIFICATION_PATTERNS.sub("", raw)
    # Collapse multiple internal spaces that may be left behind
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()


class MLSQoPScraper:
    """
    Scrapes MLS Next Quality-of-Play standings for a given age group and division.

    Usage::

        scraper = MLSQoPScraper(age_group="U14", division="Northeast")
        snapshot = await scraper.scrape()
    """

    # URL template: age_group "U14" → "u14"
    MLS_STANDINGS_URL_TEMPLATE = (
        "https://www.mlssoccer.com/mlsnext/standings/{age_slug}/"
    )

    # Retry configuration (mirrors MLSScraper)
    MAX_RETRIES = 3
    RETRY_DELAY_BASE = 1.0
    RETRY_BACKOFF_MULTIPLIER = 2.0

    # Selector timeout (ms)
    DEFAULT_TIMEOUT = 10_000

    def __init__(
        self,
        age_group: str,
        division: str,
        headless: bool = True,
    ) -> None:
        """
        Initialize the QoP scraper.

        Args:
            age_group: Age group to scrape, e.g. "U14".
            division:  Division label to select, e.g. "Northeast".
                       Matched case-insensitively against options shown on the page.
            headless:  Whether to run the browser in headless mode.
        """
        self.age_group = age_group
        self.division = division
        self.headless = headless
        self.browser_manager: Optional[BrowserManager] = None

        age_slug = age_group.lower()
        self.standings_url = self.MLS_STANDINGS_URL_TEMPLATE.format(age_slug=age_slug)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def scrape(self) -> QoPSnapshot:
        """
        Navigate to the standings page, select the division filter, and extract
        all team rankings.

        Returns:
            QoPSnapshot populated with the current standings data.

        Raises:
            QoPScraperError: If the scrape fails after all retries.
        """
        logger.info(
            "Starting QoP standings scrape",
            extra={
                "age_group": self.age_group,
                "division": self.division,
                "url": self.standings_url,
            },
        )

        last_exc: Optional[Exception] = None

        for attempt in range(self.MAX_RETRIES):
            try:
                snapshot = await self._scrape_attempt()
                logger.info(
                    "QoP standings scrape completed",
                    extra={
                        "age_group": self.age_group,
                        "division": self.division,
                        "rankings_count": len(snapshot.rankings),
                        "attempt": attempt + 1,
                    },
                )
                return snapshot

            except QoPScraperError:
                # Non-retryable logical errors (e.g. division not found) — re-raise immediately
                raise

            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "QoP scrape attempt failed",
                    extra={
                        "attempt": attempt + 1,
                        "max_retries": self.MAX_RETRIES,
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                    },
                )

                if attempt < self.MAX_RETRIES - 1:
                    delay = self._retry_delay(attempt)
                    logger.info(
                        "Retrying QoP scrape",
                        extra={"delay_seconds": delay, "next_attempt": attempt + 2},
                    )
                    await asyncio.sleep(delay)

            finally:
                # Clean up browser between retries
                if self.browser_manager:
                    await self.browser_manager.cleanup()
                    self.browser_manager = None

        raise QoPScraperError(
            f"QoP scrape failed after {self.MAX_RETRIES} attempts: {last_exc}"
        ) from last_exc

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _scrape_attempt(self) -> QoPSnapshot:
        """Execute a single scrape attempt (browser init → navigate → extract)."""
        # Initialise browser
        browser_config = BrowserConfig(
            headless=self.headless,
            timeout=30_000,
            viewport_width=1280,
            viewport_height=720,
        )
        self.browser_manager = BrowserManager(browser_config)
        await self.browser_manager.initialize()

        async with self.browser_manager.get_page() as page:
            await self._navigate(page)
            await self._select_division(page)
            rankings = await self._extract_rankings(page)

        today = date.today()
        week_of = today - timedelta(days=today.weekday())

        return QoPSnapshot(
            week_of=week_of,
            division=self.division,
            age_group=self.age_group,
            scraped_at=datetime.now(tz=timezone.utc),
            rankings=rankings,
        )

    async def _navigate(self, page: Any) -> None:
        """Navigate to the standings URL and handle consent banners."""
        logger.info("Navigating to standings page", extra={"url": self.standings_url})

        navigator = PageNavigator(page, max_retries=self.MAX_RETRIES)
        success = await navigator.navigate_to(self.standings_url, wait_until="load")
        if not success:
            raise QoPScraperError(
                f"Failed to navigate to standings page: {self.standings_url}"
            )

        logger.info("Navigation successful — handling consent banner")
        consent_handler = MLSConsentHandler(page)
        consent_handled = await consent_handler.handle_consent_banner()
        if not consent_handled:
            logger.warning("Consent handling failed; continuing anyway")

        page_ready = await consent_handler.wait_for_page_ready()
        if not page_ready:
            logger.warning("Page readiness check failed; continuing anyway")

    async def _select_division(self, page: Any) -> None:
        """
        Find the division filter control on the page and select the target division.

        The MLS Next standings page may expose the division filter as:
          - A native <select> element
          - A button-based dropdown (div/ul with clickable items)

        We try the native select first, then fall back to button-based interaction.
        """
        target = self.division.lower()
        logger.info("Selecting division filter", extra={"division": self.division})

        # --- Strategy 1: native <select> element ---
        selected = await self._try_select_element(page, target)
        if selected:
            logger.info("Division selected via <select> element")
            await page.wait_for_timeout(1500)
            return

        # --- Strategy 2: clickable filter buttons / links ---
        selected = await self._try_button_filter(page, target)
        if selected:
            logger.info("Division selected via button/link filter")
            await page.wait_for_timeout(1500)
            return

        raise QoPScraperError(
            f"Division filter not found for '{self.division}'. "
            "The page structure may have changed or the division name is incorrect."
        )

    async def _try_select_element(self, page: Any, target_lower: str) -> bool:
        """
        Attempt to select the division using a native <select> dropdown.

        Returns True if the division was successfully selected.
        """
        # Common selector patterns for MLS Next filter dropdowns
        select_selectors = [
            "select[name*='division']",
            "select[id*='division']",
            "select[class*='division']",
            "select[name*='group']",
            "select[id*='group']",
            "select",  # broad fallback — iterate all selects
        ]

        for sel in select_selectors:
            try:
                select_elements = await page.query_selector_all(sel)
                for select_el in select_elements:
                    options = await select_el.query_selector_all("option")
                    for option in options:
                        text = await option.text_content() or ""
                        if target_lower in text.lower():
                            value = await option.get_attribute("value") or text.strip()
                            await select_el.select_option(value=value)
                            return True
            except Exception as exc:
                logger.debug(
                    "select_element attempt failed",
                    extra={"selector": sel, "error": str(exc)},
                )

        return False

    async def _try_button_filter(self, page: Any, target_lower: str) -> bool:
        """
        Attempt to select the division by clicking a button or link that contains
        the division name.

        Returns True if the division was successfully selected.
        """
        # Selectors for MLS Next filter pill/button patterns
        button_selectors = [
            f"button:has-text('{self.division}')",
            f"a:has-text('{self.division}')",
            f"[data-value*='{self.division}']",
            f"[data-filter*='{self.division}']",
        ]

        for sel in button_selectors:
            try:
                el = await page.query_selector(sel)
                if el:
                    await el.click()
                    return True
            except Exception:
                pass

        # Broader search: find any clickable element whose visible text contains
        # the division name (case-insensitive)
        try:
            candidates = await page.query_selector_all(
                "button, a, [role='option'], [role='button'], li"
            )
            for el in candidates:
                text = await el.text_content() or ""
                if target_lower in text.lower() and "division" in text.lower():
                    await el.click()
                    return True
        except Exception as exc:
            logger.debug("Broad button filter search failed", extra={"error": str(exc)})

        return False

    async def _extract_rankings(self, page: Any) -> list[QoPRanking]:
        """
        Wait for the standings table and extract all rows.

        Returns:
            List of QoPRanking objects ordered by rank.
        """
        logger.info("Waiting for standings table")

        # Try multiple table selectors
        table_selectors = [
            "table tbody tr",
            "tbody tr",
            "[class*='standings'] tr",
            "[class*='table'] tr",
            "tr",
        ]

        rows = []
        for sel in table_selectors:
            try:
                await page.wait_for_selector(sel, timeout=self.DEFAULT_TIMEOUT)
                rows = await page.query_selector_all(sel)
                if rows:
                    logger.info(
                        "Found standings rows",
                        extra={"selector": sel, "row_count": len(rows)},
                    )
                    break
            except Exception:
                continue

        if not rows:
            raise QoPScraperError(
                "Could not locate standings table rows on the page. "
                "The page structure may have changed."
            )

        rankings: list[QoPRanking] = []
        skipped = 0

        for row in rows:
            cells = await row.query_selector_all("td")
            if len(cells) < 6:
                # Skip header rows or malformed rows
                skipped += 1
                continue

            try:
                rank_text = (await cells[0].text_content() or "").strip()
                team_raw = (await cells[1].text_content() or "").strip()
                mp_text = (await cells[2].text_content() or "").strip()
                att_text = (await cells[3].text_content() or "").strip()
                def_text = (await cells[4].text_content() or "").strip()
                qop_text = (await cells[5].text_content() or "").strip()

                rank = int(rank_text)
                team_name = strip_qualification_text(team_raw)
                matches_played = int(mp_text)
                att_score = float(att_text)
                def_score = float(def_text)
                qop_score = float(qop_text)

                rankings.append(
                    QoPRanking(
                        rank=rank,
                        team_name=team_name,
                        matches_played=matches_played,
                        att_score=att_score,
                        def_score=def_score,
                        qop_score=qop_score,
                    )
                )

            except (ValueError, IndexError) as exc:
                skipped += 1
                logger.debug(
                    "Skipping unparseable standings row",
                    extra={"error": str(exc)},
                )

        logger.info(
            "Standings extraction complete",
            extra={"parsed_rows": len(rankings), "skipped_rows": skipped},
        )

        if not rankings:
            raise QoPScraperError(
                "No rankings could be extracted from the standings table. "
                "Check that the correct division is selected and the page rendered."
            )

        return rankings

    def _retry_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay for a given attempt (0-based)."""
        return self.RETRY_DELAY_BASE * (self.RETRY_BACKOFF_MULTIPLIER**attempt)
