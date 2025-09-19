"""Date handling and calculation utilities for MLS Match Scraper.

Provides functions for calculating date ranges, validating dates, and formatting
dates for web form inputs with proper edge case handling.
"""

import calendar
from datetime import date, datetime, timedelta
from typing import Optional


def calculate_date_range(
    look_back_days: int, reference_date: Optional[date] = None
) -> tuple[date, date]:
    """Calculate start and end dates based on look_back_days.

    Args:
        look_back_days: Number of days to look back from reference date
        reference_date: Reference date to calculate from (defaults to today)

    Returns:
        Tuple of (start_date, end_date)

    Raises:
        ValueError: If look_back_days is negative
    """
    if look_back_days < 0:
        raise ValueError("look_back_days must be non-negative")

    if reference_date is None:
        reference_date = date.today()

    end_date = reference_date
    start_date = end_date - timedelta(days=look_back_days)

    return start_date, end_date


def validate_date_range(start_date: date, end_date: date) -> None:
    """Validate that date range is logical.

    Args:
        start_date: Start date of the range
        end_date: End date of the range

    Raises:
        ValueError: If start_date is after end_date
    """
    if start_date > end_date:
        raise ValueError(
            f"start_date ({start_date}) cannot be after end_date ({end_date})"
        )


def is_weekend(target_date: date) -> bool:
    """Check if a date falls on a weekend.

    Args:
        target_date: Date to check

    Returns:
        True if date is Saturday or Sunday, False otherwise
    """
    return target_date.weekday() >= 5  # Saturday = 5, Sunday = 6


def is_holiday(target_date: date) -> bool:
    """Check if a date is a common US holiday that might affect match scheduling.

    Note: This is a simplified implementation focusing on major holidays.
    For production use, consider using a more comprehensive holiday library.

    Args:
        target_date: Date to check

    Returns:
        True if date is a recognized holiday, False otherwise
    """
    year = target_date.year

    # Fixed date holidays
    fixed_holidays = [
        date(year, 1, 1),  # New Year's Day
        date(year, 7, 4),  # Independence Day
        date(year, 12, 25),  # Christmas Day
    ]

    if target_date in fixed_holidays:
        return True

    # Memorial Day (last Monday in May)
    memorial_day = _get_last_monday_of_month(year, 5)
    if target_date == memorial_day:
        return True

    # Labor Day (first Monday in September)
    labor_day = _get_first_monday_of_month(year, 9)
    if target_date == labor_day:
        return True

    # Thanksgiving (fourth Thursday in November)
    thanksgiving = _get_nth_weekday_of_month(
        year, 11, 3, 4
    )  # 3 = Thursday, 4th occurrence
    if target_date == thanksgiving:
        return True

    return False


def _get_last_monday_of_month(year: int, month: int) -> date:
    """Get the last Monday of a given month and year."""
    # Get the last day of the month
    last_day = calendar.monthrange(year, month)[1]
    last_date = date(year, month, last_day)

    # Find the last Monday
    days_back = (last_date.weekday() - 0) % 7  # 0 = Monday
    return last_date - timedelta(days=days_back)


def _get_first_monday_of_month(year: int, month: int) -> date:
    """Get the first Monday of a given month and year."""
    first_date = date(year, month, 1)
    days_forward = (0 - first_date.weekday()) % 7  # 0 = Monday
    return first_date + timedelta(days=days_forward)


def _get_nth_weekday_of_month(
    year: int, month: int, weekday: int, occurrence: int
) -> date:
    """Get the nth occurrence of a weekday in a month.

    Args:
        year: Year
        month: Month (1-12)
        weekday: Weekday (0=Monday, 1=Tuesday, ..., 6=Sunday)
        occurrence: Which occurrence (1=first, 2=second, etc.)
    """
    first_date = date(year, month, 1)
    first_weekday = first_date.weekday()

    # Calculate days to the first occurrence of the target weekday
    days_to_first = (weekday - first_weekday) % 7
    first_occurrence = first_date + timedelta(days=days_to_first)

    # Calculate the nth occurrence
    target_date = first_occurrence + timedelta(weeks=occurrence - 1)

    # Ensure we're still in the same month
    if target_date.month != month:
        raise ValueError(
            f"No {occurrence}th occurrence of weekday {weekday} in {year}-{month}"
        )

    return target_date


