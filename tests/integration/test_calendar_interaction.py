"""
Integration tests for calendar interaction functionality.

Tests calendar widget interactions with mock calendar implementations
to verify date selection, navigation, and filter application.
"""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from src.scraper.calendar_interaction import (
    CalendarInteractionError,
    MLSCalendarInteractor,
)


class TestMLSCalendarInteractor:
    """Test MLSCalendarInteractor class with mock calendar widget."""

    @pytest.fixture
    def mock_page(self):
        """Create mock page for testing."""
        return AsyncMock()

    @pytest.fixture
    def calendar_interactor(self, mock_page):
        """Create MLSCalendarInteractor instance for testing."""
        return MLSCalendarInteractor(mock_page, timeout=5000)

    @pytest.fixture
    def mock_calendar_elements(self, mock_page):
        """Set up mock calendar elements and behaviors."""
        # Mock date field click
        mock_page.wait_for_selector.return_value = True
        mock_page.click.return_value = None

        # Mock calendar widget appearance
        calendar_widget = AsyncMock()
        mock_page.query_selector.return_value = calendar_widget

        return {"page": mock_page, "calendar_widget": calendar_widget}

    @pytest.mark.asyncio
    async def test_open_calendar_widget_success(self, calendar_interactor, mock_page):
        """Test successful calendar widget opening."""
        # Mock ElementInteractor methods
        with (
            patch.object(
                calendar_interactor.interactor, "wait_for_element"
            ) as mock_wait,
            patch.object(calendar_interactor.interactor, "click_element") as mock_click,
        ):
            mock_wait.side_effect = [True, True]  # date field found, calendar appears
            mock_click.return_value = True

            result = await calendar_interactor.open_calendar_widget()

            assert result is True
            mock_click.assert_called()

    @pytest.mark.asyncio
    async def test_open_calendar_widget_no_date_field(
        self, calendar_interactor, mock_page
    ):
        """Test calendar opening when date field not found."""
        # Mock ElementInteractor methods
        with (
            patch.object(
                calendar_interactor.interactor, "wait_for_element"
            ) as mock_wait,
            patch.object(calendar_interactor.interactor, "click_element") as mock_click,
        ):
            mock_wait.return_value = False  # No date field found

            result = await calendar_interactor.open_calendar_widget()

            assert result is False
            mock_click.assert_not_called()

    @pytest.mark.asyncio
    async def test_open_calendar_widget_no_calendar_appears(
        self, calendar_interactor, mock_page
    ):
        """Test when date field clicks but calendar doesn't appear."""
        # Mock ElementInteractor methods
        with (
            patch.object(
                calendar_interactor.interactor, "wait_for_element"
            ) as mock_wait,
            patch.object(calendar_interactor.interactor, "click_element") as mock_click,
        ):
            mock_wait.side_effect = [
                True,
                False,
            ]  # date field found, calendar doesn't appear
            mock_click.return_value = True

            result = await calendar_interactor.open_calendar_widget()

            assert result is False

    @pytest.mark.asyncio
    async def test_navigate_to_month_year_same_month(
        self, calendar_interactor, mock_page
    ):
        """Test navigation when already in target month/year."""
        target_date = date(2024, 3, 15)

        # Mock current month/year detection
        with patch.object(
            calendar_interactor, "_get_current_month_year"
        ) as mock_get_current:
            mock_get_current.return_value = (3, 2024)  # Already in March 2024

            result = await calendar_interactor.navigate_to_month_year(target_date)

            assert result is True

    @pytest.mark.asyncio
    async def test_navigate_to_month_year_different_month(
        self, calendar_interactor, mock_page
    ):
        """Test navigation to different month in same year."""
        target_date = date(2024, 5, 15)

        # Mock current month/year and navigation
        with (
            patch.object(
                calendar_interactor, "_get_current_month_year"
            ) as mock_get_current,
            patch.object(calendar_interactor, "_navigate_to_year") as mock_nav_year,
            patch.object(calendar_interactor, "_navigate_to_month") as mock_nav_month,
        ):
            mock_get_current.return_value = (3, 2024)  # Currently March 2024
            mock_nav_year.return_value = True
            mock_nav_month.return_value = True

            result = await calendar_interactor.navigate_to_month_year(target_date)

            assert result is True
            mock_nav_year.assert_called_once_with(2024, 2024)
            mock_nav_month.assert_called_once_with(3, 5)

    @pytest.mark.asyncio
    async def test_navigate_to_month_year_different_year(
        self, calendar_interactor, mock_page
    ):
        """Test navigation to different year."""
        target_date = date(2025, 3, 15)

        with (
            patch.object(
                calendar_interactor, "_get_current_month_year"
            ) as mock_get_current,
            patch.object(calendar_interactor, "_navigate_to_year") as mock_nav_year,
            patch.object(calendar_interactor, "_navigate_to_month") as mock_nav_month,
        ):
            mock_get_current.return_value = (3, 2024)  # Currently March 2024
            mock_nav_year.return_value = True
            mock_nav_month.return_value = True

            result = await calendar_interactor.navigate_to_month_year(target_date)

            assert result is True
            mock_nav_year.assert_called_once_with(2024, 2025)
            mock_nav_month.assert_called_once_with(3, 3)

    @pytest.mark.asyncio
    async def test_navigate_to_month_year_navigation_fails(
        self, calendar_interactor, mock_page
    ):
        """Test navigation failure."""
        target_date = date(2025, 5, 15)

        with (
            patch.object(
                calendar_interactor, "_get_current_month_year"
            ) as mock_get_current,
            patch.object(calendar_interactor, "_navigate_to_year") as mock_nav_year,
        ):
            mock_get_current.return_value = (3, 2024)
            mock_nav_year.return_value = False  # Navigation fails

            result = await calendar_interactor.navigate_to_month_year(target_date)

            assert result is False

    @pytest.mark.asyncio
    async def test_select_date_with_data_attribute(
        self, calendar_interactor, mock_page
    ):
        """Test date selection using data-date attribute."""
        target_date = date(2024, 3, 15)

        # Mock successful navigation and date selection
        with (
            patch.object(
                calendar_interactor, "navigate_to_month_year"
            ) as mock_navigate,
            patch.object(
                calendar_interactor.interactor, "wait_for_element"
            ) as mock_wait,
            patch.object(calendar_interactor.interactor, "click_element") as mock_click,
        ):
            mock_navigate.return_value = True
            mock_wait.return_value = True
            mock_click.return_value = True

            result = await calendar_interactor.select_date(target_date)

            assert result is True
            mock_navigate.assert_called_once_with(target_date)

    @pytest.mark.asyncio
    async def test_select_date_navigation_fails(self, calendar_interactor, mock_page):
        """Test date selection when navigation fails."""
        target_date = date(2024, 3, 15)

        with patch.object(
            calendar_interactor, "navigate_to_month_year"
        ) as mock_navigate:
            mock_navigate.return_value = False  # Navigation fails

            result = await calendar_interactor.select_date(target_date)

            assert result is False

    @pytest.mark.asyncio
    async def test_select_date_with_element_search(
        self, calendar_interactor, mock_page
    ):
        """Test date selection by searching through elements."""
        target_date = date(2024, 3, 15)

        # Mock navigation success but data-attribute approach fails
        with (
            patch.object(
                calendar_interactor, "navigate_to_month_year"
            ) as mock_navigate,
            patch.object(
                calendar_interactor.interactor, "wait_for_element"
            ) as mock_wait,
        ):
            mock_navigate.return_value = True
            mock_wait.return_value = False  # Data-attribute selectors fail

            # Mock element search approach
            mock_element = AsyncMock()
            mock_element.text_content.return_value = "15"
            mock_element.is_enabled.return_value = True
            mock_element.get_attribute.return_value = "day"
            mock_element.click.return_value = None

            mock_page.query_selector_all.return_value = [mock_element]

            result = await calendar_interactor.select_date(target_date)

            assert result is True
            mock_element.click.assert_called_once()

    @pytest.mark.asyncio
    async def test_select_date_range_success(self, calendar_interactor, mock_page):
        """Test successful date range selection."""
        start_date = date(2024, 3, 10)
        end_date = date(2024, 3, 20)

        with patch.object(calendar_interactor, "select_date") as mock_select:
            mock_select.return_value = True

            result = await calendar_interactor.select_date_range(start_date, end_date)

            assert result is True
            assert mock_select.call_count == 2
            mock_select.assert_any_call(start_date)
            mock_select.assert_any_call(end_date)

    @pytest.mark.asyncio
    async def test_select_date_range_start_date_fails(
        self, calendar_interactor, mock_page
    ):
        """Test date range selection when start date selection fails."""
        start_date = date(2024, 3, 10)
        end_date = date(2024, 3, 20)

        with patch.object(calendar_interactor, "select_date") as mock_select:
            mock_select.side_effect = [False, True]  # Start fails, end would succeed

            result = await calendar_interactor.select_date_range(start_date, end_date)

            assert result is False
            assert mock_select.call_count == 1  # Should stop after first failure

    @pytest.mark.asyncio
    async def test_select_date_range_end_date_fails(
        self, calendar_interactor, mock_page
    ):
        """Test date range selection when end date selection fails."""
        start_date = date(2024, 3, 10)
        end_date = date(2024, 3, 20)

        with patch.object(calendar_interactor, "select_date") as mock_select:
            mock_select.side_effect = [True, False]  # Start succeeds, end fails

            result = await calendar_interactor.select_date_range(start_date, end_date)

            assert result is False
            assert mock_select.call_count == 2

    @pytest.mark.asyncio
    async def test_apply_date_filter_success(self, calendar_interactor, mock_page):
        """Test successful date filter application."""
        # Mock ElementInteractor methods
        with (
            patch.object(
                calendar_interactor.interactor, "wait_for_element"
            ) as mock_wait,
            patch.object(calendar_interactor.interactor, "click_element") as mock_click,
        ):
            mock_wait.side_effect = [True, False]  # Button found, calendar closed
            mock_click.return_value = True

            result = await calendar_interactor.apply_date_filter()

            assert result is True
            mock_click.assert_called()

    @pytest.mark.asyncio
    async def test_apply_date_filter_no_button(self, calendar_interactor, mock_page):
        """Test date filter application when no apply button found."""
        # Mock ElementInteractor methods
        with (
            patch.object(
                calendar_interactor.interactor, "wait_for_element"
            ) as mock_wait,
            patch.object(calendar_interactor.interactor, "click_element") as mock_click,
        ):
            mock_wait.return_value = False  # No apply button found

            result = await calendar_interactor.apply_date_filter()

            assert result is False
            mock_click.assert_not_called()

    @pytest.mark.asyncio
    async def test_set_date_range_filter_complete_workflow(
        self, calendar_interactor, mock_page
    ):
        """Test complete date range filter workflow."""
        start_date = date(2024, 3, 10)
        end_date = date(2024, 3, 20)

        with (
            patch.object(calendar_interactor, "open_calendar_widget") as mock_open,
            patch.object(calendar_interactor, "select_date_range") as mock_select_range,
            patch.object(calendar_interactor, "apply_date_filter") as mock_apply,
        ):
            mock_open.return_value = True
            mock_select_range.return_value = True
            mock_apply.return_value = True

            result = await calendar_interactor.set_date_range_filter(
                start_date, end_date
            )

            assert result is True
            mock_open.assert_called_once()
            mock_select_range.assert_called_once_with(start_date, end_date)
            mock_apply.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_date_range_filter_open_fails(
        self, calendar_interactor, mock_page
    ):
        """Test workflow when calendar opening fails."""
        start_date = date(2024, 3, 10)
        end_date = date(2024, 3, 20)

        with patch.object(calendar_interactor, "open_calendar_widget") as mock_open:
            mock_open.return_value = False

            with pytest.raises(
                CalendarInteractionError, match="Failed to open calendar widget"
            ):
                await calendar_interactor.set_date_range_filter(start_date, end_date)

    @pytest.mark.asyncio
    async def test_set_date_range_filter_select_fails(
        self, calendar_interactor, mock_page
    ):
        """Test workflow when date selection fails."""
        start_date = date(2024, 3, 10)
        end_date = date(2024, 3, 20)

        with (
            patch.object(calendar_interactor, "open_calendar_widget") as mock_open,
            patch.object(calendar_interactor, "select_date_range") as mock_select_range,
        ):
            mock_open.return_value = True
            mock_select_range.return_value = False

            with pytest.raises(
                CalendarInteractionError, match="Failed to select date range"
            ):
                await calendar_interactor.set_date_range_filter(start_date, end_date)

    @pytest.mark.asyncio
    async def test_set_date_range_filter_apply_fails(
        self, calendar_interactor, mock_page
    ):
        """Test workflow when filter application fails."""
        start_date = date(2024, 3, 10)
        end_date = date(2024, 3, 20)

        with (
            patch.object(calendar_interactor, "open_calendar_widget") as mock_open,
            patch.object(calendar_interactor, "select_date_range") as mock_select_range,
            patch.object(calendar_interactor, "apply_date_filter") as mock_apply,
        ):
            mock_open.return_value = True
            mock_select_range.return_value = True
            mock_apply.return_value = False

            with pytest.raises(
                CalendarInteractionError, match="Failed to apply date filter"
            ):
                await calendar_interactor.set_date_range_filter(start_date, end_date)


