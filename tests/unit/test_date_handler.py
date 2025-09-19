"""Unit tests for date handling functionality."""

from datetime import date, timedelta

import pytest

from src.scraper.date_handler import (
    _get_first_monday_of_month,
    _get_last_monday_of_month,
    _get_nth_weekday_of_month,
    adjust_for_weekends_and_holidays,
    calculate_date_range,
    format_date_for_web_form,
    get_date_range_for_scraping,
    is_holiday,
    is_weekend,
    parse_date_from_string,
    validate_date_range,
)


class TestCalculateDateRange:
    """Test date range calculation functionality."""

    def test_calculate_date_range_basic(self):
        """Test basic date range calculation."""
        reference_date = date(2024, 1, 15)
        start_date, end_date = calculate_date_range(7, reference_date)

        assert end_date == reference_date
        assert start_date == date(2024, 1, 8)

    def test_calculate_date_range_zero_days(self):
        """Test date range with zero look back days."""
        reference_date = date(2024, 1, 15)
        start_date, end_date = calculate_date_range(0, reference_date)

        assert start_date == reference_date
        assert end_date == reference_date

    def test_calculate_date_range_default_reference(self):
        """Test date range calculation with default reference date (today)."""
        start_date, end_date = calculate_date_range(1)

        expected_end = date.today()
        expected_start = expected_end - timedelta(days=1)

        assert end_date == expected_end
        assert start_date == expected_start

    def test_calculate_date_range_negative_days_raises_error(self):
        """Test that negative look_back_days raises ValueError."""
        with pytest.raises(ValueError, match="look_back_days must be non-negative"):
            calculate_date_range(-1)

    def test_calculate_date_range_large_number(self):
        """Test date range calculation with large number of days."""
        reference_date = date(2024, 6, 15)
        start_date, end_date = calculate_date_range(365, reference_date)

        assert end_date == reference_date
        assert start_date == date(2023, 6, 16)  # 365 days back from 2024-06-15

    def test_calculate_date_range_cross_year_boundary(self):
        """Test date range calculation crossing year boundary."""
        reference_date = date(2024, 1, 5)
        start_date, end_date = calculate_date_range(10, reference_date)

        assert end_date == reference_date
        assert start_date == date(2023, 12, 26)


class TestValidateDateRange:
    """Test date range validation functionality."""

    def test_validate_date_range_valid(self):
        """Test validation of valid date range."""
        start_date = date(2024, 1, 1)
        end_date = date(2024, 1, 31)

        # Should not raise any exception
        validate_date_range(start_date, end_date)

    def test_validate_date_range_same_date(self):
        """Test validation when start and end dates are the same."""
        target_date = date(2024, 1, 15)

        # Should not raise any exception
        validate_date_range(target_date, target_date)

    def test_validate_date_range_invalid_raises_error(self):
        """Test that invalid date range raises ValueError."""
        start_date = date(2024, 1, 31)
        end_date = date(2024, 1, 1)

        with pytest.raises(ValueError, match="start_date .* cannot be after end_date"):
            validate_date_range(start_date, end_date)


class TestIsWeekend:
    """Test weekend detection functionality."""

    def test_is_weekend_saturday(self):
        """Test Saturday detection."""
        saturday = date(2024, 1, 6)  # Known Saturday
        assert is_weekend(saturday) is True

    def test_is_weekend_sunday(self):
        """Test Sunday detection."""
        sunday = date(2024, 1, 7)  # Known Sunday
        assert is_weekend(sunday) is True

    def test_is_weekend_monday(self):
        """Test Monday is not weekend."""
        monday = date(2024, 1, 8)  # Known Monday
        assert is_weekend(monday) is False

    def test_is_weekend_friday(self):
        """Test Friday is not weekend."""
        friday = date(2024, 1, 5)  # Known Friday
        assert is_weekend(friday) is False

    def test_is_weekend_all_weekdays(self):
        """Test all weekdays are correctly identified."""
        # Start with a known Monday
        monday = date(2024, 1, 8)

        # Test each day of the week
        for i in range(7):
            current_date = monday + timedelta(days=i)
            expected_weekend = i >= 5  # Saturday and Sunday
            assert is_weekend(current_date) == expected_weekend