def adjust_for_weekends_and_holidays(
    target_date: date, direction: str = "forward"
) -> date:
    """Adjust a date to avoid weekends and holidays.

    Args:
        target_date: Date to adjust
        direction: Direction to adjust ("forward" or "backward")

    Returns:
        Adjusted date that avoids weekends and holidays

    Raises:
        ValueError: If direction is not "forward" or "backward"
    """
    if direction not in ("forward", "backward"):
        raise ValueError("direction must be 'forward' or 'backward'")

    adjusted_date = target_date
    delta = timedelta(days=1) if direction == "forward" else timedelta(days=-1)

    # Keep adjusting until we find a valid date (max 14 days to prevent infinite loops)
    for _ in range(14):
        if not is_weekend(adjusted_date) and not is_holiday(adjusted_date):
            return adjusted_date
        adjusted_date += delta

    # If we can't find a valid date within 14 days, return the original
    return target_date


def format_date_for_web_form(target_date: date, format_type: str = "mm/dd/yyyy") -> str:
    """Format a date for web form input.

    Args:
        target_date: Date to format
        format_type: Format type ("mm/dd/yyyy", "yyyy-mm-dd", "dd/mm/yyyy")

    Returns:
        Formatted date string

    Raises:
        ValueError: If format_type is not supported
    """
    format_map = {
        "mm/dd/yyyy": "%m/%d/%Y",
        "yyyy-mm-dd": "%Y-%m-%d",
        "dd/mm/yyyy": "%d/%m/%Y",
        "mm-dd-yyyy": "%m-%d-%Y",
    }

    if format_type not in format_map:
        supported_formats = ", ".join(format_map.keys())
        raise ValueError(
            f"Unsupported format_type: {format_type}. Supported formats: {supported_formats}"
        )

    return target_date.strftime(format_map[format_type])


def parse_date_from_string(date_string: str, format_type: str = "mm/dd/yyyy") -> date:
    """Parse a date from a string using the specified format.

    Args:
        date_string: Date string to parse
        format_type: Expected format type

    Returns:
        Parsed date object

    Raises:
        ValueError: If date_string cannot be parsed or format_type is not supported
    """
    format_map = {
        "mm/dd/yyyy": "%m/%d/%Y",
        "yyyy-mm-dd": "%Y-%m-%d",
        "dd/mm/yyyy": "%d/%m/%Y",
        "mm-dd-yyyy": "%m-%d-%Y",
    }

    if format_type not in format_map:
        supported_formats = ", ".join(format_map.keys())
        raise ValueError(
            f"Unsupported format_type: {format_type}. Supported formats: {supported_formats}"
        )

    try:
        parsed_datetime = datetime.strptime(date_string, format_map[format_type])
        return parsed_datetime.date()
    except ValueError as e:
        raise ValueError(
            f"Cannot parse date string '{date_string}' with format '{format_type}': {e}"
        ) from e


def get_date_range_for_scraping(
    look_back_days: int,
    avoid_weekends: bool = False,
    avoid_holidays: bool = False,
    reference_date: Optional[date] = None,
) -> tuple[date, date]:
    """Get optimized date range for scraping with optional weekend/holiday avoidance.

    Args:
        look_back_days: Number of days to look back
        avoid_weekends: Whether to adjust dates to avoid weekends
        avoid_holidays: Whether to adjust dates to avoid holidays
        reference_date: Reference date (defaults to today)

    Returns:
        Tuple of (start_date, end_date) optimized for scraping
    """
    start_date, end_date = calculate_date_range(look_back_days, reference_date)

    if avoid_weekends or avoid_holidays:
        # Adjust start date backward to avoid weekends/holidays
        if avoid_weekends and is_weekend(start_date):
            start_date = adjust_for_weekends_and_holidays(start_date, "backward")
        if avoid_holidays and is_holiday(start_date):
            start_date = adjust_for_weekends_and_holidays(start_date, "backward")

        # Adjust end date forward to avoid weekends/holidays
        if avoid_weekends and is_weekend(end_date):
            end_date = adjust_for_weekends_and_holidays(end_date, "forward")
        if avoid_holidays and is_holiday(end_date):
            end_date = adjust_for_weekends_and_holidays(end_date, "forward")

    return start_date, end_date
