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
    Handles application of filters on the MLS website.

    Provides methods to apply age group, club, competition, and division filters
    with validation, error handling, and result loading verification.
    """

    # CSS selectors for MLS website filter elements
    AGE_GROUP_SELECTOR = (
        'select[name="age_group"], #age-group-select, .age-group-filter'
    )
    CLUB_SELECTOR = 'select[name="club"], #club-select, .club-filter'
    COMPETITION_SELECTOR = (
        'select[name="competition"], #competition-select, .competition-filter'
    )
    DIVISION_SELECTOR = 'select[name="division"], #division-select, .division-filter'

    # Alternative selectors for different page layouts
    FILTER_FORM_SELECTOR = ".filter-form, .search-form, .filters-container"
    RESULTS_CONTAINER_SELECTOR = (
        ".results-container, .matches-container, .schedule-results"
    )
    LOADING_INDICATOR_SELECTOR = ".loading, .spinner, .loading-indicator"

    # Valid filter options (these would typically be discovered dynamically)
    VALID_AGE_GROUPS = {"U13", "U14", "U15", "U16", "U17", "U18", "U19"}
    VALID_DIVISIONS = {
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

    async def discover_available_options(self) -> dict[str, set[str]]:
        """
        Discover available filter options from the website.

        Returns:
            Dictionary mapping filter names to sets of available options
        """
        try:
            logger.info("Discovering available filter options")

            options = {
                "age_group": set(),
                "club": set(),
                "competition": set(),
                "division": set(),
            }

            # Discover age group options
            age_group_options = await self._get_dropdown_options(
                [self.AGE_GROUP_SELECTOR, 'select[name*="age" i]', "#age-group"]
            )
            if age_group_options:
                options["age_group"] = set(age_group_options)
                logger.debug(
                    "Discovered age group options", extra={"options": age_group_options}
                )

            # Discover club options
            club_options = await self._get_dropdown_options(
                [self.CLUB_SELECTOR, 'select[name*="club" i]', "#club"]
            )
            if club_options:
                options["club"] = set(club_options)
                logger.debug(
                    "Discovered club options", extra={"count": len(club_options)}
                )

            # Discover competition options
            competition_options = await self._get_dropdown_options(
                [
                    self.COMPETITION_SELECTOR,
                    'select[name*="competition" i]',
                    "#competition",
                ]
            )
            if competition_options:
                options["competition"] = set(competition_options)
                logger.debug(
                    "Discovered competition options",
                    extra={"count": len(competition_options)},
                )

            # Discover division options
            division_options = await self._get_dropdown_options(
                [self.DIVISION_SELECTOR, 'select[name*="division" i]', "#division"]
            )
            if division_options:
                options["division"] = set(division_options)
                logger.debug(
                    "Discovered division options", extra={"options": division_options}
                )

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
        Apply age group filter.

        Args:
            age_group: Age group to filter by (e.g., "U14")

        Returns:
            True if filter applied successfully, False otherwise
        """
        try:
            logger.info("Applying age group filter", extra={"age_group": age_group})

            if not age_group:
                logger.debug("Empty age group provided, skipping filter")
                return True

            # Validate age group
            if not await self._validate_filter_option("age_group", age_group):
                logger.warning("Invalid age group", extra={"age_group": age_group})
                return False

            # Try multiple selectors for age group dropdown
            selectors = [
                self.AGE_GROUP_SELECTOR,
                'select[name*="age" i]',
                "#age-group",
                ".age-group-select",
                'select[id*="age" i]',
            ]

            for selector in selectors:
                logger.debug("Trying age group selector", extra={"selector": selector})

                if await self.interactor.wait_for_element(selector, timeout=3000):
                    if await self.interactor.select_dropdown_option(
                        selector, age_group
                    ):
                        logger.info(
                            "Age group filter applied",
                            extra={"selector": selector, "age_group": age_group},
                        )
                        return True

            logger.error(
                "Failed to apply age group filter - no working selectors found"
            )
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
        Apply division filter.

        Args:
            division: Division name to filter by

        Returns:
            True if filter applied successfully, False otherwise
        """
        try:
            logger.info("Applying division filter", extra={"division": division})

            if not division:
                logger.debug("Empty division provided, skipping filter")
                return True

            # Validate division option
            if not await self._validate_filter_option("division", division):
                logger.warning("Invalid division", extra={"division": division})
                return False

            # Try multiple selectors for division dropdown
            selectors = [
                self.DIVISION_SELECTOR,
                'select[name*="division" i]',
                "#division",
                ".division-select",
                'select[id*="division" i]',
            ]

            for selector in selectors:
                logger.debug("Trying division selector", extra={"selector": selector})

                if await self.interactor.wait_for_element(selector, timeout=3000):
                    if await self.interactor.select_dropdown_option(selector, division):
                        logger.info(
                            "Division filter applied",
                            extra={"selector": selector, "division": division},
                        )
                        return True

            logger.error("Failed to apply division filter - no working selectors found")
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

            # Discover available options first
            await self.discover_available_options()

            # Apply filters in order
            filters_applied = []

            # Apply age group filter
            if await self.apply_age_group_filter(config.age_group):
                filters_applied.append("age_group")
            else:
                logger.error("Failed to apply age group filter")
                return False

            # Small delay between filter applications
            await asyncio.sleep(0.5)

            # Apply club filter
            if await self.apply_club_filter(config.club):
                filters_applied.append("club")
            else:
                logger.error("Failed to apply club filter")
                return False

            await asyncio.sleep(0.5)

            # Apply competition filter
            if await self.apply_competition_filter(config.competition):
                filters_applied.append("competition")
            else:
                logger.error("Failed to apply competition filter")
                return False

            await asyncio.sleep(0.5)

            # Apply division filter
            if await self.apply_division_filter(config.division):
                filters_applied.append("division")
            else:
                logger.error("Failed to apply division filter")
                return False

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
