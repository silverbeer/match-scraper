"""
Calendar widget interaction utilities for MLS website scraping.

This module provides functionality to interact with the MLS website's calendar widget,
including clicking the Match Date field, navigating the date picker, selecting dates,
and applying filters with comprehensive error handling.
"""

import asyncio
from datetime import date
from typing import Optional

from playwright.async_api import Frame, Page

from ..utils.logger import get_logger
from .browser import ElementInteractor

logger = get_logger()


class CalendarInteractionError(Exception):
    """Custom exception for calendar interaction failures."""

    pass


class MLSCalendarInteractor:
    """
    Handles interaction with the MLS website calendar widget.

    Provides methods to open the calendar, navigate to specific dates,
    select date ranges, and apply filters with robust error handling.
    """

    # CSS selectors for MLS website calendar elements (iframe-based)
    IFRAME_SELECTOR = 'main[role="main"] iframe, [aria-label*="main"] iframe, iframe[src*="modular11"]'
    MATCH_DATE_FIELD_SELECTOR = (
        'input[name="datefilter"]'  # Correct selector for MLS iframe
    )
    APPLY_BUTTON_SELECTOR = 'button.applyBtn, button:has-text("Apply"), .applyBtn'

    # Legacy selectors (keeping for fallback)
    LEGACY_MATCH_DATE_FIELD_SELECTOR = (
        'input[name="match_date"], #match-date-input, .date-picker-input'
    )
    CALENDAR_WIDGET_SELECTOR = ".calendar-widget, .date-picker, .datepicker"
    DATE_CELL_SELECTOR = ".calendar-day, .datepicker-day, td[data-date]"
    CALENDAR_MONTH_SELECTOR = ".calendar-month, .datepicker-month"
    CALENDAR_YEAR_SELECTOR = ".calendar-year, .datepicker-year"
    NEXT_MONTH_BUTTON_SELECTOR = ".next-month, .datepicker-next"
    PREV_MONTH_BUTTON_SELECTOR = ".prev-month, .datepicker-prev"

    def __init__(self, page: Page, timeout: int = 15000):
        """
        Initialize calendar interactor.

        Args:
            page: Playwright page instance
            timeout: Default timeout for operations in milliseconds
        """
        self.page = page
        self.timeout = timeout
        self.interactor = ElementInteractor(page, timeout)
        self.iframe_content: Optional[Frame] = None

    async def open_calendar_widget(self) -> bool:
        """
        Open the calendar widget by clicking the Match Date field.

        Returns:
            True if calendar opened successfully, False otherwise
        """
        try:
            logger.info("Opening calendar widget")

            # Try multiple possible selectors for the date field
            selectors = [
                'input[name="match_date"]',
                "#match-date-input",
                ".date-picker-input",
                'input[placeholder*="date" i]',
                'input[type="date"]',
                '.form-control[name*="date" i]',
            ]

            for selector in selectors:
                logger.debug("Trying date field selector", extra={"selector": selector})

                if await self.interactor.wait_for_element(selector, timeout=3000):
                    if await self.interactor.click_element(selector):
                        logger.info("Clicked date field", extra={"selector": selector})

                        # Wait for calendar widget to appear
                        calendar_selectors = [
                            ".calendar-widget",
                            ".date-picker",
                            ".datepicker",
                            ".ui-datepicker",
                            '[role="dialog"]',
                        ]

                        for cal_selector in calendar_selectors:
                            if await self.interactor.wait_for_element(
                                cal_selector, timeout=3000
                            ):
                                logger.info(
                                    "Calendar widget opened",
                                    extra={
                                        "date_field_selector": selector,
                                        "calendar_selector": cal_selector,
                                    },
                                )
                                return True

                        # If no calendar appeared, try next selector
                        logger.debug(
                            "No calendar appeared after clicking",
                            extra={"selector": selector},
                        )
                        continue

            logger.error("Failed to open calendar widget - no working selectors found")
            return False

        except Exception as e:
            logger.error(
                "Error opening calendar widget",
                extra={"error": str(e), "error_type": type(e).__name__},
            )
            return False

    async def navigate_to_month_year(self, target_date: date) -> bool:
        """
        Navigate the calendar to the specified month and year.

        Args:
            target_date: Date to navigate to (only month/year used)

        Returns:
            True if navigation successful, False otherwise
        """
        try:
            logger.info(
                "Navigating to month/year",
                extra={
                    "target_month": target_date.month,
                    "target_year": target_date.year,
                },
            )

            # Get current month/year from calendar
            current_month, current_year = await self._get_current_month_year()
            if current_month is None or current_year is None:
                logger.error("Could not determine current calendar month/year")
                return False

            target_month = target_date.month
            target_year = target_date.year

            logger.debug(
                "Calendar navigation",
                extra={
                    "current_month": current_month,
                    "current_year": current_year,
                    "target_month": target_month,
                    "target_year": target_year,
                },
            )

            # Navigate to target year first
            if not await self._navigate_to_year(current_year, target_year):
                return False

            # Then navigate to target month
            if not await self._navigate_to_month(current_month, target_month):
                return False

            logger.info("Successfully navigated to target month/year")
            return True

        except Exception as e:
            logger.error(
                "Error navigating to month/year",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "target_date": str(target_date),
                },
            )
            return False

    async def select_date(self, target_date: date) -> bool:
        """
        Select a specific date in the calendar.

        Args:
            target_date: Date to select

        Returns:
            True if date selected successfully, False otherwise
        """
        try:
            logger.info("Selecting date", extra={"target_date": str(target_date)})

            # First navigate to the correct month/year
            if not await self.navigate_to_month_year(target_date):
                logger.error("Failed to navigate to target month/year")
                return False

            # Try different approaches to select the date
            day = target_date.day

            # Approach 1: Look for data-date attribute
            date_str = target_date.strftime("%Y-%m-%d")
            selector = f'[data-date="{date_str}"], [data-date="{target_date.strftime("%m/%d/%Y")}"]'

            if await self.interactor.wait_for_element(selector, timeout=3000):
                if await self.interactor.click_element(selector):
                    logger.info(
                        "Selected date using data-date attribute",
                        extra={"selector": selector, "date": str(target_date)},
                    )
                    return True

            # Approach 2: Look for day number in calendar cells
            day_selectors = [
                f'.calendar-day:has-text("{day}")',
                f'.datepicker-day:has-text("{day}")',
                f'td:has-text("{day}"):not(.other-month)',
                f'.day:has-text("{day}")',
                f'[data-day="{day}"]',
            ]

            for selector in day_selectors:
                logger.debug("Trying day selector", extra={"selector": selector})

                if await self.interactor.wait_for_element(selector, timeout=3000):
                    if await self.interactor.click_element(selector):
                        logger.info(
                            "Selected date using day selector",
                            extra={"selector": selector, "date": str(target_date)},
                        )
                        return True

            # Approach 3: Try to find clickable elements with the day number
            try:
                # Get all elements that might be calendar days
                elements = await self.page.query_selector_all(
                    "td, .day, .calendar-day, .datepicker-day"
                )

                for element in elements:
                    text = await element.text_content()
                    if text and text.strip() == str(day):
                        # Check if this element is clickable and in current month
                        is_clickable = await element.is_enabled()
                        classes = await element.get_attribute("class") or ""

                        # Skip if it's marked as other month or disabled
                        if "other-month" in classes or "disabled" in classes:
                            continue

                        if is_clickable:
                            await element.click()
                            logger.info(
                                "Selected date by finding day element",
                                extra={
                                    "date": str(target_date),
                                    "element_text": text.strip(),
                                },
                            )
                            return True

            except Exception as e:
                logger.debug(
                    "Error in element-by-element approach", extra={"error": str(e)}
                )

            logger.error(
                "Failed to select date - no working approach found",
                extra={"target_date": str(target_date)},
            )
            return False

        except Exception as e:
            logger.error(
                "Error selecting date",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "target_date": str(target_date),
                },
            )
            return False

    async def select_date_range(self, start_date: date, end_date: date) -> bool:
        """
        Select a date range in the calendar.

        Args:
            start_date: Start date of the range
            end_date: End date of the range

        Returns:
            True if date range selected successfully, False otherwise
        """
        try:
            logger.info(
                "Selecting date range",
                extra={"start_date": str(start_date), "end_date": str(end_date)},
            )

            # Select start date first
            if not await self.select_date(start_date):
                logger.error("Failed to select start date")
                return False

            # Small delay to allow UI to update
            await asyncio.sleep(0.5)

            # Select end date
            if not await self.select_date(end_date):
                logger.error("Failed to select end date")
                return False

            logger.info("Successfully selected date range")
            return True

        except Exception as e:
            logger.error(
                "Error selecting date range",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "start_date": str(start_date),
                    "end_date": str(end_date),
                },
            )
            return False

    async def apply_date_filter(self) -> bool:
        """
        Apply the selected date filter by clicking the Apply button.

        Returns:
            True if filter applied successfully, False otherwise
        """
        try:
            logger.info("Applying date filter")

            # Try multiple possible selectors for the apply button
            apply_selectors = [
                'button[type="submit"]',
                ".apply-button",
                ".filter-apply",
                'button:has-text("Apply")',
                'input[type="submit"]',
                ".btn-primary",
                ".submit-btn",
            ]

            for selector in apply_selectors:
                logger.debug(
                    "Trying apply button selector", extra={"selector": selector}
                )

                if await self.interactor.wait_for_element(selector, timeout=3000):
                    if await self.interactor.click_element(selector):
                        logger.info(
                            "Clicked apply button", extra={"selector": selector}
                        )

                        # Wait for page to update after applying filter
                        await asyncio.sleep(2)

                        # Verify that calendar closed (optional)
                        calendar_closed = not await self.interactor.wait_for_element(
                            self.CALENDAR_WIDGET_SELECTOR, timeout=2000
                        )

                        if calendar_closed:
                            logger.info("Calendar closed after applying filter")

                        return True

            logger.error("Failed to find and click apply button")
            return False

        except Exception as e:
            logger.error(
                "Error applying date filter",
                extra={"error": str(e), "error_type": type(e).__name__},
            )
            return False

    async def set_date_range_filter(self, start_date: date, end_date: date) -> bool:
        """
        Complete workflow to set a date range filter using iframe direct input method.

        This method uses our working approach:
        1. Access iframe content
        2. Input date range directly to datefilter field
        3. Apply filter

        Args:
            start_date: Start date of the range
            end_date: End date of the range

        Returns:
            True if entire workflow completed successfully, False otherwise
        """
        try:
            logger.info(
                "Setting date range filter",
                extra={"start_date": str(start_date), "end_date": str(end_date)},
            )

            # Step 1: Access iframe content
            if not await self._access_iframe_content():
                raise CalendarInteractionError("Failed to access iframe content")

            # Step 2: Set date range using direct input method
            if not await self._set_date_range_direct_input(start_date, end_date):
                raise CalendarInteractionError("Failed to set date range")

            logger.info("Successfully set date range filter")
            return True

        except CalendarInteractionError:
            # Re-raise our custom exceptions
            raise
        except Exception as e:
            logger.error(
                "Error in date range filter workflow",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "start_date": str(start_date),
                    "end_date": str(end_date),
                },
            )
            raise CalendarInteractionError(
                f"Date range filter workflow failed: {e}"
            ) from e

    async def _access_iframe_content(self) -> bool:
        """
        Access the iframe content where date filter is located.

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

    async def _set_date_range_direct_input(
        self, start_date: date, end_date: date
    ) -> bool:
        """
        Set date range using date field interaction and calendar picker.

        Args:
            start_date: Start date of the range
            end_date: End date of the range

        Returns:
            True if date range set successfully, False otherwise
        """
        try:
            if not self.iframe_content:
                logger.debug("No iframe content available")
                return False

            # Format dates in the expected format: MM/DD/YYYY HH:MM AM/PM
            start_formatted = f"{start_date.strftime('%m/%d/%Y')} 12:00 AM"
            end_formatted = f"{end_date.strftime('%m/%d/%Y')} 11:59 PM"
            date_range_text = f"{start_formatted} – {end_formatted}"

            logger.info(f"Setting date range: {date_range_text}")

            # Find and click the date field to open calendar picker
            date_field = self.iframe_content.locator(self.MATCH_DATE_FIELD_SELECTOR)
            if await date_field.count() > 0:
                await date_field.click()
                logger.debug("Clicked date field to open calendar")
                await asyncio.sleep(2)  # Wait for calendar to open

                # Check if calendar picker appeared
                calendar_picker = self.iframe_content.locator(".daterangepicker")
                if await calendar_picker.count() > 0:
                    logger.info("Calendar picker opened successfully")

                    # Navigate to start_date's month if needed
                    if not await self._navigate_daterangepicker_to_month(
                        start_date.month, start_date.year
                    ):
                        logger.warning(
                            "Failed to navigate to start date month",
                            extra={
                                "target_month": start_date.month,
                                "target_year": start_date.year,
                            },
                        )
                        return False

                    # Click on start date - use left calendar only
                    start_day = start_date.day  # Use actual start date
                    start_date_selectors = [
                        f'.daterangepicker .drp-calendar.left td:has-text("{start_day}"):not(.off)',
                        f'.drp-calendar.left .calendar-table td:has-text("{start_day}"):not(.off)',
                        f'.daterangepicker .left td:has-text("{start_day}"):not(.off)',
                    ]

                    start_clicked = False
                    for start_selector in start_date_selectors:
                        start_cell = self.iframe_content.locator(start_selector)
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

                    # Determine if end date is in the same month as start date
                    same_month = (
                        start_date.month == end_date.month
                        and start_date.year == end_date.year
                    )

                    if same_month:
                        # Same month: Select end date from left calendar
                        logger.debug(
                            "Start and end dates in same month - selecting end date from left calendar"
                        )
                        end_day = end_date.day
                        end_date_selectors = [
                            f'.daterangepicker .drp-calendar.left td:has-text("{end_day}"):not(.off)',
                            f'.drp-calendar.left .calendar-table td:has-text("{end_day}"):not(.off)',
                            f'.daterangepicker .left td:has-text("{end_day}"):not(.off)',
                        ]

                        end_clicked = False
                        for end_selector in end_date_selectors:
                            end_cell = self.iframe_content.locator(end_selector)
                            if await end_cell.count() > 0:
                                await end_cell.first.click()
                                logger.info(
                                    f"Clicked end date {end_day} on left calendar using selector: {end_selector}"
                                )
                                await asyncio.sleep(1)
                                end_clicked = True
                                break

                        if not end_clicked:
                            logger.warning(
                                f"Could not click end date {end_day} on left calendar"
                            )
                            return False
                    else:
                        # Different months: Navigate to end month (left calendar will update)
                        # then select end date from left calendar
                        logger.debug(
                            "Start and end dates in different months - navigating to end month"
                        )
                        if not await self._navigate_daterangepicker_to_month(
                            end_date.month, end_date.year
                        ):
                            logger.warning(
                                "Failed to navigate to end date month",
                                extra={
                                    "target_month": end_date.month,
                                    "target_year": end_date.year,
                                },
                            )
                            return False

                        end_day = end_date.day
                        end_date_selectors = [
                            f'.daterangepicker .drp-calendar.left td:has-text("{end_day}"):not(.off)',
                            f'.drp-calendar.left .calendar-table td:has-text("{end_day}"):not(.off)',
                            f'.daterangepicker .left td:has-text("{end_day}"):not(.off)',
                        ]

                        end_clicked = False
                        for end_selector in end_date_selectors:
                            end_cell = self.iframe_content.locator(end_selector)
                            if await end_cell.count() > 0:
                                await end_cell.first.click()
                                logger.info(
                                    f"Clicked end date {end_day} on left calendar using selector: {end_selector}"
                                )
                                await asyncio.sleep(1)
                                end_clicked = True
                                break

                        if not end_clicked:
                            logger.warning(
                                f"Could not click end date {end_day} on left calendar"
                            )
                            return False

                    # Click Apply button
                    apply_selectors = [
                        ".daterangepicker button.applyBtn",
                        ".daterangepicker .applyBtn",
                        "button.applyBtn",
                        ".applyBtn",
                    ]

                    apply_clicked = False
                    for apply_selector in apply_selectors:
                        apply_button = self.iframe_content.locator(apply_selector)
                        if await apply_button.count() > 0:
                            await apply_button.click()
                            logger.info(f"Clicked Apply button: {apply_selector}")
                            await asyncio.sleep(3)  # Wait for results to load
                            apply_clicked = True
                            break

                    if apply_clicked:
                        logger.info(
                            "Date filter applied via calendar date picker",
                            extra={
                                "start_date": str(start_date),
                                "end_date": str(end_date),
                            },
                        )
                        return True
                    else:
                        logger.warning("Apply button not found in calendar picker")
                        return False
                else:
                    # Fallback: try direct input without calendar picker
                    logger.debug("Calendar picker not found, trying direct input")
                    await date_field.press("Control+a")
                    await date_field.press("Delete")
                    await asyncio.sleep(0.5)

                    await date_field.type(date_range_text, delay=50)
                    logger.info(f"Typed date range (fallback): {date_range_text}")
                    await asyncio.sleep(1)

                    await date_field.press("Enter")
                    await asyncio.sleep(2)

                    logger.info(
                        "Date filter applied via direct input fallback",
                        extra={"date_range": date_range_text},
                    )
                    return True
            else:
                logger.warning("Date field not found")
                return False

        except Exception as e:
            logger.error(
                "Error setting date range",
                extra={
                    "error": str(e),
                    "start_date": str(start_date),
                    "end_date": str(end_date),
                },
            )
            return False

    async def _get_current_month_year(self) -> tuple[Optional[int], Optional[int]]:
        """
        Get the current month and year displayed in the calendar.

        Returns:
            Tuple of (month, year) or (None, None) if not found
        """
        try:
            # Try different selectors for month/year display
            month_year_selectors = [
                ".calendar-month-year",
                ".datepicker-month-year",
                ".calendar-header",
                ".month-year-display",
            ]

            for selector in month_year_selectors:
                text = await self.interactor.get_text_content(selector)
                if text:
                    # Try to parse month/year from text
                    month, year = self._parse_month_year_text(text)
                    if month and year:
                        return month, year

            # Try separate month and year selectors
            month_text = await self.interactor.get_text_content(
                ".calendar-month, .datepicker-month"
            )
            year_text = await self.interactor.get_text_content(
                ".calendar-year, .datepicker-year"
            )

            if month_text and year_text:
                month = self._parse_month_name(month_text.strip())
                try:
                    year = int(year_text.strip())
                    if month:
                        return month, year
                except ValueError:
                    pass

            return None, None

        except Exception as e:
            logger.debug("Error getting current month/year", extra={"error": str(e)})
            return None, None

    async def _get_daterangepicker_current_month_year(
        self,
    ) -> tuple[Optional[int], Optional[int]]:
        """
        Get the current month and year displayed in the daterangepicker left calendar.

        This is specifically for the daterangepicker widget that appears when clicking
        the date field in the iframe. It reads the month/year from the left calendar panel.

        Returns:
            Tuple of (month, year) or (None, None) if not found
        """
        try:
            if not self.iframe_content:
                logger.debug("No iframe content available for daterangepicker")
                return None, None

            # Selectors for daterangepicker month/year display
            # The daterangepicker shows month in format "Oct 2025" in the calendar header
            month_year_selectors = [
                ".daterangepicker .drp-calendar.left .month",
                ".daterangepicker .drp-calendar.left th.month",
                ".drp-calendar.left .calendar-table th.month",
            ]

            for selector in month_year_selectors:
                month_element = self.iframe_content.locator(selector)
                if await month_element.count() > 0:
                    text = await month_element.first.text_content()
                    if text:
                        logger.debug(
                            "Found daterangepicker month/year text",
                            extra={"text": text.strip(), "selector": selector},
                        )
                        # Parse the text using existing helper
                        month, year = self._parse_month_year_text(text.strip())
                        if month and year:
                            logger.debug(
                                "Parsed daterangepicker month/year",
                                extra={"month": month, "year": year},
                            )
                            return month, year

            logger.debug("Could not find daterangepicker month/year display")
            return None, None

        except Exception as e:
            logger.debug(
                "Error getting daterangepicker current month/year",
                extra={"error": str(e)},
            )
            return None, None

    async def _navigate_daterangepicker_to_month(
        self, target_month: int, target_year: int
    ) -> bool:
        """
        Navigate the daterangepicker to the specified month and year.

        This method clicks the prev/next month arrows in the daterangepicker
        until the left calendar shows the target month and year.

        Args:
            target_month: Target month (1-12)
            target_year: Target year (e.g., 2025)

        Returns:
            True if navigation successful, False otherwise
        """
        try:
            if not self.iframe_content:
                logger.debug(
                    "No iframe content available for daterangepicker navigation"
                )
                return False

            # Get current displayed month/year
            (
                current_month,
                current_year,
            ) = await self._get_daterangepicker_current_month_year()
            if current_month is None or current_year is None:
                logger.warning("Could not get current daterangepicker month/year")
                return False

            logger.info(
                "Navigating daterangepicker",
                extra={
                    "current_month": current_month,
                    "current_year": current_year,
                    "target_month": target_month,
                    "target_year": target_year,
                },
            )

            # Calculate how many months to navigate (forward or backward)
            current_total_months = current_year * 12 + current_month
            target_total_months = target_year * 12 + target_month
            months_diff = target_total_months - current_total_months

            if months_diff == 0:
                logger.debug("Already on target month/year")
                return True

            is_forward = months_diff > 0
            iterations = abs(months_diff)

            # Limit iterations to prevent infinite loops
            max_iterations = min(iterations, 24)  # Max 2 years navigation

            # Selectors for daterangepicker navigation buttons
            prev_selector = ".daterangepicker .drp-calendar.left .prev"
            next_selector = ".daterangepicker .drp-calendar.left .next"

            for i in range(max_iterations):
                if is_forward:
                    # Click next month button
                    next_button = self.iframe_content.locator(next_selector)
                    if await next_button.count() > 0:
                        await next_button.first.click()
                        logger.debug(f"Clicked next month button (iteration {i + 1})")
                    else:
                        logger.warning("Next month button not found")
                        return False
                else:
                    # Click previous month button
                    prev_button = self.iframe_content.locator(prev_selector)
                    if await prev_button.count() > 0:
                        await prev_button.first.click()
                        logger.debug(f"Clicked prev month button (iteration {i + 1})")
                    else:
                        logger.warning("Prev month button not found")
                        return False

                # Wait for UI to update (reduced from 0.5s to 0.3s for faster navigation)
                await asyncio.sleep(0.3)

                # Check if we've reached the target month/year
                (
                    updated_month,
                    updated_year,
                ) = await self._get_daterangepicker_current_month_year()
                if updated_month == target_month and updated_year == target_year:
                    logger.info(
                        "Successfully navigated to target month/year",
                        extra={"month": target_month, "year": target_year},
                    )
                    return True

            logger.warning(
                "Failed to reach target month after max iterations",
                extra={
                    "max_iterations": max_iterations,
                    "target_month": target_month,
                    "target_year": target_year,
                },
            )
            return False

        except Exception as e:
            logger.error(
                "Error navigating daterangepicker to month",
                extra={
                    "error": str(e),
                    "target_month": target_month,
                    "target_year": target_year,
                },
            )
            return False

    def _parse_month_year_text(self, text: str) -> tuple[Optional[int], Optional[int]]:
        """
        Parse month and year from calendar header text.

        Args:
            text: Calendar header text (e.g., "January 2024", "Jan 2024")

        Returns:
            Tuple of (month, year) or (None, None) if parsing fails
        """
        logger.debug("Parsing month/year text", extra={"text": text})
        try:
            import re

            # Common patterns for month/year display
            patterns = [
                r"(\w+)\s*,?\s*(\d{4})",  # "January 2024" or "January, 2024"
                r"(\d{1,2})/(\d{4})",  # "01/2024"
                r"(\d{4})-(\d{1,2})",  # "2024-01"
            ]

            for i, pattern in enumerate(patterns):
                match = re.search(pattern, text)
                if match:
                    group1, group2 = match.groups()

                    # Handle different patterns
                    if i == 2:  # "2024-01" pattern - year first, then month
                        year_str, month_str = group1, group2
                    else:  # Other patterns - month first, then year
                        month_str, year_str = group1, group2

                    # Try to parse month
                    month: Optional[int]
                    try:
                        month = int(month_str)
                    except ValueError:
                        month = self._parse_month_name(month_str)

                    try:
                        year = int(year_str)
                        if month and 1 <= month <= 12:
                            return month, year
                    except ValueError:
                        pass

            return None, None

        except Exception:
            return None, None

    def _parse_month_name(self, month_str: str) -> Optional[int]:
        """
        Parse month name to month number.

        Args:
            month_str: Month name (e.g., "January", "Jan")

        Returns:
            Month number (1-12) or None if parsing fails
        """
        month_names = {
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
            "sept": 9,
            "october": 10,
            "oct": 10,
            "november": 11,
            "nov": 11,
            "december": 12,
            "dec": 12,
        }

        return month_names.get(month_str.lower().strip())

    async def _navigate_to_year(self, current_year: int, target_year: int) -> bool:
        """
        Navigate to target year using navigation buttons.

        Args:
            current_year: Current year displayed
            target_year: Target year to navigate to

        Returns:
            True if navigation successful, False otherwise
        """
        if current_year == target_year:
            return True

        try:
            # Determine direction and number of years to navigate
            years_diff = target_year - current_year
            is_forward = years_diff > 0

            # Limit navigation to prevent infinite loops
            max_iterations = min(abs(years_diff), 10)

            for _ in range(max_iterations):
                if is_forward:
                    # Navigate forward (next year)
                    if not await self._click_next_year():
                        return False
                else:
                    # Navigate backward (previous year)
                    if not await self._click_prev_year():
                        return False

                # Check if we've reached the target year
                _, updated_year = await self._get_current_month_year()
                if updated_year == target_year:
                    return True

                # Small delay between clicks
                await asyncio.sleep(0.3)

            return False

        except Exception as e:
            logger.debug(
                "Error navigating to year",
                extra={
                    "error": str(e),
                    "current_year": current_year,
                    "target_year": target_year,
                },
            )
            return False

    async def _navigate_to_month(self, current_month: int, target_month: int) -> bool:
        """
        Navigate to target month using navigation buttons.

        Args:
            current_month: Current month displayed
            target_month: Target month to navigate to

        Returns:
            True if navigation successful, False otherwise
        """
        if current_month == target_month:
            return True

        try:
            # Calculate shortest path (considering year wrap-around)
            months_diff = target_month - current_month

            # If difference is more than 6 months, go the other way
            if months_diff > 6:
                months_diff -= 12
            elif months_diff < -6:
                months_diff += 12

            is_forward = months_diff > 0
            iterations = abs(months_diff)

            # Limit iterations to prevent infinite loops
            max_iterations = min(iterations, 12)

            for _ in range(max_iterations):
                if is_forward:
                    # Navigate forward (next month)
                    if not await self._click_next_month():
                        return False
                else:
                    # Navigate backward (previous month)
                    if not await self._click_prev_month():
                        return False

                # Check if we've reached the target month
                updated_month, _ = await self._get_current_month_year()
                if updated_month == target_month:
                    return True

                # Small delay between clicks
                await asyncio.sleep(0.3)

            return False

        except Exception as e:
            logger.debug(
                "Error navigating to month",
                extra={
                    "error": str(e),
                    "current_month": current_month,
                    "target_month": target_month,
                },
            )
            return False

    async def _click_next_month(self) -> bool:
        """Click next month navigation button."""
        selectors = [
            ".next-month",
            ".datepicker-next",
            ".calendar-next",
            'button[title*="next" i]',
            ".nav-next",
        ]

        for selector in selectors:
            if await self.interactor.click_element(selector):
                return True

        return False

    async def _click_prev_month(self) -> bool:
        """Click previous month navigation button."""
        selectors = [
            ".prev-month",
            ".datepicker-prev",
            ".calendar-prev",
            'button[title*="prev" i]',
            ".nav-prev",
        ]

        for selector in selectors:
            if await self.interactor.click_element(selector):
                return True

        return False

    async def _click_next_year(self) -> bool:
        """Click next year navigation button."""
        selectors = [".next-year", ".year-next", 'button[title*="next year" i]']

        for selector in selectors:
            if await self.interactor.click_element(selector):
                return True

        # If no year-specific button, simulate by clicking next month 12 times
        for _ in range(12):
            if not await self._click_next_month():
                return False
            await asyncio.sleep(0.1)  # Small delay between clicks

        return True

    async def _click_prev_year(self) -> bool:
        """Click previous year navigation button."""
        selectors = [".prev-year", ".year-prev", 'button[title*="prev year" i]']

        for selector in selectors:
            if await self.interactor.click_element(selector):
                return True

        # If no year-specific button, simulate by clicking prev month 12 times
        for _ in range(12):
            if not await self._click_prev_month():
                return False
            await asyncio.sleep(0.1)  # Small delay between clicks

        return True


# Example usage
async def example_calendar_usage() -> None:
    """
    Example demonstrating how to use the MLSCalendarInteractor.

    This example shows the complete workflow for setting up date filters
    on the MLS website calendar widget.
    """
    from datetime import date, timedelta

    from .browser import PageNavigator, get_browser_manager

    # Calculate date range (e.g., last 7 days)
    end_date = date.today()
    start_date = end_date - timedelta(days=7)

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

            # Create calendar interactor
            calendar = MLSCalendarInteractor(page)

            try:
                # Set date range filter
                await calendar.set_date_range_filter(start_date, end_date)
                print(f"Successfully set date filter: {start_date} to {end_date}")

                # Wait for results to load
                import asyncio

                await asyncio.sleep(3)

                print("Date filter applied successfully!")

            except CalendarInteractionError as e:
                print(f"Calendar interaction failed: {e}")
            except Exception as e:
                print(f"Unexpected error: {e}")


if __name__ == "__main__":
    asyncio.run(example_calendar_usage())
