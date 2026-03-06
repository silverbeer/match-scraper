"""Unit tests for calendar interaction module."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.scraper.calendar_interaction import (
    CalendarInteractionError,
    MLSCalendarInteractor,
)


class TestCalendarInteractionError:
    """Test cases for CalendarInteractionError exception."""

    def test_calendar_interaction_error_creation(self):
        """Test CalendarInteractionError creation."""
        error = CalendarInteractionError("Test error message")
        assert str(error) == "Test error message"
        assert isinstance(error, Exception)

    def test_calendar_interaction_error_with_cause(self):
        """Test CalendarInteractionError with underlying cause."""
        original_error = ValueError("Original error")
        try:
            raise CalendarInteractionError("Wrapper error") from original_error
        except CalendarInteractionError as error:
            assert str(error) == "Wrapper error"
            assert error.__cause__ == original_error


class TestMLSCalendarInteractor:
    """Test cases for MLSCalendarInteractor class."""

    @pytest.fixture
    def mock_page(self):
        """Create a mock Playwright page."""
        page = AsyncMock()
        return page

    @pytest.fixture
    def calendar_interactor(self, mock_page):
        """Create MLSCalendarInteractor instance with mocked dependencies."""
        return MLSCalendarInteractor(mock_page, timeout=5000)

    def test_init(self, mock_page):
        """Test MLSCalendarInteractor initialization."""
        interactor = MLSCalendarInteractor(mock_page, timeout=10000)

        assert interactor.page == mock_page
        assert interactor.timeout == 10000
        assert interactor.iframe_content is None

    def test_parse_month_name_valid_names(self, calendar_interactor):
        """Test parsing valid month names."""
        assert calendar_interactor._parse_month_name("January") == 1
        assert calendar_interactor._parse_month_name("february") == 2
        assert calendar_interactor._parse_month_name("MARCH") == 3
        assert calendar_interactor._parse_month_name("April") == 4
        assert calendar_interactor._parse_month_name("May") == 5
        assert calendar_interactor._parse_month_name("June") == 6
        assert calendar_interactor._parse_month_name("July") == 7
        assert calendar_interactor._parse_month_name("August") == 8
        assert calendar_interactor._parse_month_name("September") == 9
        assert calendar_interactor._parse_month_name("October") == 10
        assert calendar_interactor._parse_month_name("November") == 11
        assert calendar_interactor._parse_month_name("December") == 12

    def test_parse_month_name_short_names(self, calendar_interactor):
        """Test parsing short month names."""
        assert calendar_interactor._parse_month_name("Jan") == 1
        assert calendar_interactor._parse_month_name("feb") == 2
        assert calendar_interactor._parse_month_name("MAR") == 3
        assert calendar_interactor._parse_month_name("Dec") == 12

    def test_parse_month_name_invalid(self, calendar_interactor):
        """Test parsing invalid month names."""
        assert calendar_interactor._parse_month_name("InvalidMonth") is None
        assert calendar_interactor._parse_month_name("") is None
        assert calendar_interactor._parse_month_name("13") is None
        assert calendar_interactor._parse_month_name("Month13") is None

    def test_parse_month_year_text_valid_formats(self, calendar_interactor):
        """Test parsing valid month/year text formats."""
        # Test various formats that might appear in calendar widgets
        month, year = calendar_interactor._parse_month_year_text("January 2024")
        assert month == 1
        assert year == 2024

        month, year = calendar_interactor._parse_month_year_text("February 2023")
        assert month == 2
        assert year == 2023

        month, year = calendar_interactor._parse_month_year_text("Dec 2025")
        assert month == 12
        assert year == 2025

    def test_parse_month_year_text_different_formats(self, calendar_interactor):
        """Test parsing different month/year text formats."""
        # Test format with comma
        month, year = calendar_interactor._parse_month_year_text("March, 2024")
        assert month == 3
        assert year == 2024

        # Test format with extra spaces
        month, year = calendar_interactor._parse_month_year_text("  April   2024  ")
        assert month == 4
        assert year == 2024

    def test_parse_month_year_text_invalid_formats(self, calendar_interactor):
        """Test parsing invalid month/year text formats."""
        # Test invalid formats
        month, year = calendar_interactor._parse_month_year_text("InvalidMonth 2024")
        assert month is None
        assert year is None

        month, year = calendar_interactor._parse_month_year_text("January")
        assert month is None
        assert year is None

        month, year = calendar_interactor._parse_month_year_text("2024")
        assert month is None
        assert year is None

        month, year = calendar_interactor._parse_month_year_text("")
        assert month is None
        assert year is None

        month, year = calendar_interactor._parse_month_year_text("January InvalidYear")
        assert month is None
        assert year is None

    @patch("src.scraper.calendar_interaction.logger")
    def test_parse_month_year_text_with_logging(self, mock_logger, calendar_interactor):
        """Test that parsing logs debug information."""
        calendar_interactor._parse_month_year_text("January 2024")

        # Check that debug logging was called
        mock_logger.debug.assert_called()

    @pytest.mark.asyncio
    async def test_access_iframe_content_success(self, calendar_interactor, mock_page):
        """Test successful iframe content access."""
        # Mock iframe content
        mock_iframe = AsyncMock()
        mock_content_frame = AsyncMock()
        mock_iframe.content_frame.return_value = mock_content_frame
        mock_page.wait_for_selector.return_value = mock_iframe

        result = await calendar_interactor._access_iframe_content()

        assert result is True
        assert calendar_interactor.iframe_content == mock_content_frame
        mock_page.wait_for_selector.assert_called_once()

    @pytest.mark.asyncio
    async def test_access_iframe_content_no_iframe(
        self, calendar_interactor, mock_page
    ):
        """Test iframe content access when no iframe is found."""
        mock_page.wait_for_selector.return_value = None

        result = await calendar_interactor._access_iframe_content()

        assert result is False
        assert calendar_interactor.iframe_content is None

    @pytest.mark.asyncio
    async def test_access_iframe_content_no_content_frame(
        self, calendar_interactor, mock_page
    ):
        """Test iframe content access when iframe has no content frame."""
        mock_iframe = AsyncMock()
        mock_iframe.content_frame.return_value = None
        mock_page.wait_for_selector.return_value = mock_iframe

        result = await calendar_interactor._access_iframe_content()

        assert result is False
        assert calendar_interactor.iframe_content is None

    @pytest.mark.asyncio
    async def test_access_iframe_content_with_exception(
        self, calendar_interactor, mock_page
    ):
        """Test iframe content access with exception handling."""
        mock_page.wait_for_selector.side_effect = Exception("Test error")

        result = await calendar_interactor._access_iframe_content()

        assert result is False
        assert calendar_interactor.iframe_content is None

    @pytest.mark.asyncio
    @pytest.mark.skip(
        reason="Complex mock setup - needs refactoring for proper async mock support"
    )
    async def test_set_date_range_direct_input_success(self, calendar_interactor):
        """Test successful direct date input."""
        # Mock iframe content
        from unittest.mock import MagicMock

        mock_iframe_content = MagicMock()
        mock_locator = MagicMock()

        # Make count() async and return 1
        async def async_count():
            return 1

        mock_locator.count = async_count

        # Make click() async
        async def async_click():
            return None

        mock_locator.click = async_click
        mock_locator.first = MagicMock()
        mock_locator.first.click = async_click

        # Mock calendar picker with the same structure
        mock_calendar_picker = MagicMock()
        mock_calendar_picker.count = async_count

        # Mock locator method to return different mocks for different selectors
        def mock_locator_side_effect(selector):
            if "daterangepicker" in selector:
                return mock_calendar_picker
            return mock_locator

        mock_iframe_content.locator = mock_locator_side_effect
        calendar_interactor.iframe_content = mock_iframe_content

        start_date = date(2024, 1, 15)
        end_date = date(2024, 1, 20)

        result = await calendar_interactor._set_date_range_direct_input(
            start_date, end_date
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_set_date_range_direct_input_no_iframe(self, calendar_interactor):
        """Test direct date input when no iframe content is available."""
        calendar_interactor.iframe_content = None

        start_date = date(2024, 1, 15)
        end_date = date(2024, 1, 20)

        result = await calendar_interactor._set_date_range_direct_input(
            start_date, end_date
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_set_date_range_direct_input_no_input_field(
        self, calendar_interactor
    ):
        """Test date range setting when input field is not found."""
        mock_iframe_content = MagicMock()
        mock_locator = MagicMock()
        mock_locator.count = AsyncMock(return_value=0)
        mock_iframe_content.locator.return_value = mock_locator
        calendar_interactor.iframe_content = mock_iframe_content

        result = await calendar_interactor._set_date_range_direct_input(
            date(2024, 1, 15), date(2024, 1, 20)
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_set_date_range_direct_input_with_exception(
        self, calendar_interactor
    ):
        """Test date range setting with exception handling."""
        mock_iframe_content = MagicMock()
        mock_iframe_content.locator.side_effect = Exception("Locator error")
        calendar_interactor.iframe_content = mock_iframe_content

        result = await calendar_interactor._set_date_range_direct_input(
            date(2024, 1, 15), date(2024, 1, 20)
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_set_date_range_calendar_picker_not_opened(self, calendar_interactor):
        """Test date range when calendar picker doesn't open after clicking."""
        mock_iframe_content = MagicMock()

        mock_date_field = MagicMock()
        mock_date_field.count = AsyncMock(return_value=1)
        mock_date_field.click = AsyncMock()

        mock_picker = MagicMock()
        mock_picker.count = AsyncMock(return_value=0)

        def locator_side_effect(selector):
            if "datefilter" in selector:
                return mock_date_field
            if "daterangepicker" in selector:
                return mock_picker
            return MagicMock(count=AsyncMock(return_value=0))

        mock_iframe_content.locator.side_effect = locator_side_effect
        calendar_interactor.iframe_content = mock_iframe_content

        result = await calendar_interactor._set_date_range_direct_input(
            date(2025, 8, 28), date(2025, 9, 4)
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_set_date_range_navigation_fails(self, calendar_interactor):
        """Test date range when month navigation fails."""
        mock_iframe_content = MagicMock()

        mock_date_field = MagicMock()
        mock_date_field.count = AsyncMock(return_value=1)
        mock_date_field.click = AsyncMock()

        mock_picker = MagicMock()
        mock_picker.count = AsyncMock(return_value=1)

        def locator_side_effect(selector):
            if "datefilter" in selector:
                return mock_date_field
            if "daterangepicker" in selector and "td" not in selector:
                return mock_picker
            return MagicMock(count=AsyncMock(return_value=0))

        mock_iframe_content.locator.side_effect = locator_side_effect
        calendar_interactor.iframe_content = mock_iframe_content

        with patch.object(
            calendar_interactor,
            "_navigate_daterangepicker_to_month",
            return_value=False,
        ):
            result = await calendar_interactor._set_date_range_direct_input(
                date(2025, 8, 28), date(2025, 9, 4)
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_set_date_range_start_date_click_fails(self, calendar_interactor):
        """Test date range when clicking start date fails."""
        mock_iframe_content = MagicMock()

        mock_date_field = MagicMock()
        mock_date_field.count = AsyncMock(return_value=1)
        mock_date_field.click = AsyncMock()

        mock_picker = MagicMock()
        mock_picker.count = AsyncMock(return_value=1)

        mock_cell = MagicMock()
        mock_cell.count = AsyncMock(return_value=0)

        def locator_side_effect(selector):
            if "datefilter" in selector:
                return mock_date_field
            if "daterangepicker" in selector and "td" not in selector:
                return mock_picker
            return mock_cell

        mock_iframe_content.locator.side_effect = locator_side_effect
        calendar_interactor.iframe_content = mock_iframe_content

        with patch.object(
            calendar_interactor,
            "_navigate_daterangepicker_to_month",
            return_value=True,
        ):
            result = await calendar_interactor._set_date_range_direct_input(
                date(2025, 10, 1), date(2025, 10, 8)
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_set_date_range_wide_range_success(self, calendar_interactor):
        """Test date range for month_diff >= 2 (wide range requiring end navigation)."""
        mock_iframe_content = MagicMock()

        mock_date_field = MagicMock()
        mock_date_field.count = AsyncMock(return_value=1)
        mock_date_field.click = AsyncMock()
        mock_date_field.input_value = AsyncMock(
            return_value="08/01/2025 12:00 AM – 11/01/2025 11:59 PM"
        )

        mock_picker = MagicMock()
        mock_picker.count = AsyncMock(return_value=1)

        mock_cell = MagicMock()
        mock_cell.count = AsyncMock(return_value=1)
        mock_cell.first = MagicMock()
        mock_cell.first.click = AsyncMock()

        mock_apply = MagicMock()
        mock_apply.count = AsyncMock(return_value=1)
        mock_apply.first = MagicMock()
        mock_apply.first.click = AsyncMock()

        def locator_side_effect(selector):
            if "datefilter" in selector:
                return mock_date_field
            if (
                "daterangepicker" in selector
                and "td" not in selector
                and "apply" not in selector.lower()
            ):
                return mock_picker
            if "applyBtn" in selector:
                return mock_apply
            return mock_cell

        mock_iframe_content.locator.side_effect = locator_side_effect
        calendar_interactor.iframe_content = mock_iframe_content

        with patch.object(
            calendar_interactor,
            "_navigate_daterangepicker_to_month",
            return_value=True,
        ):
            result = await calendar_interactor._set_date_range_direct_input(
                date(2025, 8, 1), date(2025, 11, 1)
            )

        assert result is True

    @pytest.mark.asyncio
    async def test_set_date_range_end_date_not_found(self, calendar_interactor):
        """Test when end date cell is not found on calendar."""
        mock_iframe_content = MagicMock()

        mock_date_field = MagicMock()
        mock_date_field.count = AsyncMock(return_value=1)
        mock_date_field.click = AsyncMock()

        mock_picker = MagicMock()
        mock_picker.count = AsyncMock(return_value=1)

        # Start date cell found (count=1), end date cell not found (count=0)
        start_cell = MagicMock()
        start_cell.count = AsyncMock(return_value=1)
        start_cell.first = MagicMock()
        start_cell.first.click = AsyncMock()

        end_cell = MagicMock()
        end_cell.count = AsyncMock(return_value=0)

        call_count = 0

        def locator_side_effect(selector):
            nonlocal call_count
            if "datefilter" in selector:
                return mock_date_field
            if (
                "daterangepicker" in selector
                and "td" not in selector
                and "apply" not in selector.lower()
            ):
                return mock_picker
            if "td" in selector:
                # First two calls are start date selectors, next are end date
                call_count += 1
                if call_count <= 1:
                    return start_cell
                return end_cell
            return end_cell

        mock_iframe_content.locator.side_effect = locator_side_effect
        calendar_interactor.iframe_content = mock_iframe_content

        with patch.object(
            calendar_interactor,
            "_navigate_daterangepicker_to_month",
            return_value=True,
        ):
            result = await calendar_interactor._set_date_range_direct_input(
                date(2025, 10, 1), date(2025, 10, 8)
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_set_date_range_apply_button_not_found(self, calendar_interactor):
        """Test when Apply button is not found."""
        mock_iframe_content = MagicMock()

        mock_date_field = MagicMock()
        mock_date_field.count = AsyncMock(return_value=1)
        mock_date_field.click = AsyncMock()

        mock_picker = MagicMock()
        mock_picker.count = AsyncMock(return_value=1)

        mock_cell = MagicMock()
        mock_cell.count = AsyncMock(return_value=1)
        mock_cell.first = MagicMock()
        mock_cell.first.click = AsyncMock()

        # Apply button not found
        mock_apply = MagicMock()
        mock_apply.count = AsyncMock(return_value=0)

        def locator_side_effect(selector):
            if "datefilter" in selector:
                return mock_date_field
            if (
                "daterangepicker" in selector
                and "td" not in selector
                and "apply" not in selector.lower()
            ):
                return mock_picker
            if "applyBtn" in selector:
                return mock_apply
            return mock_cell

        mock_iframe_content.locator.side_effect = locator_side_effect
        calendar_interactor.iframe_content = mock_iframe_content

        with patch.object(
            calendar_interactor,
            "_navigate_daterangepicker_to_month",
            return_value=True,
        ):
            result = await calendar_interactor._set_date_range_direct_input(
                date(2025, 10, 1), date(2025, 10, 8)
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_set_date_range_verify_exception(self, calendar_interactor):
        """Test when verification throws an exception."""
        mock_iframe_content = MagicMock()

        mock_date_field = MagicMock()
        mock_date_field.count = AsyncMock(return_value=1)
        mock_date_field.click = AsyncMock()
        mock_date_field.input_value = AsyncMock(
            side_effect=Exception("Connection lost")
        )

        mock_picker = MagicMock()
        mock_picker.count = AsyncMock(return_value=1)

        mock_cell = MagicMock()
        mock_cell.count = AsyncMock(return_value=1)
        mock_cell.first = MagicMock()
        mock_cell.first.click = AsyncMock()

        mock_apply = MagicMock()
        mock_apply.count = AsyncMock(return_value=1)
        mock_apply.first = MagicMock()
        mock_apply.first.click = AsyncMock()

        def locator_side_effect(selector):
            if "datefilter" in selector:
                return mock_date_field
            if (
                "daterangepicker" in selector
                and "td" not in selector
                and "apply" not in selector.lower()
            ):
                return mock_picker
            if "applyBtn" in selector:
                return mock_apply
            return mock_cell

        mock_iframe_content.locator.side_effect = locator_side_effect
        calendar_interactor.iframe_content = mock_iframe_content

        with patch.object(
            calendar_interactor,
            "_navigate_daterangepicker_to_month",
            return_value=True,
        ):
            result = await calendar_interactor._set_date_range_direct_input(
                date(2025, 10, 1), date(2025, 10, 8)
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_set_date_range_same_month_success(self, calendar_interactor):
        """Test successful date range setting for same-month dates."""
        mock_iframe_content = MagicMock()

        mock_date_field = MagicMock()
        mock_date_field.count = AsyncMock(return_value=1)
        mock_date_field.click = AsyncMock()
        mock_date_field.input_value = AsyncMock(
            return_value="10/01/2025 12:00 AM – 10/08/2025 11:59 PM"
        )

        mock_picker = MagicMock()
        mock_picker.count = AsyncMock(return_value=1)

        mock_cell = MagicMock()
        mock_cell.count = AsyncMock(return_value=1)
        mock_cell.first = MagicMock()
        mock_cell.first.click = AsyncMock()

        mock_apply = MagicMock()
        mock_apply.count = AsyncMock(return_value=1)
        mock_apply.first = MagicMock()
        mock_apply.first.click = AsyncMock()

        def locator_side_effect(selector):
            if "datefilter" in selector:
                return mock_date_field
            if (
                "daterangepicker" in selector
                and "td" not in selector
                and "apply" not in selector.lower()
            ):
                return mock_picker
            if "applyBtn" in selector:
                return mock_apply
            return mock_cell

        mock_iframe_content.locator.side_effect = locator_side_effect
        calendar_interactor.iframe_content = mock_iframe_content

        with patch.object(
            calendar_interactor,
            "_navigate_daterangepicker_to_month",
            return_value=True,
        ):
            result = await calendar_interactor._set_date_range_direct_input(
                date(2025, 10, 1), date(2025, 10, 8)
            )

        assert result is True

    @pytest.mark.asyncio
    async def test_set_date_range_adjacent_months_success(self, calendar_interactor):
        """Test successful date range setting for adjacent months (month_diff=1)."""
        mock_iframe_content = MagicMock()

        mock_date_field = MagicMock()
        mock_date_field.count = AsyncMock(return_value=1)
        mock_date_field.click = AsyncMock()
        mock_date_field.input_value = AsyncMock(
            return_value="08/28/2025 12:00 AM – 09/04/2025 11:59 PM"
        )

        mock_picker = MagicMock()
        mock_picker.count = AsyncMock(return_value=1)

        mock_cell = MagicMock()
        mock_cell.count = AsyncMock(return_value=1)
        mock_cell.first = MagicMock()
        mock_cell.first.click = AsyncMock()

        mock_apply = MagicMock()
        mock_apply.count = AsyncMock(return_value=1)
        mock_apply.first = MagicMock()
        mock_apply.first.click = AsyncMock()

        def locator_side_effect(selector):
            if "datefilter" in selector:
                return mock_date_field
            if (
                "daterangepicker" in selector
                and "td" not in selector
                and "apply" not in selector.lower()
            ):
                return mock_picker
            if "applyBtn" in selector:
                return mock_apply
            return mock_cell

        mock_iframe_content.locator.side_effect = locator_side_effect
        calendar_interactor.iframe_content = mock_iframe_content

        with patch.object(
            calendar_interactor,
            "_navigate_daterangepicker_to_month",
            return_value=True,
        ):
            result = await calendar_interactor._set_date_range_direct_input(
                date(2025, 8, 28), date(2025, 9, 4)
            )

        assert result is True

    @pytest.mark.asyncio
    async def test_set_date_range_verification_fails(self, calendar_interactor):
        """Test date range when verification shows wrong dates."""
        mock_iframe_content = MagicMock()

        mock_date_field = MagicMock()
        mock_date_field.count = AsyncMock(return_value=1)
        mock_date_field.click = AsyncMock()
        # Return wrong dates - verification should fail
        mock_date_field.input_value = AsyncMock(
            return_value="03/28/2026 12:00 AM – 04/04/2026 11:59 PM"
        )

        mock_picker = MagicMock()
        mock_picker.count = AsyncMock(return_value=1)

        mock_cell = MagicMock()
        mock_cell.count = AsyncMock(return_value=1)
        mock_cell.first = MagicMock()
        mock_cell.first.click = AsyncMock()

        mock_apply = MagicMock()
        mock_apply.count = AsyncMock(return_value=1)
        mock_apply.first = MagicMock()
        mock_apply.first.click = AsyncMock()

        def locator_side_effect(selector):
            if "datefilter" in selector:
                return mock_date_field
            if (
                "daterangepicker" in selector
                and "td" not in selector
                and "apply" not in selector.lower()
            ):
                return mock_picker
            if "applyBtn" in selector:
                return mock_apply
            return mock_cell

        mock_iframe_content.locator.side_effect = locator_side_effect
        calendar_interactor.iframe_content = mock_iframe_content

        with patch.object(
            calendar_interactor,
            "_navigate_daterangepicker_to_month",
            return_value=True,
        ):
            result = await calendar_interactor._set_date_range_direct_input(
                date(2025, 8, 28), date(2025, 9, 4)
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_get_current_month_year_success(self, calendar_interactor):
        """Test successful current month/year retrieval."""
        # Mock the interactor's get_text_content method to return the test value
        with patch.object(
            calendar_interactor.interactor,
            "get_text_content",
            return_value="January 2024",
        ):
            month, year = await calendar_interactor._get_current_month_year()

        assert month == 1
        assert year == 2024

    @pytest.mark.asyncio
    async def test_get_current_month_year_no_iframe(self, calendar_interactor):
        """Test current month/year retrieval when no iframe content."""
        calendar_interactor.iframe_content = None

        month, year = await calendar_interactor._get_current_month_year()

        assert month is None
        assert year is None

    @pytest.mark.asyncio
    async def test_get_current_month_year_no_element(self, calendar_interactor):
        """Test current month/year retrieval when element not found."""
        mock_iframe_content = AsyncMock()
        mock_iframe_content.query_selector.return_value = None
        calendar_interactor.iframe_content = mock_iframe_content

        month, year = await calendar_interactor._get_current_month_year()

        assert month is None
        assert year is None

    @pytest.mark.asyncio
    async def test_navigation_button_clicks(self, calendar_interactor):
        """Test calendar navigation button click methods."""
        # Mock the interactor's click_element method to return success
        with patch.object(
            calendar_interactor.interactor, "click_element", return_value=True
        ):
            # Test next month click
            result = await calendar_interactor._click_next_month()
            assert result is True

            # Verify that click_element was called
            calendar_interactor.interactor.click_element.assert_called()

        # Test prev month click
        with patch.object(
            calendar_interactor.interactor, "click_element", return_value=True
        ):
            result = await calendar_interactor._click_prev_month()
            assert result is True
            calendar_interactor.interactor.click_element.assert_called()

        # Test next year click
        with patch.object(
            calendar_interactor.interactor, "click_element", return_value=True
        ):
            result = await calendar_interactor._click_next_year()
            assert result is True
            calendar_interactor.interactor.click_element.assert_called()

        # Test prev year click
        with patch.object(
            calendar_interactor.interactor, "click_element", return_value=True
        ):
            result = await calendar_interactor._click_prev_year()
            assert result is True
            calendar_interactor.interactor.click_element.assert_called()

    @pytest.mark.asyncio
    async def test_navigation_button_clicks_no_elements(self, calendar_interactor):
        """Test navigation button clicks when no elements are found."""
        # Mock the interactor's click_element method to return False (no elements found)
        with patch.object(
            calendar_interactor.interactor, "click_element", return_value=False
        ):
            assert await calendar_interactor._click_next_month() is False
            assert await calendar_interactor._click_prev_month() is False
            assert await calendar_interactor._click_next_year() is False
            assert await calendar_interactor._click_prev_year() is False

    @pytest.mark.asyncio
    async def test_navigation_button_clicks_no_button_found_duplicate(
        self, calendar_interactor
    ):
        """Test navigation button clicks when button not found (duplicate test - should be removed)."""
        # This test duplicates the previous test and should be skipped or removed
        pytest.skip(
            "Duplicate test - same as test_navigation_button_clicks_no_elements"
        )

    @pytest.mark.asyncio
    async def test_apply_date_filter_no_button_found(self, calendar_interactor):
        """Test apply date filter when no apply button is found."""
        # Mock the interactor's click_element method to return False (no button found)
        with patch.object(
            calendar_interactor.interactor, "click_element", return_value=False
        ):
            result = await calendar_interactor.apply_date_filter()
            assert result is False

    @pytest.mark.asyncio
    async def test_constants_and_selectors(self, calendar_interactor):
        """Test that class constants are properly defined."""
        # Verify that key selectors are defined
        assert hasattr(MLSCalendarInteractor, "IFRAME_SELECTOR")
        assert hasattr(MLSCalendarInteractor, "MATCH_DATE_FIELD_SELECTOR")
        assert hasattr(MLSCalendarInteractor, "APPLY_BUTTON_SELECTOR")
        assert hasattr(MLSCalendarInteractor, "CALENDAR_WIDGET_SELECTOR")

        # Verify selectors are strings
        assert isinstance(MLSCalendarInteractor.IFRAME_SELECTOR, str)
        assert isinstance(MLSCalendarInteractor.MATCH_DATE_FIELD_SELECTOR, str)
        assert isinstance(MLSCalendarInteractor.APPLY_BUTTON_SELECTOR, str)

    def test_class_attributes(self, calendar_interactor):
        """Test class attribute initialization."""
        assert calendar_interactor.page is not None
        assert calendar_interactor.timeout == 5000
        assert calendar_interactor.iframe_content is None