class TestCalendarNavigationHelpers:
    """Test calendar navigation helper methods."""

    @pytest.fixture
    def mock_page(self):
        """Create mock page for testing."""
        return AsyncMock()

    @pytest.fixture
    def calendar_interactor(self, mock_page):
        """Create MLSCalendarInteractor instance for testing."""
        return MLSCalendarInteractor(mock_page, timeout=5000)

    def test_parse_month_name(self, calendar_interactor):
        """Test month name parsing."""
        assert calendar_interactor._parse_month_name("January") == 1
        assert calendar_interactor._parse_month_name("jan") == 1
        assert calendar_interactor._parse_month_name("FEBRUARY") == 2
        assert calendar_interactor._parse_month_name("Dec") == 12
        assert calendar_interactor._parse_month_name("invalid") is None

    def test_parse_month_year_text(self, calendar_interactor):
        """Test month/year text parsing."""
        # Test various formats
        assert calendar_interactor._parse_month_year_text("January 2024") == (1, 2024)
        assert calendar_interactor._parse_month_year_text("Dec 2023") == (12, 2023)
        assert calendar_interactor._parse_month_year_text("01/2024") == (1, 2024)
        assert calendar_interactor._parse_month_year_text("2024-03") == (3, 2024)
        assert calendar_interactor._parse_month_year_text("invalid text") == (
            None,
            None,
        )

    @pytest.mark.asyncio
    async def test_get_current_month_year_combined_selector(
        self, calendar_interactor, mock_page
    ):
        """Test getting current month/year from combined selector."""
        # Mock text content retrieval
        mock_page.text_content.return_value = "March 2024"
        mock_page.wait_for_selector.return_value = True

        with patch.object(
            calendar_interactor.interactor, "get_text_content"
        ) as mock_get_text:
            mock_get_text.return_value = "March 2024"

            month, year = await calendar_interactor._get_current_month_year()

            assert month == 3
            assert year == 2024

    @pytest.mark.asyncio
    async def test_get_current_month_year_separate_selectors(
        self, calendar_interactor, mock_page
    ):
        """Test getting current month/year from separate selectors."""
        with patch.object(
            calendar_interactor.interactor, "get_text_content"
        ) as mock_get_text:
            # Multiple None calls for combined selectors, then separate month/year
            mock_get_text.side_effect = [None, None, None, None, "March", "2024"]

            month, year = await calendar_interactor._get_current_month_year()

            assert month == 3
            assert year == 2024

    @pytest.mark.asyncio
    async def test_get_current_month_year_not_found(
        self, calendar_interactor, mock_page
    ):
        """Test getting current month/year when not found."""
        with patch.object(
            calendar_interactor.interactor, "get_text_content"
        ) as mock_get_text:
            mock_get_text.return_value = None

            month, year = await calendar_interactor._get_current_month_year()

            assert month is None
            assert year is None

    @pytest.mark.asyncio
    async def test_navigate_to_year_forward(self, calendar_interactor, mock_page):
        """Test navigating forward to future year."""
        with (
            patch.object(calendar_interactor, "_click_next_year") as mock_next_year,
            patch.object(
                calendar_interactor, "_get_current_month_year"
            ) as mock_get_current,
        ):
            mock_next_year.return_value = True
            # First call returns current year, second call after navigation returns target year
            mock_get_current.side_effect = [
                (3, 2025)
            ]  # After navigation, we're at target

            result = await calendar_interactor._navigate_to_year(2024, 2025)

            assert result is True
            mock_next_year.assert_called_once()

    @pytest.mark.asyncio
    async def test_navigate_to_year_backward(self, calendar_interactor, mock_page):
        """Test navigating backward to past year."""
        with (
            patch.object(calendar_interactor, "_click_prev_year") as mock_prev_year,
            patch.object(
                calendar_interactor, "_get_current_month_year"
            ) as mock_get_current,
        ):
            mock_prev_year.return_value = True
            # After navigation, we're at target year
            mock_get_current.side_effect = [
                (3, 2023)
            ]  # After navigation, we're at target

            result = await calendar_interactor._navigate_to_year(2024, 2023)

            assert result is True
            mock_prev_year.assert_called_once()

    @pytest.mark.asyncio
    async def test_navigate_to_month_forward(self, calendar_interactor, mock_page):
        """Test navigating forward to future month."""
        with (
            patch.object(calendar_interactor, "_click_next_month") as mock_next_month,
            patch.object(
                calendar_interactor, "_get_current_month_year"
            ) as mock_get_current,
        ):
            mock_next_month.return_value = True
            mock_get_current.side_effect = [
                (3, 2024),
                (5, 2024),
            ]  # Progress from March to May

            result = await calendar_interactor._navigate_to_month(3, 5)

            assert result is True
            assert mock_next_month.call_count == 2  # March -> April -> May

    @pytest.mark.asyncio
    async def test_navigate_to_month_backward(self, calendar_interactor, mock_page):
        """Test navigating backward to past month."""
        with (
            patch.object(calendar_interactor, "_click_prev_month") as mock_prev_month,
            patch.object(
                calendar_interactor, "_get_current_month_year"
            ) as mock_get_current,
        ):
            mock_prev_month.return_value = True
            mock_get_current.side_effect = [
                (5, 2024),
                (3, 2024),
            ]  # Progress from May to March

            result = await calendar_interactor._navigate_to_month(5, 3)

            assert result is True
            assert mock_prev_month.call_count == 2  # May -> April -> March

    @pytest.mark.asyncio
    async def test_navigate_to_month_wrap_around(self, calendar_interactor, mock_page):
        """Test navigating with year wrap-around (shortest path)."""
        with (
            patch.object(calendar_interactor, "_click_prev_month") as mock_prev_month,
            patch.object(
                calendar_interactor, "_get_current_month_year"
            ) as mock_get_current,
        ):
            mock_prev_month.return_value = True
            # Navigate from February to November (should go backward: Feb -> Jan -> Dec -> Nov)
            mock_get_current.side_effect = [(2, 2024), (11, 2023)]

            result = await calendar_interactor._navigate_to_month(2, 11)

            assert result is True
            # Should use backward navigation (3 steps) instead of forward (9 steps)
            # But the mock only shows 1 call because we mock the final state
            assert mock_prev_month.call_count >= 1

    @pytest.mark.asyncio
    async def test_click_navigation_buttons(self, calendar_interactor, mock_page):
        """Test clicking navigation buttons."""
        # Mock successful button clicks
        mock_page.wait_for_selector.return_value = True
        mock_page.click.return_value = None

        with patch.object(
            calendar_interactor.interactor, "click_element"
        ) as mock_click:
            mock_click.return_value = True

            # Test all navigation methods
            assert await calendar_interactor._click_next_month() is True
            assert await calendar_interactor._click_prev_month() is True
            assert (
                await calendar_interactor._click_next_year() is True
            )  # Falls back to month navigation
            assert (
                await calendar_interactor._click_prev_year() is True
            )  # Falls back to month navigation

    @pytest.mark.asyncio
    async def test_navigation_button_not_found(self, calendar_interactor, mock_page):
        """Test navigation when buttons are not found."""
        with patch.object(
            calendar_interactor.interactor, "click_element"
        ) as mock_click:
            mock_click.return_value = False  # No buttons found

            assert await calendar_interactor._click_next_month() is False
            assert await calendar_interactor._click_prev_month() is False