class TestIsHoliday:
    """Test holiday detection functionality."""

    def test_is_holiday_new_years_day(self):
        """Test New Year's Day detection."""
        new_years = date(2024, 1, 1)
        assert is_holiday(new_years) is True

    def test_is_holiday_independence_day(self):
        """Test Independence Day detection."""
        july_fourth = date(2024, 7, 4)
        assert is_holiday(july_fourth) is True

    def test_is_holiday_christmas(self):
        """Test Christmas Day detection."""
        christmas = date(2024, 12, 25)
        assert is_holiday(christmas) is True

    def test_is_holiday_memorial_day_2024(self):
        """Test Memorial Day detection for 2024."""
        memorial_day_2024 = date(2024, 5, 27)  # Last Monday in May 2024
        assert is_holiday(memorial_day_2024) is True

    def test_is_holiday_labor_day_2024(self):
        """Test Labor Day detection for 2024."""
        labor_day_2024 = date(2024, 9, 2)  # First Monday in September 2024
        assert is_holiday(labor_day_2024) is True

    def test_is_holiday_thanksgiving_2024(self):
        """Test Thanksgiving detection for 2024."""
        thanksgiving_2024 = date(2024, 11, 28)  # Fourth Thursday in November 2024
        assert is_holiday(thanksgiving_2024) is True

    def test_is_holiday_regular_day(self):
        """Test that regular days are not holidays."""
        regular_day = date(2024, 3, 15)
        assert is_holiday(regular_day) is False

    def test_is_holiday_different_years(self):
        """Test holiday detection across different years."""
        # New Year's Day in different years
        assert is_holiday(date(2023, 1, 1)) is True
        assert is_holiday(date(2025, 1, 1)) is True

        # Memorial Day changes each year
        memorial_2023 = date(2023, 5, 29)  # Last Monday in May 2023
        memorial_2025 = date(2025, 5, 26)  # Last Monday in May 2025
        assert is_holiday(memorial_2023) is True
        assert is_holiday(memorial_2025) is True


class TestHelperFunctions:
    """Test helper functions for holiday calculations."""

    def test_get_last_monday_of_month(self):
        """Test getting last Monday of a month."""
        # May 2024: last Monday is May 27
        last_monday = _get_last_monday_of_month(2024, 5)
        assert last_monday == date(2024, 5, 27)
        assert last_monday.weekday() == 0  # Monday

    def test_get_first_monday_of_month(self):
        """Test getting first Monday of a month."""
        # September 2024: first Monday is September 2
        first_monday = _get_first_monday_of_month(2024, 9)
        assert first_monday == date(2024, 9, 2)
        assert first_monday.weekday() == 0  # Monday

    def test_get_nth_weekday_of_month(self):
        """Test getting nth weekday of a month."""
        # Fourth Thursday in November 2024 (Thanksgiving)
        fourth_thursday = _get_nth_weekday_of_month(2024, 11, 3, 4)  # 3 = Thursday
        assert fourth_thursday == date(2024, 11, 28)
        assert fourth_thursday.weekday() == 3  # Thursday

    def test_get_nth_weekday_of_month_invalid_occurrence(self):
        """Test error when requesting invalid occurrence."""
        # February 2024 doesn't have a 5th Monday
        with pytest.raises(ValueError, match="No 5th occurrence"):
            _get_nth_weekday_of_month(2024, 2, 0, 5)  # 0 = Monday


class TestAdjustForWeekendsAndHolidays:
    """Test date adjustment functionality."""

    def test_adjust_forward_from_saturday(self):
        """Test adjusting forward from Saturday."""
        saturday = date(2024, 1, 6)  # Known Saturday
        adjusted = adjust_for_weekends_and_holidays(saturday, "forward")

        # Should move to Monday (skipping Sunday)
        assert adjusted == date(2024, 1, 8)
        assert not is_weekend(adjusted)

    def test_adjust_backward_from_sunday(self):
        """Test adjusting backward from Sunday."""
        sunday = date(2024, 1, 7)  # Known Sunday
        adjusted = adjust_for_weekends_and_holidays(sunday, "backward")

        # Should move to Friday
        assert adjusted == date(2024, 1, 5)
        assert not is_weekend(adjusted)

    def test_adjust_forward_from_holiday(self):
        """Test adjusting forward from holiday."""
        new_years = date(2024, 1, 1)  # New Year's Day (Monday in 2024)
        adjusted = adjust_for_weekends_and_holidays(new_years, "forward")

        # Should move to next non-holiday weekday
        assert adjusted != new_years
        assert not is_holiday(adjusted)
        assert not is_weekend(adjusted)

    def test_adjust_no_change_needed(self):
        """Test that valid dates are not changed."""
        valid_date = date(2024, 1, 9)  # Tuesday, not a holiday
        adjusted = adjust_for_weekends_and_holidays(valid_date, "forward")

        assert adjusted == valid_date

    def test_adjust_invalid_direction_raises_error(self):
        """Test that invalid direction raises ValueError."""
        target_date = date(2024, 1, 1)

        with pytest.raises(
            ValueError, match="direction must be 'forward' or 'backward'"
        ):
            adjust_for_weekends_and_holidays(target_date, "invalid")


