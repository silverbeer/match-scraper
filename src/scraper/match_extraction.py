"""
Match data extraction utilities for MLS website scraping.

This module provides functionality to extract match information from the MLS website
results table, including parsing HTML elements, mapping data to Match objects,
and handling different match statuses with comprehensive error handling.
"""

import re
from datetime import datetime
from typing import Optional

from playwright.async_api import Page

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

    # CSS selectors for MLS website match elements
    RESULTS_TABLE_SELECTOR = (
        ".results-table, .matches-table, .schedule-table, table.matches"
    )
    MATCH_ROW_SELECTOR = "tbody tr, .match-row, .game-row"
    MATCH_CELL_SELECTORS = {
        "date": "td.date, .match-date, .game-date, td:nth-child(1)",
        "time": "td.time, .match-time, .game-time, td:nth-child(2)",
        "home_team": "td.home-team, .home, td:nth-child(3)",
        "away_team": "td.away-team, .away, td:nth-child(4)",
        "score": "td.score, .result, td:nth-child(5)",
        "venue": "td.venue, .location, td:nth-child(6)",
        "status": "td.status, .match-status, td:nth-child(7)",
    }

    # Alternative selectors for different page layouts
    MATCH_CARD_SELECTOR = ".match-card, .game-card, .fixture-card"
    NO_RESULTS_SELECTOR = ".no-results, .no-matches, .empty-results"

    # Regex patterns for data extraction
    SCORE_PATTERN = re.compile(r"(\d+)\s*[-–—]\s*(\d+)")
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

    async def extract_matches(
        self, age_group: str, division: str, competition: Optional[str] = None
    ) -> list[Match]:
        """
        Extract all matches from the current page.

        Args:
            age_group: Age group for the matches (e.g., "U14")
            division: Division for the matches
            competition: Optional competition name

        Returns:
            List of Match objects extracted from the page
        """
        try:
            logger.info(
                "Extracting matches from page",
                extra={
                    "age_group": age_group,
                    "division": division,
                    "competition": competition,
                },
            )

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
                logger.info("Table extraction found no matches, trying card-based extraction")
                matches = await self._extract_from_cards(age_group, division, competition)
            else:
                logger.info(f"Table extraction found {len(matches)} matches")

            logger.info(
                "Match extraction completed",
                extra={"matches_found": len(matches), "age_group": age_group},
            )

            return matches

        except Exception as e:
            logger.error(
                "Error extracting matches",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "age_group": age_group,
                    "division": division,
                },
            )
            raise MatchExtractionError(f"Failed to extract matches: {e}") from e

    async def _wait_for_results(self) -> bool:
        """
        Wait for results to appear on the page.

        Returns:
            True if results found, False otherwise
        """
        try:
            logger.debug("Waiting for results to appear")

            # Try multiple selectors for results container
            result_selectors = [
                self.RESULTS_TABLE_SELECTOR,
                self.MATCH_CARD_SELECTOR,
                ".results-container",
                ".matches-container",
                ".schedule-results",
            ]

            for selector in result_selectors:
                if await self.interactor.wait_for_element(selector, timeout=10000):
                    logger.debug("Results found", extra={"selector": selector})
                    return True

            logger.debug("No results container found")
            return False

        except Exception as e:
            logger.debug("Error waiting for results", extra={"error": str(e)})
            return False

    async def _check_no_results(self) -> bool:
        """
        Check if page shows no results message.

        Returns:
            True if no results message found, False otherwise
        """
        try:
            no_results_selectors = [
                self.NO_RESULTS_SELECTOR,
                ".no-results",
                ".no-matches",
                ".empty-results",
                ':has-text("No matches found")',
                ':has-text("No results")',
            ]

            for selector in no_results_selectors:
                if await self.interactor.wait_for_element(selector, timeout=2000):
                    logger.debug("No results message found", extra={"selector": selector})
                    return True

            return False

        except Exception as e:
            logger.debug("Error checking no results", extra={"error": str(e)})
            return False

    async def _extract_from_table(
        self, age_group: str, division: str, competition: Optional[str]
    ) -> list[Match]:
        """
        Extract matches from table-based layout.

        Args:
            age_group: Age group for the matches
            division: Division for the matches
            competition: Optional competition name

        Returns:
            List of Match objects
        """
        try:
            logger.debug("Attempting table-based extraction")

            # Find the results table
            table_selectors = [
                self.RESULTS_TABLE_SELECTOR,
                "table.matches",
                "table.schedule",
                ".results-table",
                "table",
            ]

            table_element = None
            for selector in table_selectors:
                if await self.interactor.wait_for_element(selector, timeout=3000):
                    table_element = await self.page.query_selector(selector)
                    if table_element:
                        logger.debug("Found table", extra={"selector": selector})
                        break

            if not table_element:
                logger.debug("No table found")
                return []

            # Get all match rows
            row_selectors = [
                "tbody tr",
                "tr.match-row",
                "tr.game-row",
                "tr:not(:first-child)",  # Skip header row
            ]

            match_rows = []
            for selector in row_selectors:
                rows = await table_element.query_selector_all(selector)
                if rows:
                    match_rows = rows
                    logger.debug("Found match rows", extra={"count": len(rows), "selector": selector})
                    break

            if not match_rows:
                logger.debug("No match rows found in table")
                return []

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

            logger.debug("Table extraction completed", extra={"matches": len(matches)})
            return matches

        except Exception as e:
            logger.debug("Error in table extraction", extra={"error": str(e)})
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
                    logger.debug("Found match cards", extra={"count": len(cards), "selector": selector})
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
        row_element,
        row_index: int,
        age_group: str,
        division: str,
        competition: Optional[str],
    ) -> Optional[Match]:
        """
        Extract match data from a table row element.

        Args:
            row_element: Playwright element for the table row
            row_index: Index of the row for ID generation
            age_group: Age group for the match
            division: Division for the match
            competition: Optional competition name

        Returns:
            Match object or None if extraction fails
        """
        try:
            logger.debug("Extracting match from row", extra={"row_index": row_index})

            # Extract data from cells
            cells = await row_element.query_selector_all("td")
            if len(cells) < 3:  # Need at least date, teams
                logger.debug("Insufficient cells in row", extra={"cell_count": len(cells)})
                return None

            # Try to extract data using different approaches
            match_data = {}

            # Approach 1: Use cell selectors
            for field, selectors in self.MATCH_CELL_SELECTORS.items():
                for selector in selectors.split(", "):
                    cell = await row_element.query_selector(selector)
                    if cell:
                        text = await cell.text_content()
                        if text and text.strip():
                            match_data[field] = text.strip()
                            break

            # Approach 2: Use cell positions if selectors fail
            if not match_data:
                match_data = await self._extract_from_cell_positions(cells)

            # Approach 3: Use text content analysis
            if not match_data:
                row_text = await row_element.text_content()
                if row_text:
                    match_data = self._parse_row_text(row_text.strip())

            if not match_data:
                logger.debug("No data extracted from row")
                return None

            # Convert to Match object
            match = await self._create_match_from_data(
                match_data, row_index, age_group, division, competition
            )

            logger.debug("Successfully extracted match from row", extra={"match_id": match.match_id if match else None})
            return match

        except Exception as e:
            logger.debug(
                "Error extracting match from row",
                extra={"row_index": row_index, "error": str(e)},
            )
            return None

    async def _extract_match_from_card(
        self,
        card_element,
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

            logger.debug("Successfully extracted match from card", extra={"match_id": match.match_id if match else None})
            return match

        except Exception as e:
            logger.debug(
                "Error extracting match from card",
                extra={"card_index": card_index, "error": str(e)},
            )
            return None

    async def _extract_from_cell_positions(self, cells) -> dict:
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
            logger.debug("Error extracting from cell positions", extra={"error": str(e)})
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
            for i, part in enumerate(parts):
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
            text_parts = [p for p in parts if len(p) > 3 and not any(c.isdigit() for c in p)]
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
            # Generate match ID
            match_id = f"{age_group}_{division}_{index}_{datetime.now().strftime('%Y%m%d')}"

            # Parse date and time
            match_date = self._parse_match_datetime(
                data.get("date", ""), data.get("time", "")
            )
            if not match_date:
                logger.debug("Could not parse match date/time", extra={"data": data})
                return None

            # Extract team names
            home_team = data.get("home_team", "").strip()
            away_team = data.get("away_team", "").strip()
            
            if not home_team or not away_team:
                logger.debug("Missing team names", extra={"home": home_team, "away": away_team})
                return None

            # Parse score and determine status
            score_text = data.get("score", "").strip()
            status_text = data.get("status", "").strip().lower()
            
            home_score, away_score, status = self._parse_score_and_status(score_text, status_text)

            # Create Match object
            match = Match(
                match_id=match_id,
                home_team=home_team,
                away_team=away_team,
                match_date=match_date,
                match_time=data.get("time"),
                venue=data.get("venue"),
                age_group=age_group,
                division=division,
                competition=competition,
                status=status,
                home_score=home_score,
                away_score=away_score,
            )

            logger.debug("Created match object", extra={"match_id": match_id, "status": status})
            return match

        except Exception as e:
            logger.debug(
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
            
            # MM/DD/YYYY
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
                    month_name, day, year = match.groups()
                    month_map = {
                        "january": 1, "jan": 1, "february": 2, "feb": 2,
                        "march": 3, "mar": 3, "april": 4, "apr": 4,
                        "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
                        "august": 8, "aug": 8, "september": 9, "sep": 9,
                        "october": 10, "oct": 10, "november": 11, "nov": 11,
                        "december": 12, "dec": 12
                    }
                    month = month_map.get(month_name.lower())
                    if month:
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

    def _parse_score_and_status(self, score_text: str, status_text: str) -> tuple[Optional[int], Optional[int], str]:
        """
        Parse score and status information.

        Args:
            score_text: Score text from the page
            status_text: Status text from the page

        Returns:
            Tuple of (home_score, away_score, status)
        """
        try:
            home_score = None
            away_score = None
            status = "scheduled"

            # Check for explicit status indicators
            if any(word in status_text for word in ["completed", "final", "finished"]):
                status = "completed"
            elif any(word in status_text for word in ["live", "playing", "in progress"]):
                status = "in_progress"
            elif any(word in status_text for word in ["scheduled", "upcoming"]):
                status = "scheduled"

            # Try to parse score
            if score_text:
                score_match = self.SCORE_PATTERN.search(score_text)
                if score_match:
                    home_score = int(score_match.group(1))
                    away_score = int(score_match.group(2))
                    # If we have a score, it's likely completed
                    if status == "scheduled":
                        status = "completed"
                elif any(word in score_text.lower() for word in ["vs", "v", "@"]):
                    # This indicates a scheduled match
                    status = "scheduled"

            return home_score, away_score, status

        except Exception as e:
            logger.debug(
                "Error parsing score and status",
                extra={"error": str(e), "score_text": score_text, "status_text": status_text},
            )
            return None, None, "scheduled"


# Example usage
async def example_match_extraction():
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
                    age_group="U14",
                    division="Northeast",
                    competition="MLS Next"
                )

                print(f"Extracted {len(matches)} matches:")
                for match in matches:
                    print(f"  {match.home_team} vs {match.away_team} - {match.status}")
                    if match.has_score():
                        print(f"    Score: {match.get_score_string()}")

            except MatchExtractionError as e:
                print(f"Match extraction failed: {e}")
            except Exception as e:
                print(f"Unexpected error: {e}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(example_match_extraction())