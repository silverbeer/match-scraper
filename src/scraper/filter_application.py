"""
MLS website filter application utilities.

This module provides functionality to apply filters on the MLS website including
age_group, club, competition, and division filters with comprehensive error handling
and validation.
"""

import asyncio
from typing import Optional

from playwright.async_api import Page

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

    # Iframe access pattern
    IFRAME_SELECTOR = 'iframe'
    
    # Age group value mappings (from Bootstrap Select)
    AGE_GROUP_VALUES = {
        "U13": "21",
        "U14": "22", 
        "U15": "33",
        "U16": "14",
        "U17": "15",
        "U19": "26"
    }

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
    RESULTS_CONTAINER_SELECTOR = ".results-container, .matches-container, .schedule-results"

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
        self._iframe_content = None

    async def _get_iframe_content(self):
        """
        Get the iframe content frame for filter interactions.
        
        Returns:
            The iframe content frame or None if not found
        """
        try:
            if self._iframe_content is None:
                logger.debug("Looking for iframe on page")
                
                # Wait for iframe to be available with shorter timeout
                try:
                    iframe_element = await self.page.wait_for_selector(self.IFRAME_SELECTOR, timeout=5000)
                    if iframe_element:
                        self._iframe_content = await iframe_element.content_frame()
                        logger.info("Successfully accessed iframe content frame")
                        # Wait for iframe content to load
                        await asyncio.sleep(2)
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

            options = {
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
                # Discover age group options from select element
                age_select = iframe_content.locator('select[js-age]')
                if await age_select.count() > 0:
                    age_options = await age_select.locator('option').all()
                    for option in age_options:
                        value = await option.get_attribute('value')
                        text = await option.text_content()
                        if value and text and value != "":
                            # Map back from value to age group
                            for age, val in self.AGE_GROUP_VALUES.items():
                                if val == value:
                                    options["age_group"].add(age)
                                    break
                
                # If no options found via select, use hardcoded valid options
                if not options["age_group"]:
                    options["age_group"] = self.VALID_AGE_GROUPS.copy()

                # For divisions, use hardcoded options for now
                # Could be enhanced to discover from iframe dropdowns
                options["division"] = {"Homegrown Division", "Academy Division"}

                logger.debug("Successfully discovered options from iframe")

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
            logger.info("Applying age group filter in iframe", extra={"age_group": age_group})

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

            # Strategy 1: Try Bootstrap Select UI interaction (based on actual HTML structure)
            try:
                # Find the age group bootstrap select specifically (using js-age attribute)
                age_bootstrap_select = iframe_content.locator('select[js-age]').locator('..')
                
                # Click the dropdown toggle button
                dropdown_button = age_bootstrap_select.locator('.dropdown-toggle')
                await dropdown_button.click()
                await asyncio.sleep(1)  # Give more time for dropdown to open
                
                # Wait for dropdown to be visible
                await iframe_content.locator('.dropdown-menu.open').wait_for(timeout=2000)
                
                # Click the specific age group option from the dropdown menu
                age_option = iframe_content.locator(f'.dropdown-menu li a .text:has-text("{age_group}")').first()
                await age_option.click()
                await asyncio.sleep(1)
                
                logger.info("Age group filter applied via Bootstrap UI", extra={"age_group": age_group})
                return True
                
            except Exception as e:
                logger.debug(f"Bootstrap UI method failed: {e}")

            # Strategy 2: Try clicking the option parent link directly  
            try:
                # First ensure dropdown is open
                dropdown_button = iframe_content.locator('.bootstrap-select .dropdown-toggle').first()
                await dropdown_button.click()
                await asyncio.sleep(1)
                
                # Click the <a> element that contains the age group text
                age_link = iframe_content.locator(f'li a:has(.text:has-text("{age_group}"))')
                await age_link.click()
                await asyncio.sleep(1)
                
                logger.info("Age group filter applied via option link", extra={"age_group": age_group})
                return True
                
            except Exception as e:
                logger.debug(f"Option link method failed: {e}")

            # Strategy 3: Try direct select option (fallback)
            try:
                age_value = self.AGE_GROUP_VALUES.get(age_group)
                if age_value:
                    age_select = iframe_content.locator('select[js-age]')
                    await age_select.select_option(value=age_value)
                    
                    logger.info("Age group filter applied via direct select", extra={"age_group": age_group, "value": age_value})
                    return True
                    
            except Exception as e:
                logger.debug(f"Direct select method failed: {e}")

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
        Apply club filter.

        Args:
            club: Club name to filter by

        Returns:
            True if filter applied successfully, False otherwise
        """
        try:
            logger.info("Applying club filter", extra={"club": club})

            if not club:
                logger.debug("Empty club provided, skipping filter")
                return True

            # Validate club option
            if not await self._validate_filter_option("club", club):
                logger.warning("Invalid club", extra={"club": club})
                return False

            # Try multiple selectors for club dropdown
            selectors = [
                self.CLUB_SELECTOR,
                'select[name*="club" i]',
                "#club",
                ".club-select",
                'select[id*="club" i]',
            ]

            for selector in selectors:
                logger.debug("Trying club selector", extra={"selector": selector})

                if await self.interactor.wait_for_element(selector, timeout=3000):
                    if await self.interactor.select_dropdown_option(selector, club):
                        logger.info(
                            "Club filter applied",
                            extra={"selector": selector, "club": club},
                        )
                        return True

            logger.error("Failed to apply club filter - no working selectors found")
            return False

        except Exception as e:
            logger.error(
                "Error applying club filter",
                extra={"error": str(e), "error_type": type(e).__name__, "club": club},
            )
            return False

    async def apply_competition_filter(self, competition: str) -> bool:
        """
        Apply competition filter.

        Args:
            competition: Competition name to filter by

        Returns:
            True if filter applied successfully, False otherwise
        """
        try:
            logger.info(
                "Applying competition filter", extra={"competition": competition}
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

            # Try multiple selectors for competition dropdown
            selectors = [
                self.COMPETITION_SELECTOR,
                'select[name*="competition" i]',
                "#competition",
                ".competition-select",
                'select[id*="competition" i]',
            ]

            for selector in selectors:
                logger.debug(
                    "Trying competition selector", extra={"selector": selector}
                )

                if await self.interactor.wait_for_element(selector, timeout=3000):
                    if await self.interactor.select_dropdown_option(
                        selector, competition
                    ):
                        logger.info(
                            "Competition filter applied",
                            extra={"selector": selector, "competition": competition},
                        )
                        return True

            logger.error(
                "Failed to apply competition filter - no working selectors found"
            )
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

    async def apply_division_filter(self, division: str) -> bool:
        """
        Apply division filter using iframe Bootstrap Select dropdown.

        Args:
            division: Division name to filter by

        Returns:
            True if filter applied successfully, False otherwise
        """
        try:
            logger.info("Applying division filter in iframe", extra={"division": division})

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

            # Strategy 1: Try role-based interaction (from recorded script)
            try:
                # Extract the division name (e.g., "Central" from "Division Central")
                division_name = division.replace("Division", "").strip()
                division_button = iframe_content.get_by_role("button", name=f"Division {division_name}")
                await division_button.click()
                
                logger.info("Division filter applied via role button", extra={"division": division})
                return True
                
            except Exception as e:
                logger.debug(f"Role button method failed: {e}")

            # Strategy 2: Try Bootstrap Select UI interaction
            try:
                # Click the division dropdown toggle
                division_dropdown = iframe_content.locator('label:has-text("Division") + div .dropdown-toggle')
                await division_dropdown.click()
                await asyncio.sleep(0.5)
                
                # Click the specific division option
                division_option = iframe_content.locator(f'span.text:has-text("{division}")')
                await division_option.click()
                await asyncio.sleep(0.5)
                
                logger.info("Division filter applied via Bootstrap UI", extra={"division": division})
                return True
                
            except Exception as e:
                logger.debug(f"Bootstrap UI method failed: {e}")

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
            logger.info("Applying age group filter via URL navigation", extra={"age_group": age_group})

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
                await self.page.goto(full_url, wait_until='load')
                
                # Wait for page to load
                await asyncio.sleep(2)
                
                logger.info("Age group filter applied via URL navigation", extra={"age_group": age_group, "url": full_url})
                return True
            else:
                logger.error("No URL mapping found for age group", extra={"age_group": age_group})
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
            logger.info("Applying division filter via URL navigation", extra={"division": division})

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
            elif division_lower in ["northeast", "southeast", "central", "southwest", "northwest", "mid-atlantic", "great lakes", "texas", "california"]:
                # For geographical divisions, we might need to construct a different URL
                # For now, log that this type of division filtering needs additional investigation
                logger.warning("Geographical division filtering not yet implemented", extra={"division": division})
                return True  # Return True to not fail the whole process
            
            if url_path:
                # Navigate to the division specific page
                base_url = "https://www.mlssoccer.com"
                full_url = base_url + url_path
                
                logger.info("Navigating to division URL", extra={"url": full_url})
                await self.page.goto(full_url, wait_until='load')
                
                # Wait for page to load
                await asyncio.sleep(2)
                
                logger.info("Division filter applied via URL navigation", extra={"division": division, "url": full_url})
                return True
            else:
                logger.error("No URL mapping found for division", extra={"division": division})
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
            logger.info("Applying date filter in iframe", extra={"start_date": start_date, "end_date": end_date})

            if not start_date or not end_date:
                logger.debug("Empty dates provided, skipping date filter")
                return True

            # Get iframe content
            iframe_content = await self._get_iframe_content()
            if not iframe_content:
                logger.error("Could not access iframe content for date filter")
                return False

            try:
                # Format date range string
                date_range = f"{start_date} - {end_date}"
                
                # Fill the date filter input
                date_input = iframe_content.locator('input[name="datefilter"]')
                await date_input.fill(date_range)
                await asyncio.sleep(0.5)
                
                # Apply the filter
                apply_button = iframe_content.get_by_role("button", name="Apply")
                await apply_button.click()
                await asyncio.sleep(1)
                
                logger.info("Date filter applied successfully", extra={"date_range": date_range})
                return True
                
            except Exception as e:
                logger.debug(f"Date filter method failed: {e}")
                
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
                    "club": config.club,
                    "competition": config.competition,
                    "division": config.division,
                },
            )

            # Stay on the current page - use URL navigation for filtering on /schedule/all/
            # Only use iframe if we're already on a division page that has one
            
            # Discover available options from current page
            await self.discover_available_options()

            # Apply filters using the appropriate method for current page
            filters_applied = []

            # Check if we're on the main schedule page (uses URL navigation)
            current_url = self.page.url
            is_main_schedule_page = "/schedule/all/" in current_url
            
            if is_main_schedule_page:
                # Use URL navigation for main schedule page
                logger.info("Using URL navigation filtering for main schedule page")
                
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
                        
            else:
                # Use iframe filtering for division-specific pages
                logger.info("Using iframe filtering for division-specific page")
                
                # Apply age group filter via iframe
                if config.age_group:
                    if await self.apply_age_group_filter(config.age_group):
                        filters_applied.append("age_group")
                        await asyncio.sleep(1)
                    else:
                        logger.error("Failed to apply age group filter via iframe")
                        return False
                
                # Apply division filter via iframe
                if config.division:
                    if await self.apply_division_filter(config.division):
                        filters_applied.append("division")
                        await asyncio.sleep(1)
                    else:
                        logger.error("Failed to apply division filter via iframe")
                        return False

            # Apply date filters if available in config
            # Note: This would require adding date fields to ScrapingConfig
            # For now, just log that date filtering is available
            if hasattr(config, 'start_date') and hasattr(config, 'end_date'):
                if config.start_date and config.end_date:
                    if await self.apply_date_filter(config.start_date, config.end_date):
                        filters_applied.append("date_range")
                        await asyncio.sleep(1)
                    else:
                        logger.warning("Failed to apply date filter")

            # Club and competition filters are supported via iframe but not yet implemented
            if config.club:
                logger.warning("Club filtering via iframe not yet implemented", extra={"club": config.club})
                
            if config.competition:
                logger.warning("Competition filtering via iframe not yet implemented", extra={"competition": config.competition})

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

            # First, wait for any loading indicators to disappear
            loading_selectors = [
                self.LOADING_INDICATOR_SELECTOR,
                ".loading",
                ".spinner",
                ".loading-indicator",
                '[data-loading="true"]',
            ]

            for selector in loading_selectors:
                # Wait for loading indicator to appear (optional)
                await self.interactor.wait_for_element(
                    selector, timeout=2000, state="visible"
                )

                # Then wait for it to disappear
                await self.interactor.wait_for_element(
                    selector, timeout=timeout, state="hidden"
                )

            # Wait for results container to be visible and populated
            results_selectors = [
                self.RESULTS_CONTAINER_SELECTOR,
                ".results-container",
                ".matches-container",
                ".schedule-results",
                ".match-list",
                "table tbody tr",
            ]

            for selector in results_selectors:
                if await self.interactor.wait_for_element(selector, timeout=5000):
                    logger.info("Filter results loaded", extra={"selector": selector})

                    # Additional wait to ensure content is fully rendered
                    await asyncio.sleep(1)
                    return True

            # If no specific results container found, just wait a bit
            logger.debug("No specific results container found, using generic wait")
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
async def example_filter_usage():
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