class TestFormatDateForWebForm:
    """Test date formatting functionality."""

    def test_format_mm_dd_yyyy(self):
        """Test MM/DD/YYYY format."""
        target_date = date(2024, 3, 5)
        formatted = format_date_for_web_form(target_date, "mm/dd/yyyy")
        assert formatted == "03/05/2024"

    def test_format_yyyy_mm_dd(self):
        """Test YYYY-MM-DD format."""
        target_date = date(2024, 3, 5)
        formatted = format_date_for_web_form(target_date, "yyyy-mm-dd")
        assert formatted == "2024-03-05"

    def test_format_dd_mm_yyyy(self):
        """Test DD/MM/YYYY format."""
        target_date = date(2024, 3, 5)
        formatted = format_date_for_web_form(target_date, "dd/mm/yyyy")
        assert formatted == "05/03/2024"

    def test_format_mm_dd_yyyy_with_dashes(self):
        """Test MM-DD-YYYY format."""
        target_date = date(2024, 3, 5)
        formatted = format_date_for_web_form(target_date, "mm-dd-yyyy")
        assert formatted == "03-05-2024"

    def test_format_invalid_format_raises_error(self):
        """Test that invalid format raises ValueError."""
        target_date = date(2024, 3, 5)

        with pytest.raises(ValueError, match="Unsupported format_type"):
            format_date_for_web_form(target_date, "invalid_format")

    def test_format_edge_cases(self):
        """Test formatting edge cases."""
        # Single digit month and day
        target_date = date(2024, 1, 1)
        formatted = format_date_for_web_form(target_date, "mm/dd/yyyy")
        assert formatted == "01/01/2024"

        # December 31st
        target_date = date(2024, 12, 31)
        formatted = format_date_for_web_form(target_date, "mm/dd/yyyy")
        assert formatted == "12/31/2024"


