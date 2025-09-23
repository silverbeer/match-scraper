"""
Unit tests for MLS website filter application functionality.

Tests filter application methods, validation, error handling, and result loading.
"""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from src.scraper.browser import ElementInteractor
from src.scraper.config import ScrapingConfig
from src.scraper.filter_application import FilterApplicationError, MLSFilterApplicator


class TestMLSFilterApplicator:
    """Test cases for MLSFilterApplicator class."""

    @pytest.fixture
    def mock_page(self):
        """Create a mock Playwright page."""
        page = AsyncMock()
        page.query_selector_all = AsyncMock()
        return page

    @pytest.fixture
    def mock_interactor(self):
        """Create a mock ElementInteractor."""
        interactor = AsyncMock(spec=ElementInteractor)
        return interactor

    @pytest.fixture
    def filter_applicator(self, mock_page):
        """Create MLSFilterApplicator instance with mocked dependencies."""
        return MLSFilterApplicator(mock_page, timeout=5000)

    @pytest.fixture
    def sample_config(self):
        """Create a sample ScrapingConfig for testing."""
        return ScrapingConfig(
            age_group="U14",
            club="Test Club",
            competition="Test Competition",
            division="Northeast",
            look_back_days=1,
            start_date=date.today(),
            end_date=date.today(),
            missing_table_api_url="https://api.example.com",
            missing_table_api_key="test-key",
            log_level="INFO",
        )

    @pytest.mark.asyncio
    async def test_init(self, mock_page):
        """Test MLSFilterApplicator initialization."""
        applicator = MLSFilterApplicator(mock_page, timeout=10000)

        assert applicator.page == mock_page
        assert applicator.timeout == 10000
        assert isinstance(applicator.interactor, ElementInteractor)
        assert applicator._available_options == {}

    @pytest.mark.asyncio
    async def test_discover_available_options_success(
        self, filter_applicator, mock_page
    ):
        """Test successful discovery of available filter options."""
        # Mock the _get_iframe_content method to return None so it uses hardcoded fallback
        with patch.object(filter_applicator, "_get_iframe_content", return_value=None):
            options = await filter_applicator.discover_available_options()

        assert "age_group" in options
        assert "U14" in options["age_group"]
        assert "division" in options
        # Update assertion to match actual hardcoded values
        assert "Homegrown Division" in options["division"]
        assert "Academy Division" in options["division"]
        assert len(options["club"]) == 0
        assert len(options["competition"]) == 0

    @pytest.mark.asyncio
    async def test_discover_available_options_no_elements(self, filter_applicator):
        """Test discovery when no filter elements are found."""
        # Mock _get_iframe_content to return None to trigger the fallback logic
        with patch.object(filter_applicator, "_get_iframe_content", return_value=None):
            options = await filter_applicator.discover_available_options()

        # When iframe is not accessible, it falls back to hardcoded values
        # So we expect age_group and division to have values, but club and competition to be empty
        assert len(options["age_group"]) > 0  # Should have hardcoded age groups
        assert len(options["division"]) > 0  # Should have hardcoded divisions
        assert len(options["club"]) == 0  # Should be empty
        assert len(options["competition"]) == 0  # Should be empty

    @pytest.mark.asyncio
    async def test_apply_age_group_filter_success(self, filter_applicator):
        """Test successful age group filter application."""
        # Create properly mocked iframe content and select element
        mock_iframe_content = AsyncMock()
        mock_select = AsyncMock()

        # Mock the async methods that the implementation actually calls
        mock_select.count = AsyncMock(return_value=1)
        mock_select.select_option = AsyncMock(return_value=None)
        mock_iframe_content.locator = AsyncMock(return_value=mock_select)

        with patch.object(
            filter_applicator, "_get_iframe_content", return_value=mock_iframe_content
        ):
            result = await filter_applicator.apply_age_group_filter("U14")

            assert result is True
            # Verify the expected method calls were made
            mock_iframe_content.locator.assert_called_with("select[js-age]")
            mock_select.count.assert_called_once()
            mock_select.select_option.assert_called_once_with(value="22")

    @pytest.mark.asyncio
    async def test_apply_age_group_filter_empty_value(self, filter_applicator):
        """Test age group filter with empty value."""
        result = await filter_applicator.apply_age_group_filter("")
        assert result is True  # Empty values should be accepted

    @pytest.mark.asyncio
    async def test_apply_age_group_filter_invalid_value(self, filter_applicator):
        """Test age group filter with invalid value."""
        with patch.object(
            filter_applicator, "_validate_filter_option", return_value=False
        ):
            result = await filter_applicator.apply_age_group_filter("InvalidAge")
            assert result is False

    @pytest.mark.asyncio
    async def test_apply_age_group_filter_no_element_found(self, filter_applicator):
        """Test age group filter when no dropdown element is found."""
        # Mock iframe content returning None to simulate iframe access failure
        with (
            patch.object(
                filter_applicator, "_validate_filter_option", return_value=True
            ),
            patch.object(filter_applicator, "_get_iframe_content", return_value=None),
        ):
            result = await filter_applicator.apply_age_group_filter("U14")
            assert result is False

    @pytest.mark.asyncio
    async def test_apply_club_filter_success(self, filter_applicator):
        """Test successful club filter application."""
        with (
            patch.object(
                filter_applicator, "_validate_filter_option", return_value=True
            ),
            patch.object(
                filter_applicator.interactor, "wait_for_element", return_value=True
            ),
            patch.object(
                filter_applicator.interactor,
                "select_dropdown_option",
                return_value=True,
            ),
        ):
            result = await filter_applicator.apply_club_filter("Test Club")
            assert result is True

    @pytest.mark.asyncio
    async def test_apply_club_filter_empty_value(self, filter_applicator):
        """Test club filter with empty value."""
        result = await filter_applicator.apply_club_filter("")
        assert result is True

    @pytest.mark.asyncio
    async def test_apply_competition_filter_success(self, filter_applicator):
        """Test successful competition filter application."""
        with (
            patch.object(
                filter_applicator, "_validate_filter_option", return_value=True
            ),
            patch.object(
                filter_applicator.interactor, "wait_for_element", return_value=True
            ),
            patch.object(
                filter_applicator.interactor,
                "select_dropdown_option",
                return_value=True,
            ),
        ):
            result = await filter_applicator.apply_competition_filter(
                "Test Competition"
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_apply_division_filter_success(self, filter_applicator):
        """Test successful division filter application."""
        with (
            patch.object(
                filter_applicator, "_validate_filter_option", return_value=True
            ),
            patch.object(
                filter_applicator.interactor, "wait_for_element", return_value=True
            ),
            patch.object(
                filter_applicator.interactor,
                "select_dropdown_option",
                return_value=True,
            ),
        ):
            result = await filter_applicator.apply_division_filter("Northeast")
            assert result is True

    @pytest.mark.asyncio
    async def test_apply_all_filters_success(self, filter_applicator, sample_config):
        """Test successful application of all filters."""
        with (
            patch.object(
                filter_applicator, "discover_available_options", return_value={}
            ),
            patch.object(
                filter_applicator, "apply_age_group_filter", return_value=True
            ),
            patch.object(filter_applicator, "apply_club_filter", return_value=True),
            patch.object(
                filter_applicator, "apply_competition_filter", return_value=True
            ),
            patch.object(filter_applicator, "apply_division_filter", return_value=True),
            patch.object(
                filter_applicator, "wait_for_filter_results", return_value=True
            ),
        ):
            result = await filter_applicator.apply_all_filters(sample_config)
            assert result is True

    @pytest.mark.asyncio
    async def test_apply_all_filters_age_group_failure(
        self, filter_applicator, sample_config
    ):
        """Test apply_all_filters when age group filter fails."""
        with (
            patch.object(
                filter_applicator, "discover_available_options", return_value={}
            ),
            patch.object(
                filter_applicator, "apply_age_group_filter", return_value=False
            ),
        ):
            result = await filter_applicator.apply_all_filters(sample_config)
            assert result is False

    @pytest.mark.asyncio
    async def test_apply_all_filters_club_failure(
        self, filter_applicator, sample_config
    ):
        """Test apply_all_filters when club filter fails."""
        with (
            patch.object(
                filter_applicator, "discover_available_options", return_value={}
            ),
            patch.object(
                filter_applicator, "apply_age_group_filter", return_value=True
            ),
            patch.object(filter_applicator, "apply_club_filter", return_value=False),
        ):
            result = await filter_applicator.apply_all_filters(sample_config)
            assert result is False

    @pytest.mark.asyncio
    async def test_wait_for_filter_results_success(self, filter_applicator):
        """Test successful waiting for filter results."""
        with patch.object(
            filter_applicator.interactor, "wait_for_element"
        ) as mock_wait:
            # Mock: loading indicators not found, then results container found
            def mock_wait_side_effect(selector, timeout=None, state="visible"):
                if "loading" in selector or "spinner" in selector:
                    return False  # No loading indicators
                elif "results" in selector or "matches" in selector:
                    return True  # Results container found
                return False

            mock_wait.side_effect = mock_wait_side_effect

            result = await filter_applicator.wait_for_filter_results()
            assert result is True

    @pytest.mark.asyncio
    async def test_wait_for_filter_results_no_results_container(
        self, filter_applicator
    ):
        """Test waiting for results when no results container is found."""
        with patch.object(
            filter_applicator.interactor, "wait_for_element", return_value=False
        ):
            result = await filter_applicator.wait_for_filter_results()
            assert result is True  # Should still return True with generic wait

    @pytest.mark.asyncio
    async def test_validate_filters_success(self, filter_applicator, sample_config):
        """Test successful filter validation."""
        with (
            patch.object(
                filter_applicator, "discover_available_options", return_value={}
            ),
            patch.object(
                filter_applicator, "_validate_filter_option", return_value=True
            ),
        ):
            results = await filter_applicator.validate_filters(sample_config)

            assert all(results.values())
            assert len(results) == 4

    @pytest.mark.asyncio
    async def test_validate_filters_mixed_results(
        self, filter_applicator, sample_config
    ):
        """Test filter validation with mixed results."""

        def mock_validate(filter_type, value):
            return filter_type in ["age_group", "division"]

        with (
            patch.object(
                filter_applicator, "discover_available_options", return_value={}
            ),
            patch.object(
                filter_applicator, "_validate_filter_option", side_effect=mock_validate
            ),
        ):
            results = await filter_applicator.validate_filters(sample_config)

            assert results["age_group"] is True
            assert results["division"] is True
            assert results["club"] is False
            assert results["competition"] is False

    @pytest.mark.asyncio
    async def test_get_dropdown_options_success(self, filter_applicator, mock_page):
        """Test successful dropdown options retrieval."""
        # Mock option elements
        mock_option1 = AsyncMock()
        mock_option1.get_attribute.return_value = "U14"
        mock_option1.text_content.return_value = "U14"

        mock_option2 = AsyncMock()
        mock_option2.get_attribute.return_value = "U15"
        mock_option2.text_content.return_value = "U15"

        mock_page.query_selector_all.return_value = [mock_option1, mock_option2]

        with patch.object(
            filter_applicator.interactor, "wait_for_element", return_value=True
        ):
            options = await filter_applicator._get_dropdown_options(
                ['select[name="test"]']
            )

            assert "U14" in options
            assert "U15" in options
            assert len(options) == 2

    @pytest.mark.asyncio
    async def test_get_dropdown_options_no_element(self, filter_applicator):
        """Test dropdown options retrieval when no element is found."""
        with patch.object(
            filter_applicator.interactor, "wait_for_element", return_value=False
        ):
            options = await filter_applicator._get_dropdown_options(
                ['select[name="test"]']
            )
            assert options == []

    @pytest.mark.asyncio
    async def test_get_dropdown_options_filters_empty_values(
        self, filter_applicator, mock_page
    ):
        """Test that empty and placeholder values are filtered out."""
        # Mock option elements with various values
        mock_options = []
        values = ["", "all", "select", "choose", "U14", "Northeast"]

        for value in values:
            mock_option = AsyncMock()
            mock_option.get_attribute.return_value = value
            mock_option.text_content.return_value = value
            mock_options.append(mock_option)

        mock_page.query_selector_all.return_value = mock_options

        with patch.object(
            filter_applicator.interactor, "wait_for_element", return_value=True
        ):
            options = await filter_applicator._get_dropdown_options(
                ['select[name="test"]']
            )

            assert "U14" in options
            assert "Northeast" in options
            assert "" not in options
            assert "all" not in options
            assert "select" not in options
            assert "choose" not in options

    @pytest.mark.asyncio
    async def test_validate_filter_option_empty_value(self, filter_applicator):
        """Test validation of empty filter values."""
        result = await filter_applicator._validate_filter_option("age_group", "")
        assert result is True

        result = await filter_applicator._validate_filter_option("age_group", "   ")
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_filter_option_with_discovered_options(
        self, filter_applicator
    ):
        """Test validation using discovered options."""
        filter_applicator._available_options = {"age_group": {"U14", "U15", "U16"}}

        result = await filter_applicator._validate_filter_option("age_group", "U14")
        assert result is True

        result = await filter_applicator._validate_filter_option("age_group", "U99")
        assert result is False

    @pytest.mark.asyncio
    async def test_validate_filter_option_case_insensitive(self, filter_applicator):
        """Test case-insensitive validation."""
        filter_applicator._available_options = {"age_group": {"U14", "U15"}}

        result = await filter_applicator._validate_filter_option("age_group", "u14")
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_filter_option_hardcoded_age_group(self, filter_applicator):
        """Test validation using hardcoded age group values."""
        # No discovered options, should fall back to hardcoded
        result = await filter_applicator._validate_filter_option("age_group", "U14")
        assert result is True

        result = await filter_applicator._validate_filter_option("age_group", "U99")
        assert result is False

    @pytest.mark.asyncio
    async def test_validate_filter_option_hardcoded_division(self, filter_applicator):
        """Test validation using hardcoded division values."""
        result = await filter_applicator._validate_filter_option(
            "division", "Northeast"
        )
        assert result is True

        result = await filter_applicator._validate_filter_option(
            "division", "InvalidDivision"
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_validate_filter_option_club_competition_fallback(
        self, filter_applicator
    ):
        """Test validation for club and competition with fallback logic."""
        # For club and competition, any non-empty value should be valid if no options discovered
        result = await filter_applicator._validate_filter_option("club", "Any Club")
        assert result is True

        result = await filter_applicator._validate_filter_option(
            "competition", "Any Competition"
        )
        assert result is True

        result = await filter_applicator._validate_filter_option("club", "")
        assert result is True

    @pytest.mark.asyncio
    async def test_error_handling_in_apply_age_group_filter(self, filter_applicator):
        """Test error handling in apply_age_group_filter."""
        with patch.object(
            filter_applicator,
            "_validate_filter_option",
            side_effect=Exception("Test error"),
        ):
            result = await filter_applicator.apply_age_group_filter("U14")
            assert result is False

    @pytest.mark.asyncio
    async def test_error_handling_in_discover_available_options(
        self, filter_applicator
    ):
        """Test error handling in discover_available_options."""
        with patch.object(
            filter_applicator,
            "_get_dropdown_options",
            side_effect=Exception("Test error"),
        ):
            options = await filter_applicator.discover_available_options()
            assert options == {}

    @pytest.mark.asyncio
    async def test_error_handling_in_validate_filters(
        self, filter_applicator, sample_config
    ):
        """Test error handling in validate_filters."""
        with patch.object(
            filter_applicator,
            "discover_available_options",
            side_effect=Exception("Test error"),
        ):
            results = await filter_applicator.validate_filters(sample_config)
            assert all(not result for result in results.values())

    @pytest.mark.asyncio
    async def test_multiple_selector_fallback(self, filter_applicator):
        """Test that multiple selectors are tried in order."""
        with patch.object(
            filter_applicator, "_validate_filter_option", return_value=True
        ):
            # Mock first selector failing, second succeeding
            def mock_wait_for_element(selector, timeout=None):
                return selector == 'select[name*="age" i]'

            with (
                patch.object(
                    filter_applicator.interactor,
                    "wait_for_element",
                    side_effect=mock_wait_for_element,
                ),
                patch.object(
                    filter_applicator.interactor,
                    "select_dropdown_option",
                    return_value=True,
                ),
            ):
                result = await filter_applicator.apply_age_group_filter("U14")
                assert result is True

    @pytest.mark.asyncio
    async def test_filter_application_with_delays(
        self, filter_applicator, sample_config
    ):
        """Test that delays are properly applied between filter applications."""
        with (
            patch("asyncio.sleep") as mock_sleep,
            patch.object(
                filter_applicator, "discover_available_options", return_value={}
            ),
            patch.object(
                filter_applicator, "apply_age_group_filter", return_value=True
            ),
            patch.object(filter_applicator, "apply_club_filter", return_value=True),
            patch.object(
                filter_applicator, "apply_competition_filter", return_value=True
            ),
            patch.object(filter_applicator, "apply_division_filter", return_value=True),
            patch.object(
                filter_applicator, "wait_for_filter_results", return_value=True
            ),
        ):
            await filter_applicator.apply_all_filters(sample_config)

            # Should have 3 sleep calls (between the 4 filter applications)
            assert mock_sleep.call_count == 3
            mock_sleep.assert_called_with(0.5)


class TestFilterApplicationError:
    """Test cases for FilterApplicationError exception."""

    def test_filter_application_error_creation(self):
        """Test FilterApplicationError creation."""
        error = FilterApplicationError("Test error message")
        assert str(error) == "Test error message"
        assert isinstance(error, Exception)

    def test_filter_application_error_with_cause(self):
        """Test FilterApplicationError with underlying cause."""
        original_error = ValueError("Original error")
        try:
            raise FilterApplicationError("Wrapper error") from original_error
        except FilterApplicationError as error:
            assert str(error) == "Wrapper error"
            assert error.__cause__ == original_error


# Integration-style tests
class TestMLSFilterApplicatorIntegration:
    """Integration-style tests for MLSFilterApplicator."""

    @pytest.fixture
    def mock_page_with_elements(self):
        """Create a mock page with realistic element interactions."""
        page = AsyncMock()

        # Mock successful element finding and interaction
        async def mock_query_selector_all(selector):
            if "age" in selector:
                mock_option = AsyncMock()
                mock_option.get_attribute.return_value = "U14"
                mock_option.text_content.return_value = "U14"
                return [mock_option]
            return []

        page.query_selector_all = mock_query_selector_all
        return page

    @pytest.fixture
    def sample_config(self):
        """Create a sample ScrapingConfig for testing."""
        return ScrapingConfig(
            age_group="U14",
            club="Test Club",
            competition="Test Competition",
            division="Northeast",
            look_back_days=1,
            start_date=date.today(),
            end_date=date.today(),
            missing_table_api_url="https://api.example.com",
            missing_table_api_key="test-key",
            log_level="INFO",
        )

    @pytest.mark.asyncio
    async def test_complete_filter_workflow(
        self, mock_page_with_elements, sample_config
    ):
        """Test complete filter application workflow."""
        applicator = MLSFilterApplicator(mock_page_with_elements)

        with (
            patch.object(applicator.interactor, "wait_for_element", return_value=True),
            patch.object(
                applicator.interactor, "select_dropdown_option", return_value=True
            ),
        ):
            # Test the complete workflow
            validation_results = await applicator.validate_filters(sample_config)
            assert isinstance(validation_results, dict)

            filter_success = await applicator.apply_all_filters(sample_config)
            assert filter_success is True

    @pytest.mark.asyncio
    async def test_realistic_error_scenarios(
        self, mock_page_with_elements, sample_config
    ):
        """Test realistic error scenarios."""
        applicator = MLSFilterApplicator(mock_page_with_elements)

        # Test scenario where elements are found but interaction fails
        with (
            patch.object(applicator.interactor, "wait_for_element", return_value=True),
            patch.object(
                applicator.interactor, "select_dropdown_option", return_value=False
            ),
        ):
            result = await applicator.apply_age_group_filter("U14")
            assert result is False
