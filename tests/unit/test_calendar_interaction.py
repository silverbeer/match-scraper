"""Unit tests for calendar interaction module."""

from datetime import date
from unittest.mock import AsyncMock, patch

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
        assert interactor._iframe_content is None

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
        mock_page.query_selector.return_value = mock_iframe

        result = await calendar_interactor._access_iframe_content()

        assert result is True
        assert calendar_interactor._iframe_content == mock_content_frame
        mock_page.query_selector.assert_called_once()

    @pytest.mark.asyncio
    async def test_access_iframe_content_no_iframe(
        self, calendar_interactor, mock_page
    ):
        """Test iframe content access when no iframe is found."""
        mock_page.query_selector.return_value = None

        result = await calendar_interactor._access_iframe_content()

        assert result is False
        assert calendar_interactor._iframe_content is None

    @pytest.mark.asyncio
    async def test_access_iframe_content_no_content_frame(
        self, calendar_interactor, mock_page
    ):
        """Test iframe content access when iframe has no content frame."""
        mock_iframe = AsyncMock()
        mock_iframe.content_frame.return_value = None
        mock_page.query_selector.return_value = mock_iframe

        result = await calendar_interactor._access_iframe_content()

        assert result is False
        assert calendar_interactor._iframe_content is None

    @pytest.mark.asyncio
    async def test_access_iframe_content_with_exception(
        self, calendar_interactor, mock_page
    ):
        """Test iframe content access with exception handling."""
        mock_page.query_selector.side_effect = Exception("Test error")

        result = await calendar_interactor._access_iframe_content()

        assert result is False
        assert calendar_interactor._iframe_content is None

    @pytest.mark.asyncio
    async def test_set_date_range_direct_input_success(self, calendar_interactor):
        """Test successful direct date input."""
        # Mock iframe content
        mock_iframe_content = AsyncMock()
        mock_input = AsyncMock()
        mock_iframe_content.query_selector.return_value = mock_input
        calendar_interactor._iframe_content = mock_iframe_content

        start_date = date(2024, 1, 15)
        end_date = date(2024, 1, 20)

        result = await calendar_interactor._set_date_range_direct_input(
            start_date, end_date
        )

        assert result is True
        # Verify the input was filled with the expected date range format
        mock_input.fill.assert_called_once()
        fill_call = mock_input.fill.call_args[0][0]
        assert "01/15/2024" in fill_call
        assert "01/20/2024" in fill_call

    @pytest.mark.asyncio
    async def test_set_date_range_direct_input_no_iframe(self, calendar_interactor):
        """Test direct date input when no iframe content is available."""
        calendar_interactor._iframe_content = None

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
        """Test direct date input when input field is not found."""
        mock_iframe_content = AsyncMock()
        mock_iframe_content.query_selector.return_value = None
        calendar_interactor._iframe_content = mock_iframe_content

        start_date = date(2024, 1, 15)
        end_date = date(2024, 1, 20)

        result = await calendar_interactor._set_date_range_direct_input(
            start_date, end_date
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_set_date_range_direct_input_with_exception(
        self, calendar_interactor
    ):
        """Test direct date input with exception handling."""
        mock_iframe_content = AsyncMock()
        mock_input = AsyncMock()
        mock_input.fill.side_effect = Exception("Fill error")
        mock_iframe_content.query_selector.return_value = mock_input
        calendar_interactor._iframe_content = mock_iframe_content

        start_date = date(2024, 1, 15)
        end_date = date(2024, 1, 20)

        result = await calendar_interactor._set_date_range_direct_input(
            start_date, end_date
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_get_current_month_year_success(self, calendar_interactor):
        """Test successful current month/year retrieval."""
        mock_iframe_content = AsyncMock()
        mock_element = AsyncMock()
        mock_element.text_content.return_value = "January 2024"
        mock_iframe_content.query_selector.return_value = mock_element
        calendar_interactor._iframe_content = mock_iframe_content

        month, year = await calendar_interactor._get_current_month_year()

        assert month == 1
        assert year == 2024

    @pytest.mark.asyncio
    async def test_get_current_month_year_no_iframe(self, calendar_interactor):
        """Test current month/year retrieval when no iframe content."""
        calendar_interactor._iframe_content = None

        month, year = await calendar_interactor._get_current_month_year()

        assert month is None
        assert year is None

    @pytest.mark.asyncio
    async def test_get_current_month_year_no_element(self, calendar_interactor):
        """Test current month/year retrieval when element not found."""
        mock_iframe_content = AsyncMock()
        mock_iframe_content.query_selector.return_value = None
        calendar_interactor._iframe_content = mock_iframe_content

        month, year = await calendar_interactor._get_current_month_year()

        assert month is None
        assert year is None

    @pytest.mark.asyncio
    async def test_navigation_button_clicks(self, calendar_interactor):
        """Test calendar navigation button click methods."""
        # Mock iframe content and buttons
        mock_iframe_content = AsyncMock()
        mock_button = AsyncMock()
        mock_iframe_content.query_selector.return_value = mock_button
        calendar_interactor._iframe_content = mock_iframe_content

        # Test next month click
        result = await calendar_interactor._click_next_month()
        assert result is True
        mock_button.click.assert_called()

        # Reset mock
        mock_button.reset_mock()

        # Test prev month click
        result = await calendar_interactor._click_prev_month()
        assert result is True
        mock_button.click.assert_called()

        # Reset mock
        mock_button.reset_mock()

        # Test next year click
        result = await calendar_interactor._click_next_year()
        assert result is True
        mock_button.click.assert_called()

        # Reset mock
        mock_button.reset_mock()

        # Test prev year click
        result = await calendar_interactor._click_prev_year()
        assert result is True
        mock_button.click.assert_called()

    @pytest.mark.asyncio
    async def test_navigation_button_clicks_no_iframe(self, calendar_interactor):
        """Test navigation button clicks when no iframe content."""
        calendar_interactor._iframe_content = None

        assert await calendar_interactor._click_next_month() is False
        assert await calendar_interactor._click_prev_month() is False
        assert await calendar_interactor._click_next_year() is False
        assert await calendar_interactor._click_prev_year() is False

    @pytest.mark.asyncio
    async def test_navigation_button_clicks_no_button_found(self, calendar_interactor):
        """Test navigation button clicks when button not found."""
        mock_iframe_content = AsyncMock()
        mock_iframe_content.query_selector.return_value = None
        calendar_interactor._iframe_content = mock_iframe_content

        assert await calendar_interactor._click_next_month() is False
        assert await calendar_interactor._click_prev_month() is False
        assert await calendar_interactor._click_next_year() is False
        assert await calendar_interactor._click_prev_year() is False

    @pytest.mark.asyncio
    async def test_apply_date_filter_no_iframe(self, calendar_interactor):
        """Test apply date filter when no iframe content."""
        calendar_interactor._iframe_content = None

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
        assert calendar_interactor._iframe_content is None