class TestParseDateFromString:
    """Test date parsing functionality."""

    def test_parse_mm_dd_yyyy(self):
        """Test parsing MM/DD/YYYY format."""
        date_string = "03/05/2024"
        parsed = parse_date_from_string(date_string, "mm/dd/yyyy")
        assert parsed == date(2024, 3, 5)

    def test_parse_yyyy_mm_dd(self):
        """Test parsing YYYY-MM-DD format."""
        date_string = "2024-03-05"
        parsed = parse_date_from_string(date_string, "yyyy-mm-dd")
        assert parsed == date(2024, 3, 5)

    def test_parse_dd_mm_yyyy(self):
        """Test parsing DD/MM/YYYY format."""
        date_string = "05/03/2024"
        parsed = parse_date_from_string(date_string, "dd/mm/yyyy")
        assert parsed == date(2024, 3, 5)

    def test_parse_invalid_date_string_raises_error(self):
        """Test that invalid date string raises ValueError."""
        with pytest.raises(ValueError, match="Cannot parse date string"):
            parse_date_from_string("invalid_date", "mm/dd/yyyy")

    def test_parse_invalid_format_raises_error(self):
        """Test that invalid format raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported format_type"):
            parse_date_from_string("03/05/2024", "invalid_format")

    def test_parse_wrong_format_raises_error(self):
        """Test parsing with wrong format raises ValueError."""
        # Date string is in MM/DD/YYYY but we specify DD/MM/YYYY
        with pytest.raises(ValueError, match="Cannot parse date string"):
            parse_date_from_string("13/05/2024", "mm/dd/yyyy")  # Invalid month (13)


class TestGetDateRangeForScraping:
    """Test optimized date range functionality."""

    def test_get_date_range_basic(self):
        """Test basic date range without adjustments."""
        reference_date = date(2024, 1, 15)  # Monday
        start_date, end_date = get_date_range_for_scraping(
            7, reference_date=reference_date
        )

        assert end_date == reference_date
        assert start_date == date(2024, 1, 8)

    def test_get_date_range_avoid_weekends(self):
        """Test date range with weekend avoidance."""
        # Reference date is Sunday
        reference_date = date(2024, 1, 7)  # Sunday
        start_date, end_date = get_date_range_for_scraping(
            7, avoid_weekends=True, reference_date=reference_date
        )

        # End date should be adjusted forward from Sunday
        assert not is_weekend(end_date)
        assert end_date > reference_date

    def test_get_date_range_avoid_holidays(self):
        """Test date range with holiday avoidance."""
        # Reference date is New Year's Day
        reference_date = date(2024, 1, 1)  # New Year's Day (Monday)
        start_date, end_date = get_date_range_for_scraping(
            1, avoid_holidays=True, reference_date=reference_date
        )

        # End date should be adjusted forward from holiday
        assert not is_holiday(end_date)
        assert end_date > reference_date

    def test_get_date_range_avoid_both(self):
        """Test date range avoiding both weekends and holidays."""
        # Use a date that's both weekend and near holiday
        reference_date = date(2024, 12, 25)  # Christmas Day 2024 (Wednesday)
        start_date, end_date = get_date_range_for_scraping(
            3, avoid_weekends=True, avoid_holidays=True, reference_date=reference_date
        )

        # Both dates should avoid weekends and holidays
        assert not is_weekend(start_date) and not is_holiday(start_date)
        assert not is_weekend(end_date) and not is_holiday(end_date)

    def test_get_date_range_no_adjustments_needed(self):
        """Test date range when no adjustments are needed."""
        # Use a Tuesday that's not a holiday
        reference_date = date(2024, 3, 12)  # Tuesday
        start_date, end_date = get_date_range_for_scraping(
            5, avoid_weekends=True, avoid_holidays=True, reference_date=reference_date
        )

        # Dates should be the same as basic calculation since no adjustment needed
        expected_start, expected_end = calculate_date_range(5, reference_date)
        assert start_date == expected_start
        assert end_date == expected_end


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_leap_year_handling(self):
        """Test date calculations during leap year."""
        # February 29, 2024 (leap year)
        leap_day = date(2024, 2, 29)
        start_date, end_date = calculate_date_range(1, leap_day)

        assert end_date == leap_day
        assert start_date == date(2024, 2, 28)

    def test_year_boundary_crossing(self):
        """Test calculations crossing year boundaries."""
        # New Year's Day
        new_years = date(2024, 1, 1)
        start_date, end_date = calculate_date_range(5, new_years)

        assert end_date == new_years
        assert start_date == date(2023, 12, 27)

    def test_month_boundary_crossing(self):
        """Test calculations crossing month boundaries."""
        # First day of March
        march_first = date(2024, 3, 1)
        start_date, end_date = calculate_date_range(5, march_first)

        assert end_date == march_first
        assert start_date == date(2024, 2, 25)

    def test_format_and_parse_roundtrip(self):
        """Test that formatting and parsing are inverse operations."""
        original_date = date(2024, 3, 15)

        for format_type in ["mm/dd/yyyy", "yyyy-mm-dd", "dd/mm/yyyy", "mm-dd-yyyy"]:
            formatted = format_date_for_web_form(original_date, format_type)
            parsed = parse_date_from_string(formatted, format_type)
            assert parsed == original_date

    def test_holiday_detection_edge_years(self):
        """Test holiday detection for edge case years."""
        # Test Memorial Day calculation for different years
        memorial_2020 = _get_last_monday_of_month(2020, 5)
        assert memorial_2020 == date(2020, 5, 25)

        memorial_2021 = _get_last_monday_of_month(2021, 5)
        assert memorial_2021 == date(2021, 5, 31)

    def test_large_look_back_days(self):
        """Test with very large look_back_days values."""
        reference_date = date(2024, 6, 15)
        start_date, end_date = calculate_date_range(1000, reference_date)

        assert end_date == reference_date
        # Should go back approximately 2.7 years
        assert start_date.year <= 2021
        assert (reference_date - start_date).days == 1000
