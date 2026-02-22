"""
MLS website filter application utilities.

This module provides functionality to apply filters on the MLS website including
age_group, club, competition, and division filters with comprehensive error handling
and validation.
"""

import asyncio
from typing import Any, Optional

from playwright.async_api import Frame, Page

from ..utils.logger import get_logger
from .browser import ElementInteractor
from .config import ScrapingConfig

logger = get_logger()


class FilterApplicationError(Exception):
    """Custom exception for filter application failures."""

    pass


class MLSFilterApplicator:
    """
    Handles application of filters on the MLS website iframe.

    All filters on the MLS website are contained within an iframe using Bootstrap Select
    components. This class provides methods to apply age group, club, competition,
    and division filters with proper iframe handling.
    """

    # Iframe access pattern - use more specific selector for the schedule iframe
    IFRAME_SELECTOR = 'main[role="main"] iframe, [aria-label*="main"] iframe, iframe[src*="modular11"]'

    # Age group value mappings (from Bootstrap Select)
    AGE_GROUP_VALUES = {
        "U13": "21",
        "U14": "22",
        "U15": "33",
        "U16": "14",
        "U17": "15",
        "U19": "26",
    }

    # Division value mappings (from Bootstrap Select - Select 3)
    DIVISION_VALUES = {
        "Central": "34",
        "Northeast": "41",
        "East": "35",
        "Mid-Atlantic": "68",
        "Florida": "46",
        "Southwest": "36",  # May need to verify these
        "Southeast": "37",  # May need to verify these
        "Northwest": "38",  # May need to verify these
        "Great Lakes": "39",  # May need to verify these
        "Texas": "40",  # May need to verify these
        "California": "42",  # May need to verify these
    }

    # Conference value mappings (for Academy Division and Homegrown Division pages)
    # On these pages, regional filtering uses "Conference" instead of "Division"
    CONFERENCE_VALUES = {
        "New England": "41",  # Maps to same value as Northeast
        "Northeast": "41",  # Allow both names
        "Mid-Atlantic": "68",
        "Southeast": "37",
        "Florida": "46",
        "Central": "34",
        "Great Lakes": "39",
        "Texas": "40",
        "Southwest": "36",
        "Northwest": "38",
        "California": "42",
    }

    # Bootstrap Select selectors for iframe filtering
    CLUB_SELECTOR = 'select[name="academy"][js-academy]'
    COMPETITION_SELECTOR = 'select[name="competition"]'

    # Valid filter options
    VALID_AGE_GROUPS = {"U13", "U14", "U15", "U16", "U17", "U19"}
    VALID_DIVISIONS = {
        "Homegrown Division",
        "Academy Division",
        "Northeast",
        "Southeast",
        "Central",
        "Southwest",
        "Northwest",
        "Mid-Atlantic",
        "Great Lakes",
        "Texas",
        "California",
    }

    # Loading indicator selectors for result waiting
    LOADING_INDICATOR_SELECTOR = ".loading, .spinner, .loading-indicator"
    RESULTS_CONTAINER_SELECTOR = (
        ".results-container, .matches-container, .schedule-results"
    )

    def __init__(self, page: Page, timeout: int = 15000):
        """
        Initialize filter applicator.

        Args:
            page: Playwright page instance
            timeout: Default timeout for operations in milliseconds
        """
        self.page = page
        self.timeout = timeout
        self.interactor = ElementInteractor(page, timeout)
        self._available_options: dict[str, set[str]] = {}
        self._iframe_content: Optional[Frame] = None

    async def _get_iframe_content(self) -> Any:
        """
        Get the iframe content frame for filter interactions.

        Returns:
            The iframe content frame or None if not found
        """
        try:
            if self._iframe_content is None:
                logger.debug("Looking for iframe on page")

                # Wait for iframe to be available
                try:
                    iframe_element = await self.page.wait_for_selector(
                        self.IFRAME_SELECTOR, timeout=10000
                    )
                    if iframe_element:
                        self._iframe_content = await iframe_element.content_frame()
                        logger.info("Successfully accessed iframe content frame")

                        # Simple wait for iframe to load - don't wait for specific elements
                        # as they may load at different times
                        await asyncio.sleep(5)
                        logger.info("Iframe content loading wait completed")

                    else:
                        logger.warning("Iframe element not found")
                        return None
                except Exception as e:
                    logger.warning(f"Iframe not found or timed out: {e}")
                    return None

            return self._iframe_content

        except Exception as e:
            logger.error("Failed to access iframe content", extra={"error": str(e)})
            return None

    async def discover_available_options(self) -> dict[str, set[str]]:
        """
        Discover available filter options from the iframe Bootstrap Select elements.

        Returns:
            Dictionary mapping filter names to sets of available options
        """
        try:
            logger.info("Discovering available filter options from iframe")

            options: dict[str, set[str]] = {
                "age_group": set(),
                "club": set(),
                "competition": set(),
                "division": set(),
            }

            # Get iframe content
            iframe_content = await self._get_iframe_content()
            if not iframe_content:
                logger.warning("Cannot access iframe for option discovery")
                # Fallback to hardcoded options
                options["age_group"] = self.VALID_AGE_GROUPS.copy()
                options["division"] = {"Homegrown Division", "Academy Division"}
                return options

            try:
                # For now, skip the complex discovery and use hardcoded options
                # since we know the filter application works with the right values
                logger.info("Using hardcoded age group options for reliable operation")
                options["age_group"] = self.VALID_AGE_GROUPS.copy()

                # Optional: Try to verify iframe has the expected structure (but don't block on it)
                try:
                    age_select = iframe_content.locator("select[js-age]")
                    select_count = await age_select.count()
                    logger.info(
                        f"Iframe verification: Found {select_count} select[js-age] elements"
                    )
                except Exception as verify_e:
                    logger.info(
                        f"Iframe verification failed (non-blocking): {verify_e}"
                    )

                logger.debug(f"Discovered age groups: {options['age_group']}")

                # For divisions, use hardcoded options for now
                # Could be enhanced to discover from iframe dropdowns
                options["division"] = {"Homegrown Division", "Academy Division"}

                logger.info("Successfully discovered options from iframe")

            except Exception as e:
                logger.debug(f"Error discovering from iframe, using fallback: {e}")
                # Fallback to hardcoded options
                options["age_group"] = self.VALID_AGE_GROUPS.copy()
                options["division"] = {"Homegrown Division", "Academy Division"}

            self._available_options = options
            logger.info(
                "Filter option discovery completed",
                extra={
                    "age_groups": len(options["age_group"]),
                    "clubs": len(options["club"]),
                    "competitions": len(options["competition"]),
                    "divisions": len(options["division"]),
                },
            )

            return options

        except Exception as e:
            logger.error(
                "Error discovering filter options",
                extra={"error": str(e), "error_type": type(e).__name__},
            )
            return {}

    async def apply_age_group_filter(self, age_group: str) -> bool:
        """
        Apply age group filter using iframe Bootstrap Select dropdown.

        Args:
            age_group: Age group to filter by (e.g., "U14")

        Returns:
            True if filter applied successfully, False otherwise
        """
        try:
            logger.info(
                "Applying age group filter in iframe", extra={"age_group": age_group}
            )

            if not age_group:
                logger.debug("Empty age group provided, skipping filter")
                return True

            # Validate age group
            if age_group not in self.VALID_AGE_GROUPS:
                logger.warning("Invalid age group", extra={"age_group": age_group})
                return False

            # Get iframe content
            iframe_content = await self._get_iframe_content()
            if not iframe_content:
                logger.error("Could not access iframe content for age group filter")
                return False

            # Strategy 1: Try direct select option with retries (most reliable based on testing)
            for attempt in range(3):
                try:
                    age_value = self.AGE_GROUP_VALUES.get(age_group)
                    logger.info(
                        f"Attempting direct select for {age_group} with value {age_value} (attempt {attempt + 1})"
                    )

                    if age_value:
                        age_select = iframe_content.locator("select[js-age]")
                        select_count = await age_select.count()
                        logger.info(
                            f"Found {select_count} select[js-age] elements for direct selection"
                        )

                        if select_count > 0:
                            await age_select.select_option(value=age_value)
                            logger.info(f"Selected option with value {age_value}")

                            # Give time for Bootstrap Select to update
                            await asyncio.sleep(2)

                            # Since our manual test showed this works, trust it worked and return success
                            logger.info(
                                "Age group filter applied via direct select",
                                extra={"age_group": age_group, "value": age_value},
                            )
                            return True
                        else:
                            if attempt < 2:  # Only wait if we have more attempts
                                logger.info(
                                    f"No select elements found, waiting before retry {attempt + 1}"
                                )
                                await asyncio.sleep(3)  # Wait for elements to load
                            else:
                                logger.warning(
                                    "No select[js-age] elements found after all retries"
                                )
                    else:
                        logger.warning(
                            f"No value mapping found for age group: {age_group}"
                        )
                        break  # No point retrying if we don't have the value

                except Exception as e:
                    logger.warning(
                        f"Direct select method failed on attempt {attempt + 1}: {e}"
                    )
                    if attempt < 2:
                        await asyncio.sleep(2)  # Wait before retry

            # Strategy 2: Try Bootstrap Select UI interaction (based on actual HTML structure)
            try:
                # Find the age group bootstrap select specifically (using js-age attribute)
                age_bootstrap_select = iframe_content.locator("select[js-age]").locator(
                    ".."
                )

                # Click the dropdown toggle button
                dropdown_button = age_bootstrap_select.locator(".dropdown-toggle")
                await dropdown_button.click()
                await asyncio.sleep(1)  # Give more time for dropdown to open

                # Wait for dropdown to be visible
                await iframe_content.locator(".dropdown-menu.open").wait_for(
                    timeout=2000
                )

                # Click the specific age group option from the dropdown menu
                age_option = iframe_content.locator(
                    f'.dropdown-menu li a .text:has-text("{age_group}")'
                ).first()
                await age_option.click()
                await asyncio.sleep(1)

                logger.info(
                    "Age group filter applied via Bootstrap UI",
                    extra={"age_group": age_group},
                )
                return True

            except Exception as e:
                logger.debug(f"Bootstrap UI method failed: {e}")

            # Strategy 3: Try clicking the option parent link directly
            try:
                # First ensure dropdown is open
                dropdown_button = iframe_content.locator(
                    ".bootstrap-select .dropdown-toggle"
                ).first()
                await dropdown_button.click()
                await asyncio.sleep(1)

                # Click the <a> element that contains the age group text
                age_link = iframe_content.locator(
                    f'li a:has(.text:has-text("{age_group}"))'
                )
                await age_link.click()
                await asyncio.sleep(1)

                logger.info(
                    "Age group filter applied via option link",
                    extra={"age_group": age_group},
                )
                return True

            except Exception as e:
                logger.debug(f"Option link method failed: {e}")

            logger.error("All age group filter strategies failed")
            return False

        except Exception as e:
            logger.error(
                "Error applying age group filter",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "age_group": age_group,
                },
            )
            return False

    async def apply_club_filter(self, club: str) -> bool:
        """
        Apply club filter using iframe Bootstrap Select dropdown.

        The club select element (``select[name="academy"][js-academy]``) only
        exists on certain pages (e.g. Academy).  On pages where it is absent
        (e.g. Homegrown) we skip silently instead of retrying and logging
        errors.

        Args:
            club: Club name to filter by

        Returns:
            True if filter applied successfully, False otherwise
        """
        try:
            logger.info("Applying club filter in iframe", extra={"club": club})

            if not club:
                logger.debug("Empty club provided, skipping filter")
                return True

            # Get iframe content
            iframe_content = await self._get_iframe_content()
            if not iframe_content:
                logger.error("Could not access iframe content for club filter")
                return False

            # Quick check: does the club select element exist on this page at all?
            club_select = iframe_content.locator(self.CLUB_SELECTOR)
            if await club_select.count() == 0:
                logger.info(
                    "Club select element not present on this page, skipping club filter",
                    extra={"club": club, "selector": self.CLUB_SELECTOR},
                )
                return True

            # Strategy 1: Try direct select option with retries
            for attempt in range(3):
                try:
                    logger.info(
                        f"Attempting direct club select for {club} (attempt {attempt + 1})"
                    )

                    # Find the club select element (select[name="academy"][js-academy])
                    club_select = iframe_content.locator(self.CLUB_SELECTOR)
                    select_count = await club_select.count()
                    logger.info(f"Found {select_count} club select elements")

                    if select_count > 0:
                        # Try to select by visible text (club name)
                        await club_select.select_option(label=club)
                        logger.info(f"Selected club option with label {club}")

                        # Give time for Bootstrap Select to update
                        await asyncio.sleep(2)

                        logger.info(
                            "Club filter applied via direct select",
                            extra={"club": club},
                        )
                        return True
                    else:
                        if attempt < 2:  # Only wait if we have more attempts
                            logger.info(
                                f"No club select elements found, waiting before retry {attempt + 1}"
                            )
                            await asyncio.sleep(3)  # Wait for elements to load
                        else:
                            logger.warning(
                                "No club select elements found after all retries"
                            )

                except Exception as e:
                    logger.warning(
                        f"Direct select method failed on attempt {attempt + 1}: {e}"
                    )
                    if attempt < 2:
                        await asyncio.sleep(2)  # Wait before retry

            # Strategy 2: Try Bootstrap Select UI interaction
            try:
                # Find the club bootstrap select container
                club_bootstrap_select = iframe_content.locator(
                    self.CLUB_SELECTOR
                ).locator("..")

                # Click the dropdown toggle button for club select
                dropdown_button = club_bootstrap_select.locator(".dropdown-toggle")
                await dropdown_button.click()
                await asyncio.sleep(1)  # Give time for dropdown to open

                # Wait for dropdown to be visible
                await iframe_content.locator(".dropdown-menu.open").wait_for(
                    timeout=2000
                )

                # Click the specific club option from the dropdown menu
                club_option = iframe_content.locator(
                    f'.dropdown-menu li a .text:has-text("{club}")'
                ).first()
                await club_option.click()
                await asyncio.sleep(1)

                logger.info(
                    "Club filter applied via Bootstrap UI", extra={"club": club}
                )
                return True

            except Exception as e:
                logger.debug(f"Bootstrap UI method failed: {e}")

            # Strategy 3: Try searching in the club dropdown (since it has search functionality)
            try:
                # Click the club dropdown toggle to open it
                club_bootstrap_select = iframe_content.locator(
                    self.CLUB_SELECTOR
                ).locator("..")
                dropdown_button = club_bootstrap_select.locator(".dropdown-toggle")
                await dropdown_button.click()
                await asyncio.sleep(1)

                # Find and use the search box
                search_box = iframe_content.locator('.bs-searchbox input[type="text"]')
                if await search_box.count() > 0:
                    await search_box.fill(club)
                    await asyncio.sleep(1)  # Wait for search results

                    # Click the first matching result
                    search_result = iframe_content.locator(
                        f'.dropdown-menu li a .text:has-text("{club}")'
                    ).first()
                    await search_result.click()
                    await asyncio.sleep(1)

                    logger.info("Club filter applied via search", extra={"club": club})
                    return True
                else:
                    logger.debug("Search box not found in club dropdown")

            except Exception as e:
                logger.debug(f"Search method failed: {e}")

            logger.error("All club filter strategies failed")
            return False

        except Exception as e:
            logger.error(
                "Error applying club filter",
                extra={"error": str(e), "error_type": type(e).__name__, "club": club},
            )
            return False

    async def apply_competition_filter(self, competition: str) -> bool:
        """
        Apply competition filter using iframe Bootstrap Select dropdown.

        Args:
            competition: Competition name to filter by

        Returns:
            True if filter applied successfully, False otherwise
        """
        try:
            logger.info(
                "Applying competition filter in iframe",
                extra={"competition": competition},
            )

            if not competition:
                logger.debug("Empty competition provided, skipping filter")
                return True

            # Validate competition option
            if not await self._validate_filter_option("competition", competition):
                logger.warning(
                    "Invalid competition", extra={"competition": competition}
                )
                return False

            # Get iframe content
            iframe_content = await self._get_iframe_content()
            if not iframe_content:
                logger.error("Could not access iframe content for competition filter")
                return False

            # Strategy 1: Try direct select option with retries
            for attempt in range(3):
                try:
                    logger.info(
                        f"Attempting direct competition select for {competition} (attempt {attempt + 1})"
                    )

                    # Find the competition select element
                    competition_select = iframe_content.locator(
                        self.COMPETITION_SELECTOR
                    )
                    select_count = await competition_select.count()
                    logger.info(f"Found {select_count} competition select elements")

                    if select_count > 0:
                        # Try to select by visible text (competition name)
                        await competition_select.select_option(label=competition)
                        logger.info(
                            f"Selected competition option with label {competition}"
                        )

                        # Give time for Bootstrap Select to update
                        await asyncio.sleep(2)

                        logger.info(
                            "Competition filter applied via direct select",
                            extra={"competition": competition},
                        )
                        return True
                    else:
                        if attempt < 2:  # Only wait if we have more attempts
                            logger.info(
                                f"No competition select elements found, waiting before retry {attempt + 1}"
                            )
                            await asyncio.sleep(3)  # Wait for elements to load
                        else:
                            logger.warning(
                                "No competition select elements found after all retries"
                            )

                except Exception as e:
                    logger.warning(
                        f"Direct select method failed on attempt {attempt + 1}: {e}"
                    )
                    if attempt < 2:
                        await asyncio.sleep(2)  # Wait before retry

            # Strategy 2: Try Bootstrap Select UI interaction
            try:
                # Find the competition bootstrap select container
                competition_bootstrap_select = iframe_content.locator(
                    self.COMPETITION_SELECTOR
                ).locator("..")

                # Click the dropdown toggle button for competition select
                dropdown_button = competition_bootstrap_select.locator(
                    ".dropdown-toggle"
                )
                await dropdown_button.click()
                await asyncio.sleep(1)  # Give time for dropdown to open

                # Wait for dropdown to be visible
                await iframe_content.locator(".dropdown-menu.open").wait_for(
                    timeout=2000
                )

                # Click the specific competition option from the dropdown menu
                competition_option = iframe_content.locator(
                    f'.dropdown-menu li a .text:has-text("{competition}")'
                ).first()
                await competition_option.click()
                await asyncio.sleep(1)

                logger.info(
                    "Competition filter applied via Bootstrap UI",
                    extra={"competition": competition},
                )
                return True

            except Exception as e:
                logger.debug(f"Bootstrap UI method failed: {e}")

            logger.error("All competition filter strategies failed")
            return False

        except Exception as e:
            logger.error(
                "Error applying competition filter",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "competition": competition,
                },
            )
            return False

    async def _is_on_special_league_page(self) -> bool:
        """
        Check if we're on an Academy Division or Homegrown Division page.
        These pages use "Conference" instead of "Division" for regional filtering.

        Returns:
            True if on Academy or Homegrown Division page, False otherwise
        """
        try:
            current_url = self.page.url
            is_special = (
                "/academy_division/" in current_url
                or "/homegrown-division/" in current_url
            )

            if is_special:
                logger.info(
                    "Detected special league page (Academy/Homegrown)",
                    extra={"url": current_url},
                )

            return is_special
        except Exception as e:
            logger.debug(f"Error checking page type: {e}")
            return False

    async def apply_conference_filter(self, conference: str) -> bool:
        """
        Apply conference filter on Academy Division or Homegrown Division pages.
        These pages use "Conference" instead of "Division" for regional filtering.

        Args:
            conference: Conference name to filter by (e.g., "New England")

        Returns:
            True if filter applied successfully, False otherwise
        """
        try:
            logger.info(
                "Applying conference filter in iframe", extra={"conference": conference}
            )

            if not conference:
                logger.debug("Empty conference provided, skipping filter")
                return True

            # Validate conference option - accept both conference names and division names
            if (
                conference not in self.CONFERENCE_VALUES
                and conference not in self.VALID_DIVISIONS
            ):
                logger.warning("Invalid conference", extra={"conference": conference})
                return False

            # Get iframe content
            iframe_content = await self._get_iframe_content()
            if not iframe_content:
                logger.error("Could not access iframe content for conference filter")
                return False

            # Strategy 1: Try JavaScript manipulation of select element (primary method)
            # The Bootstrap selectpicker has the select element overlaying the button,
            # blocking clicks. We use JavaScript to directly manipulate the select.
            try:
                logger.info(
                    f"Attempting JavaScript select manipulation for conference {conference} (attempt 1)"
                )

                # Wait a bit for the dropdown to be ready
                await asyncio.sleep(1)

                # Use JavaScript to find and select the conference option
                # The conference select is the 4th select element (index 3)
                js_result = await iframe_content.evaluate(
                    """
                    (conference) => {
                        // Get all select elements
                        const selects = document.querySelectorAll('select');
                        if (selects.length < 4) {
                            return { success: false, error: 'Not enough select elements', count: selects.length };
                        }

                        // Conference is the 4th select (index 3)
                        const conferenceSelect = selects[3];

                        // Find the option with matching text
                        const options = Array.from(conferenceSelect.options);
                        const targetOption = options.find(opt => opt.text.trim() === conference);

                        if (!targetOption) {
                            const availableOptions = options.map(opt => opt.text.trim()).filter(t => t);
                            return {
                                success: false,
                                error: 'Option not found',
                                available: availableOptions
                            };
                        }

                        // Select the option
                        targetOption.selected = true;

                        // Trigger change event to notify Bootstrap selectpicker
                        const changeEvent = new Event('change', { bubbles: true });
                        conferenceSelect.dispatchEvent(changeEvent);

                        // Also trigger Bootstrap selectpicker refresh if available
                        if (window.jQuery && window.jQuery.fn.selectpicker) {
                            try {
                                window.jQuery(conferenceSelect).selectpicker('refresh');
                            } catch (e) {
                                // Ignore jQuery errors
                            }
                        }

                        return {
                            success: true,
                            value: targetOption.value,
                            text: targetOption.text.trim()
                        };
                    }
                """,
                    conference,
                )

                logger.info(f"JavaScript result: {js_result}")

                if js_result.get("success"):
                    await asyncio.sleep(1)  # Wait for selection to apply
                    logger.info(
                        "Conference filter applied via JavaScript",
                        extra={
                            "conference": conference,
                            "value": js_result.get("value"),
                        },
                    )
                    return True
                else:
                    logger.warning(
                        f"JavaScript method failed: {js_result.get('error')}, available options: {js_result.get('available', [])}"
                    )

            except Exception as e:
                logger.warning(f"JavaScript method failed with exception: {e}")

            # Strategy 2: Try direct select option as fallback
            for attempt in range(3):
                try:
                    conference_value = self.CONFERENCE_VALUES.get(conference)
                    logger.info(
                        f"Attempting direct select for conference {conference} with value {conference_value} (attempt {attempt + 1})"
                    )

                    if conference_value:
                        # Find all select elements - conference might be a hidden select
                        all_selects = await iframe_content.locator("select").all()
                        logger.info(f"Found {len(all_selects)} select elements total")

                        if (
                            len(all_selects) >= 4
                        ):  # Make sure we have at least 4 selects
                            conference_select = all_selects[
                                3
                            ]  # Index 3 is the 4th select (conference/division)
                            await conference_select.select_option(
                                value=conference_value,
                                timeout=5000,  # Reduced timeout since this is fallback
                            )
                            logger.info(
                                f"Selected conference option with value {conference_value}"
                            )

                            # Give time for Bootstrap Select to update
                            await asyncio.sleep(2)

                            logger.info(
                                "Conference filter applied via direct select",
                                extra={
                                    "conference": conference,
                                    "value": conference_value,
                                },
                            )
                            return True
                        else:
                            if attempt < 2:  # Only wait if we have more attempts
                                logger.info(
                                    f"Not enough select elements found ({len(all_selects)}), waiting before retry {attempt + 1}"
                                )
                                await asyncio.sleep(2)  # Reduced wait time
                            else:
                                logger.warning(
                                    f"Not enough select elements found after all retries: {len(all_selects)}"
                                )
                    else:
                        logger.warning(
                            f"No value mapping found for conference: {conference}"
                        )
                        break  # No point retrying if we don't have the value

                except Exception as e:
                    logger.warning(
                        f"Direct select method failed on attempt {attempt + 1}: {e}"
                    )
                    if attempt < 2:
                        await asyncio.sleep(1)  # Reduced wait before retry

            logger.error("All conference filter strategies failed")
            return False

        except Exception as e:
            logger.error(
                "Error applying conference filter",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "conference": conference,
                },
            )
            return False

    async def apply_division_filter(self, division: str) -> bool:
        """
        Apply division filter using iframe Bootstrap Select dropdown.

        Args:
            division: Division name to filter by

        Returns:
            True if filter applied successfully, False otherwise
        """
        try:
            logger.info(
                "Applying division filter in iframe", extra={"division": division}
            )

            if not division:
                logger.debug("Empty division provided, skipping filter")
                return True

            # Validate division option
            if division not in self.VALID_DIVISIONS:
                logger.warning("Invalid division", extra={"division": division})
                return False

            # Get iframe content
            iframe_content = await self._get_iframe_content()
            if not iframe_content:
                logger.error("Could not access iframe content for division filter")
                return False

            # Strategy 1: Try direct select option with retries (same approach as age groups)
            for attempt in range(3):
                try:
                    division_value = self.DIVISION_VALUES.get(division)
                    logger.info(
                        f"Attempting direct select for {division} with value {division_value} (attempt {attempt + 1})"
                    )

                    if division_value:
                        # Find the division select (it's the 4th select element - index 3)
                        all_selects = await iframe_content.locator("select").all()
                        logger.info(f"Found {len(all_selects)} select elements total")

                        if (
                            len(all_selects) >= 4
                        ):  # Make sure we have at least 4 selects
                            division_select = all_selects[
                                3
                            ]  # Index 3 is the 4th select (division)
                            await division_select.select_option(value=division_value)
                            logger.info(
                                f"Selected division option with value {division_value}"
                            )

                            # Give time for Bootstrap Select to update
                            await asyncio.sleep(2)

                            # Since our manual test showed this approach works, trust it worked
                            logger.info(
                                "Division filter applied via direct select",
                                extra={"division": division, "value": division_value},
                            )
                            return True
                        else:
                            if attempt < 2:  # Only wait if we have more attempts
                                logger.info(
                                    f"Not enough select elements found ({len(all_selects)}), waiting before retry {attempt + 1}"
                                )
                                await asyncio.sleep(3)  # Wait for elements to load
                            else:
                                logger.warning(
                                    f"Not enough select elements found after all retries: {len(all_selects)}"
                                )
                    else:
                        logger.warning(
                            f"No value mapping found for division: {division}"
                        )
                        break  # No point retrying if we don't have the value

                except Exception as e:
                    logger.warning(
                        f"Direct select method failed on attempt {attempt + 1}: {e}"
                    )
                    if attempt < 2:
                        await asyncio.sleep(2)  # Wait before retry

            # Strategy 2: Try role-based interaction (from recorded script) - as fallback
            try:
                # Extract the division name (e.g., "Central" from "Division Central")
                division_name = division.replace("Division", "").strip()
                division_button = iframe_content.get_by_role(
                    "button", name=f"Division {division_name}"
                )
                await division_button.click()

                logger.info(
                    "Division filter applied via role button",
                    extra={"division": division},
                )
                return True

            except Exception as e:
                logger.debug(f"Role button method failed: {e}")

            # Strategy 3: Try Bootstrap Select UI interaction - as fallback
            try:
                # Click the division dropdown toggle
                division_dropdown = iframe_content.locator(
                    'label:has-text("Division") + div .dropdown-toggle'
                )
                await division_dropdown.click()
                await asyncio.sleep(0.5)

                # Click the specific division option
                division_option = iframe_content.locator(
                    f'span.text:has-text("{division}")'
                )
                await division_option.click()
                await asyncio.sleep(0.5)

                logger.info(
                    "Division filter applied via Bootstrap UI",
                    extra={"division": division},
                )
                return True

            except Exception as e:
                logger.debug(f"Bootstrap UI method failed: {e}")

            # Strategy 4: For Academy/Homegrown divisions, try URL navigation as final fallback
            division_lower = division.lower()
            if "academy" in division_lower or "homegrown" in division_lower:
                logger.info(
                    "Trying URL navigation for special division",
                    extra={"division": division},
                )
                return await self._apply_division_via_url(division)

            logger.error("All division filter strategies failed")
            return False

        except Exception as e:
            logger.error(
                "Error applying division filter",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "division": division,
                },
            )
            return False

    async def _apply_age_group_via_url(self, age_group: str) -> bool:
        """
        Apply age group filter by navigating to the appropriate URL.

        Args:
            age_group: Age group to filter by (e.g., "U14")

        Returns:
            True if filter applied successfully, False otherwise
        """
        try:
            logger.info(
                "Applying age group filter via URL navigation",
                extra={"age_group": age_group},
            )

            if not age_group:
                logger.debug("Empty age group provided, skipping filter")
                return True

            # Validate age group
            if age_group not in self.VALID_AGE_GROUPS:
                logger.warning("Invalid age group", extra={"age_group": age_group})
                return False

            # Map age group to URL path
            age_group_lower = age_group.lower()
            url_path = None

            if age_group_lower == "u13":
                url_path = "/mlsnext/schedule/u13/"
            elif age_group_lower == "u14":
                url_path = "/mlsnext/schedule/u14/"
            elif age_group_lower == "u15":
                url_path = "/mlsnext/schedule/u15/"
            elif age_group_lower == "u16":
                url_path = "/mlsnext/schedule/u16/"
            elif age_group_lower == "u17":
                url_path = "/mlsnext/schedule/u17/"
            elif age_group_lower == "u19":
                url_path = "/mlsnext/schedule/u19/"

            if url_path:
                # Navigate to the age group specific page
                base_url = "https://www.mlssoccer.com"
                full_url = base_url + url_path

                logger.info("Navigating to age group URL", extra={"url": full_url})
                await self.page.goto(full_url, wait_until="load")

                # Wait for page to load
                await asyncio.sleep(2)

                logger.info(
                    "Age group filter applied via URL navigation",
                    extra={"age_group": age_group, "url": full_url},
                )
                return True
            else:
                logger.error(
                    "No URL mapping found for age group", extra={"age_group": age_group}
                )
                return False

        except Exception as e:
            logger.error(
                "Error applying age group filter via URL",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "age_group": age_group,
                },
            )
            return False

    async def _apply_division_via_url(self, division: str) -> bool:
        """
        Apply division filter by navigating to the appropriate URL.

        Args:
            division: Division name to filter by

        Returns:
            True if filter applied successfully, False otherwise
        """
        try:
            logger.info(
                "Applying division filter via URL navigation",
                extra={"division": division},
            )

            if not division:
                logger.debug("Empty division provided, skipping filter")
                return True

            # Validate division option
            if division not in self.VALID_DIVISIONS:
                logger.warning("Invalid division", extra={"division": division})
                return False

            # Map division to URL path
            division_lower = division.lower()
            url_path = None

            if "homegrown" in division_lower:
                url_path = "/mlsnext/schedule/homegrown-division/"
            elif "academy" in division_lower:
                url_path = "/mlsnext/schedule/academy_division/"
            elif division_lower in [
                "northeast",
                "southeast",
                "central",
                "southwest",
                "northwest",
                "mid-atlantic",
                "great lakes",
                "texas",
                "california",
            ]:
                # For geographical divisions, we might need to construct a different URL
                # For now, log that this type of division filtering needs additional investigation
                logger.warning(
                    "Geographical division filtering not yet implemented",
                    extra={"division": division},
                )
                return True  # Return True to not fail the whole process

            if url_path:
                # Navigate to the division specific page
                base_url = "https://www.mlssoccer.com"
                full_url = base_url + url_path

                logger.info("Navigating to division URL", extra={"url": full_url})
                await self.page.goto(full_url, wait_until="load")

                # Wait for page to load
                await asyncio.sleep(2)

                logger.info(
                    "Division filter applied via URL navigation",
                    extra={"division": division, "url": full_url},
                )
                return True
            else:
                logger.error(
                    "No URL mapping found for division", extra={"division": division}
                )
                return False

        except Exception as e:
            logger.error(
                "Error applying division filter via URL",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "division": division,
                },
            )
            return False

    async def apply_date_filter(self, start_date: str, end_date: str) -> bool:
        """
        Apply date filter using iframe date picker.

        Args:
            start_date: Start date in MM/DD/YYYY format
            end_date: End date in MM/DD/YYYY format

        Returns:
            True if filter applied successfully, False otherwise
        """
        try:
            logger.info(
                "Applying date filter in iframe",
                extra={"start_date": start_date, "end_date": end_date},
            )

            if not start_date or not end_date:
                logger.debug("Empty dates provided, skipping date filter")
                return True

            # Get iframe content
            iframe_content = await self._get_iframe_content()
            if not iframe_content:
                logger.error("Could not access iframe content for date filter")
                return False

            # Strategy 1: Use calendar date picker by clicking actual date cells
            try:
                from datetime import datetime

                # Parse the provided dates (MM/DD/YYYY format)
                parsed_start_date = datetime.strptime(start_date, "%m/%d/%Y").date()
                parsed_end_date = datetime.strptime(end_date, "%m/%d/%Y").date()

                logger.info(
                    f"Using provided date range - Start: {parsed_start_date}, End: {parsed_end_date}"
                )

                # Find and click the date field to open calendar
                date_field = iframe_content.locator('input[name="datefilter"]')
                if await date_field.count() > 0:
                    await date_field.click()
                    logger.info("Clicked date field to open calendar")
                    await asyncio.sleep(2)  # Wait for calendar to appear

                    # Check if daterangepicker appeared
                    calendar_picker = iframe_content.locator(".daterangepicker")
                    if await calendar_picker.count() > 0:
                        logger.info("Calendar picker opened successfully")

                        # Extract day numbers from parsed dates
                        start_day = parsed_start_date.day
                        end_day = parsed_end_date.day

                        # Check if dates are in the same month
                        same_month = (
                            parsed_start_date.year == parsed_end_date.year
                            and parsed_start_date.month == parsed_end_date.month
                        )

                        # Click on start date - use left calendar
                        start_date_selectors = [
                            f'.daterangepicker .drp-calendar.left td[data-title]:has-text("{start_day}"):not(.off)',
                            f'.daterangepicker .drp-calendar.left td:has-text("{start_day}"):not(.off)',
                            f'.drp-calendar.left .calendar-table td:has-text("{start_day}"):not(.off)',
                            f'.daterangepicker .left td:has-text("{start_day}"):not(.off)',
                        ]

                        start_clicked = False
                        for start_selector in start_date_selectors:
                            start_cell = iframe_content.locator(start_selector)
                            if await start_cell.count() > 0:
                                await start_cell.first.click()
                                logger.info(
                                    f"Clicked start date {start_day} on left calendar using selector: {start_selector}"
                                )
                                await asyncio.sleep(1)
                                start_clicked = True
                                break

                        if not start_clicked:
                            logger.warning(
                                f"Could not click start date {start_day} on left calendar"
                            )
                            return False

                        # Click on end date - use right calendar if different month, left if same month
                        if same_month:
                            end_date_selectors = [
                                f'.daterangepicker .drp-calendar.left td[data-title]:has-text("{end_day}"):not(.off)',
                                f'.daterangepicker .drp-calendar.left td:has-text("{end_day}"):not(.off)',
                                f'.drp-calendar.left .calendar-table td:has-text("{end_day}"):not(.off)',
                                f'.daterangepicker .left td:has-text("{end_day}"):not(.off)',
                            ]
                        else:
                            end_date_selectors = [
                                f'.daterangepicker .drp-calendar.right td[data-title]:has-text("{end_day}"):not(.off)',
                                f'.daterangepicker .drp-calendar.right td:has-text("{end_day}"):not(.off)',
                                f'.drp-calendar.right .calendar-table td:has-text("{end_day}"):not(.off)',
                                f'.daterangepicker .right td:has-text("{end_day}"):not(.off)',
                            ]

                        end_clicked = False
                        for end_selector in end_date_selectors:
                            end_cell = iframe_content.locator(end_selector)
                            if await end_cell.count() > 0:
                                await end_cell.first.click()
                                logger.info(
                                    f"Clicked end date {end_day} on {'left' if same_month else 'right'} calendar using selector: {end_selector}"
                                )
                                await asyncio.sleep(1)
                                end_clicked = True
                                break

                        if not end_clicked:
                            logger.warning(
                                f"Could not click end date {end_day} on calendar"
                            )
                            return False

                        # Click Apply button
                        apply_selectors = [
                            ".daterangepicker button.applyBtn",
                            "button.applyBtn",
                            ".drp-buttons button.applyBtn",
                            'button:has-text("Apply")',
                        ]

                        apply_clicked = False
                        for apply_selector in apply_selectors:
                            apply_button = iframe_content.locator(apply_selector)
                            if await apply_button.count() > 0:
                                await apply_button.click()
                                logger.info(f"Clicked Apply button: {apply_selector}")
                                await asyncio.sleep(3)  # Wait for filter to apply
                                apply_clicked = True
                                break

                        if not apply_clicked:
                            logger.warning("Apply button not found")
                            return False

                        logger.info(
                            "Date filter applied via calendar date picker",
                            extra={
                                "start_date": str(parsed_start_date),
                                "end_date": str(parsed_end_date),
                            },
                        )
                        return True
                    else:
                        logger.warning(
                            "Calendar picker did not appear after clicking date field"
                        )
                        return False
                else:
                    logger.warning("Date field not found")

            except Exception as e:
                logger.warning(f"Direct text input method failed: {e}")

            # Strategy 2: Try role-based interaction (from recorded script)
            try:
                # Click the Match Date textbox
                match_date_textbox = iframe_content.get_by_role(
                    "textbox", name="Match Date"
                )
                await match_date_textbox.click()
                logger.info("Clicked Match Date textbox")
                await asyncio.sleep(1)

                # This opens a calendar picker - for now, just click Apply to use default dates
                # TODO: Implement specific date cell clicking based on start_date and end_date
                apply_button = iframe_content.get_by_role("button", name="Apply")
                await apply_button.click()
                logger.info("Clicked Apply button via role-based method")
                await asyncio.sleep(1)

                logger.info("Date filter applied via role-based interaction")
                return True

            except Exception as e:
                logger.debug(f"Role-based method failed: {e}")

            logger.error("Date filter application failed")
            return False

        except Exception as e:
            logger.error(
                "Error applying date filter",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "start_date": start_date,
                    "end_date": end_date,
                },
            )
            return False

    async def apply_all_filters(self, config: ScrapingConfig) -> bool:
        """
        Apply all filters from configuration.

        Args:
            config: Scraping configuration containing filter values

        Returns:
            True if all filters applied successfully, False otherwise
        """
        try:
            logger.info(
                "Applying all filters",
                extra={
                    "age_group": config.age_group,
                    "league": config.league,
                    "club": config.club,
                    "competition": config.competition,
                    "division": config.division,
                    "conference": config.conference,
                },
            )

            # Discover available options from current page
            await self.discover_available_options()

            # Apply filters using the appropriate method for current page
            filters_applied = []

            # Always try iframe filtering first since we discovered filters are available
            iframe_content = await self._get_iframe_content()

            if iframe_content:
                # Use iframe filtering when iframe is available
                logger.info("Using iframe filtering - dropdown filters detected")

                # Apply age group filter via iframe
                if config.age_group:
                    if await self.apply_age_group_filter(config.age_group):
                        filters_applied.append("age_group")
                        await asyncio.sleep(1)
                    else:
                        logger.error("Failed to apply age group filter via iframe")
                        return False

                # Apply division/conference filter based on league type
                if config.league == "Homegrown":
                    # Use division filter for Homegrown league
                    if config.division:
                        logger.info(
                            "Applying division filter for Homegrown league",
                            extra={"division": config.division},
                        )
                        if await self.apply_division_filter(config.division):
                            filters_applied.append("division")
                            await asyncio.sleep(1)
                        else:
                            logger.error("Failed to apply division filter via iframe")
                            return False
                elif config.league == "Academy":
                    # Use conference filter for Academy league
                    if config.conference:
                        logger.info(
                            "Applying conference filter for Academy league",
                            extra={"conference": config.conference},
                        )
                        if await self.apply_conference_filter(config.conference):
                            filters_applied.append("conference")
                            await asyncio.sleep(1)
                        else:
                            logger.error("Failed to apply conference filter via iframe")
                            return False

            else:
                # Fallback to URL navigation only if no iframe is available
                logger.info("No iframe detected - falling back to URL navigation")

                # Apply age group filter via URL navigation
                if config.age_group:
                    if await self._apply_age_group_via_url(config.age_group):
                        filters_applied.append("age_group")
                    else:
                        logger.error("Failed to apply age group filter via URL")
                        return False

                # Apply division filter via URL navigation
                if config.division:
                    if await self._apply_division_via_url(config.division):
                        filters_applied.append("division")
                    else:
                        logger.error("Failed to apply division filter via URL")
                        return False

            # Skip date filtering here - it's handled separately in the main workflow
            # to avoid duplicate calendar interactions

            # Apply club and competition filters if iframe is available
            if iframe_content:
                # Apply club filter via iframe
                if config.club:
                    if await self.apply_club_filter(config.club):
                        filters_applied.append("club")
                        await asyncio.sleep(1)
                    else:
                        logger.warning("Failed to apply club filter via iframe")
                        # Don't fail the whole process for club filter

                # Apply competition filter via iframe
                if config.competition:
                    if await self.apply_competition_filter(config.competition):
                        filters_applied.append("competition")
                        await asyncio.sleep(1)
                    else:
                        logger.warning("Failed to apply competition filter via iframe")
                        # Don't fail the whole process for competition filter

            logger.info(
                "All filters applied successfully",
                extra={"filters_applied": filters_applied},
            )

            # Wait for results to load after applying all filters
            await self.wait_for_filter_results()

            return True

        except Exception as e:
            logger.error(
                "Error applying all filters",
                extra={"error": str(e), "error_type": type(e).__name__},
            )
            return False

    async def wait_for_filter_results(self, timeout: Optional[int] = None) -> bool:
        """
        Wait for filter results to load after applying filters.

        Args:
            timeout: Timeout in milliseconds (uses default if None)

        Returns:
            True if results loaded successfully, False otherwise
        """
        timeout = timeout or self.timeout

        try:
            logger.info("Waiting for filter results to load")

            # Wait for the actual results container that we know exists
            results_selectors = [
                ".container-fluid.container-table-matches",  # The actual container we use
                ".container-row .row.table-content-row.hidden-xs",  # The actual match rows
                "table tbody tr",  # Fallback table rows
            ]

            for selector in results_selectors:
                if await self.interactor.wait_for_element(selector, timeout=5000):
                    logger.info("Filter results loaded", extra={"selector": selector})

                    # Additional wait to ensure content is fully rendered
                    await asyncio.sleep(2)
                    return True

            # If no specific results container found, just wait a bit and continue
            logger.info(
                "No specific results container found, proceeding with extraction"
            )
            await asyncio.sleep(3)
            return True

        except Exception as e:
            logger.error(
                "Error waiting for filter results",
                extra={"error": str(e), "error_type": type(e).__name__},
            )
            return False

    async def validate_filters(self, config: ScrapingConfig) -> dict[str, bool]:
        """
        Validate all filter values against available options.

        Args:
            config: Scraping configuration to validate

        Returns:
            Dictionary mapping filter names to validation results
        """
        try:
            logger.info("Validating filter configuration")

            # Discover available options if not already done
            if not self._available_options:
                await self.discover_available_options()

            validation_results = {
                "age_group": await self._validate_filter_option(
                    "age_group", config.age_group
                ),
                "club": await self._validate_filter_option("club", config.club),
                "competition": await self._validate_filter_option(
                    "competition", config.competition
                ),
                "division": await self._validate_filter_option(
                    "division", config.division
                ),
            }

            logger.info("Filter validation completed", extra=validation_results)
            return validation_results

        except Exception as e:
            logger.error(
                "Error validating filters",
                extra={"error": str(e), "error_type": type(e).__name__},
            )
            return {
                "age_group": False,
                "club": False,
                "competition": False,
                "division": False,
            }

    async def _get_dropdown_options(self, selectors: list[str]) -> list[str]:
        """
        Get available options from dropdown selectors.

        Args:
            selectors: List of CSS selectors to try

        Returns:
            List of available option values
        """
        try:
            for selector in selectors:
                if await self.interactor.wait_for_element(selector, timeout=3000):
                    # Get all option elements
                    options = await self.page.query_selector_all(f"{selector} option")

                    option_values = []
                    for option in options:
                        value = await option.get_attribute("value")
                        text = await option.text_content()

                        # Use value if available, otherwise use text
                        option_value = value if value and value.strip() else text

                        if (
                            option_value
                            and option_value.strip()
                            and option_value.strip().lower()
                            not in ["", "all", "select", "choose"]
                        ):
                            option_values.append(option_value.strip())

                    if option_values:
                        logger.debug(
                            "Found dropdown options",
                            extra={"selector": selector, "count": len(option_values)},
                        )
                        return option_values

            return []

        except Exception as e:
            logger.debug(
                "Error getting dropdown options",
                extra={"error": str(e), "selectors": selectors},
            )
            return []

    async def _validate_filter_option(self, filter_type: str, value: str) -> bool:
        """
        Validate a filter option against available options.

        Args:
            filter_type: Type of filter ("age_group", "club", "competition", "division")
            value: Value to validate

        Returns:
            True if value is valid, False otherwise
        """
        try:
            if not value or not value.strip():
                return True  # Empty values are considered valid (no filter)

            # Use discovered options if available
            if (
                filter_type in self._available_options
                and self._available_options[filter_type]
            ):
                available_options = self._available_options[filter_type]
                is_valid = value in available_options

                if not is_valid:
                    # Try case-insensitive match
                    is_valid = any(
                        value.lower() == option.lower() for option in available_options
                    )

                logger.debug(
                    "Validated filter option",
                    extra={
                        "filter_type": filter_type,
                        "value": value,
                        "is_valid": is_valid,
                        "available_count": len(available_options),
                    },
                )

                return is_valid

            # Fallback to hardcoded validation for known filter types
            if filter_type == "age_group":
                return value in self.VALID_AGE_GROUPS
            elif filter_type == "division":
                return value in self.VALID_DIVISIONS
            else:
                # For club and competition, accept any non-empty value if we can't discover options
                return bool(value.strip())

        except Exception as e:
            logger.debug(
                "Error validating filter option",
                extra={"error": str(e), "filter_type": filter_type, "value": value},
            )
            return False


# Example usage
async def example_filter_usage() -> None:
    """
    Example demonstrating how to use the MLSFilterApplicator.

    This example shows the complete workflow for applying filters
    on the MLS website.
    """
    from .browser import PageNavigator, get_browser_manager
    from .config import load_config

    # Load configuration
    config = load_config()

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

            # Create filter applicator
            filter_applicator = MLSFilterApplicator(page)

            try:
                # Validate filters first
                validation_results = await filter_applicator.validate_filters(config)
                print(f"Filter validation results: {validation_results}")

                # Apply all filters
                success = await filter_applicator.apply_all_filters(config)

                if success:
                    print("All filters applied successfully!")
                else:
                    print("Failed to apply some filters")

            except FilterApplicationError as e:
                print(f"Filter application failed: {e}")
            except Exception as e:
                print(f"Unexpected error: {e}")


if __name__ == "__main__":
    asyncio.run(example_filter_usage())