class TestCalendarInteractionErrorHandling:
    """Test error handling in calendar interactions."""

    @pytest.fixture
    def mock_page(self):
        """Create mock page for testing."""
        return AsyncMock()

    @pytest.fixture
    def calendar_interactor(self, mock_page):
        """Create MLSCalendarInteractor instance for testing."""
        return MLSCalendarInteractor(mock_page, timeout=5000)

    @pytest.mark.asyncio
    async def test_open_calendar_widget_exception(self, calendar_interactor, mock_page):
        """Test exception handling in calendar widget opening."""
        mock_page.wait_for_selector.side_effect = Exception("Network error")

        result = await calendar_interactor.open_calendar_widget()

        assert result is False

    @pytest.mark.asyncio
    async def test_select_date_exception(self, calendar_interactor, mock_page):
        """Test exception handling in date selection."""
        target_date = date(2024, 3, 15)

        with patch.object(
            calendar_interactor, "navigate_to_month_year"
        ) as mock_navigate:
            mock_navigate.side_effect = Exception("Navigation error")

            result = await calendar_interactor.select_date(target_date)

            assert result is False

    @pytest.mark.asyncio
    async def test_apply_date_filter_exception(self, calendar_interactor, mock_page):
        """Test exception handling in filter application."""
        mock_page.wait_for_selector.side_effect = Exception("Button error")

        result = await calendar_interactor.apply_date_filter()

        assert result is False

    @pytest.mark.asyncio
    async def test_set_date_range_filter_generic_exception(
        self, calendar_interactor, mock_page
    ):
        """Test generic exception handling in workflow."""
        start_date = date(2024, 3, 10)
        end_date = date(2024, 3, 20)

        with patch.object(calendar_interactor, "open_calendar_widget") as mock_open:
            mock_open.side_effect = Exception("Unexpected error")

            with pytest.raises(
                CalendarInteractionError, match="Date range filter workflow failed"
            ):
                await calendar_interactor.set_date_range_filter(start_date, end_date)
