"""
Unit tests for browser automation functionality.

Tests browser initialization, page navigation, element interaction,
and resource cleanup with mocked Playwright interactions.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from src.scraper.browser import (
    BrowserConfig,
    BrowserManager,
    ElementInteractor,
    PageNavigator,
    get_browser_manager,
)


class TestBrowserConfig:
    """Test BrowserConfig class."""

    def test_default_config(self):
        """Test default configuration values."""
        config = BrowserConfig()

        assert config.headless is True
        assert config.timeout == 30000
        assert config.viewport_width == 1280
        assert config.viewport_height == 720
        assert "Mozilla/5.0" in config.user_agent
        assert "Chrome" in config.user_agent

    def test_custom_config(self):
        """Test custom configuration values."""
        config = BrowserConfig(
            headless=False,
            timeout=60000,
            viewport_width=1920,
            viewport_height=1080,
            user_agent="Custom User Agent",
        )

        assert config.headless is False
        assert config.timeout == 60000
        assert config.viewport_width == 1920
        assert config.viewport_height == 1080
        assert config.user_agent == "Custom User Agent"


class TestBrowserManager:
    """Test BrowserManager class."""

    @pytest.fixture
    def browser_manager(self):
        """Create BrowserManager instance for testing."""
        return BrowserManager()

    @pytest.fixture
    def mock_playwright(self):
        """Create mock Playwright objects."""
        mock_playwright = AsyncMock()
        mock_browser = AsyncMock()
        mock_context = AsyncMock()

        mock_playwright.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context

        return {
            "playwright": mock_playwright,
            "browser": mock_browser,
            "context": mock_context,
        }

    @pytest.mark.asyncio
    async def test_initialize_success(self, browser_manager, mock_playwright):
        """Test successful browser initialization."""
        with patch("src.scraper.browser.async_playwright") as mock_async_playwright:
            # Mock the async_playwright() call to return an object with start() method
            mock_playwright_instance = AsyncMock()
            mock_playwright_instance.start.return_value = mock_playwright["playwright"]
            mock_async_playwright.return_value = mock_playwright_instance

            await browser_manager.initialize()

            # Verify Playwright was started
            mock_async_playwright.return_value.start.assert_called_once()

            # Verify browser was launched with correct args
            mock_playwright["playwright"].chromium.launch.assert_called_once()
            launch_args = mock_playwright["playwright"].chromium.launch.call_args
            assert launch_args.kwargs["headless"] is True
            assert "--no-sandbox" in launch_args.kwargs["args"]
            assert "--disable-setuid-sandbox" in launch_args.kwargs["args"]

            # Verify context was created
            mock_playwright["browser"].new_context.assert_called_once()
            context_args = mock_playwright["browser"].new_context.call_args
            assert context_args.kwargs["viewport"]["width"] == 1280
            assert context_args.kwargs["viewport"]["height"] == 720

            # Verify timeout was set
            mock_playwright["context"].set_default_timeout.assert_called_once_with(
                30000
            )

    @pytest.mark.asyncio
    async def test_initialize_failure(self, browser_manager):
        """Test browser initialization failure."""
        with patch("src.scraper.browser.async_playwright") as mock_async_playwright:
            mock_playwright_instance = AsyncMock()
            mock_playwright_instance.start.side_effect = Exception(
                "Browser launch failed"
            )
            mock_async_playwright.return_value = mock_playwright_instance

            with pytest.raises(Exception, match="Browser launch failed"):
                await browser_manager.initialize()

    @pytest.mark.asyncio
    async def test_new_page_success(self, browser_manager, mock_playwright):
        """Test successful page creation."""
        mock_page = AsyncMock()
        mock_playwright["context"].new_page.return_value = mock_page

        with patch("src.scraper.browser.async_playwright") as mock_async_playwright:
            mock_playwright_instance = AsyncMock()
            mock_playwright_instance.start.return_value = mock_playwright["playwright"]
            mock_async_playwright.return_value = mock_playwright_instance

            await browser_manager.initialize()
            page = await browser_manager.new_page()

            assert page == mock_page
            mock_playwright["context"].new_page.assert_called_once()

    @pytest.mark.asyncio
    async def test_new_page_not_initialized(self, browser_manager):
        """Test page creation when browser not initialized."""
        with pytest.raises(RuntimeError, match="Browser not initialized"):
            await browser_manager.new_page()

    @pytest.mark.asyncio
    async def test_cleanup_success(self, browser_manager, mock_playwright):
        """Test successful browser cleanup."""
        with patch("src.scraper.browser.async_playwright") as mock_async_playwright:
            mock_playwright_instance = AsyncMock()
            mock_playwright_instance.start.return_value = mock_playwright["playwright"]
            mock_async_playwright.return_value = mock_playwright_instance

            await browser_manager.initialize()
            await browser_manager.cleanup()

            # Verify cleanup order
            mock_playwright["context"].close.assert_called_once()
            mock_playwright["browser"].close.assert_called_once()
            mock_playwright["playwright"].stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_with_errors(self, browser_manager, mock_playwright):
        """Test cleanup with errors (should not raise)."""
        mock_playwright["context"].close.side_effect = Exception("Context close error")

        with patch("src.scraper.browser.async_playwright") as mock_async_playwright:
            mock_playwright_instance = AsyncMock()
            mock_playwright_instance.start.return_value = mock_playwright["playwright"]
            mock_async_playwright.return_value = mock_playwright_instance

            await browser_manager.initialize()
            # Should not raise exception
            await browser_manager.cleanup()

    @pytest.mark.asyncio
    async def test_get_page_context_manager(self, browser_manager, mock_playwright):
        """Test page context manager."""
        mock_page = AsyncMock()
        mock_playwright["context"].new_page.return_value = mock_page

        with patch("src.scraper.browser.async_playwright") as mock_async_playwright:
            mock_playwright_instance = AsyncMock()
            mock_playwright_instance.start.return_value = mock_playwright["playwright"]
            mock_async_playwright.return_value = mock_playwright_instance

            await browser_manager.initialize()

            async with browser_manager.get_page() as page:
                assert page == mock_page

            # Verify page was closed
            mock_page.close.assert_called_once()


class TestPageNavigator:
    """Test PageNavigator class."""

    @pytest.fixture
    def mock_page(self):
        """Create mock page for testing."""
        return AsyncMock()

    @pytest.fixture
    def navigator(self, mock_page):
        """Create PageNavigator instance for testing."""
        return PageNavigator(mock_page, max_retries=2, retry_delay=0.1)

    @pytest.mark.asyncio
    async def test_navigate_success(self, navigator, mock_page):
        """Test successful navigation."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status = 200
        mock_page.goto.return_value = mock_response

        result = await navigator.navigate_to("https://example.com")

        assert result is True
        mock_page.goto.assert_called_once_with(
            "https://example.com", wait_until="networkidle"
        )

    @pytest.mark.asyncio
    async def test_navigate_custom_wait_until(self, navigator, mock_page):
        """Test navigation with custom wait_until."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status = 200
        mock_page.goto.return_value = mock_response

        result = await navigator.navigate_to("https://example.com", wait_until="load")

        assert result is True
        mock_page.goto.assert_called_once_with("https://example.com", wait_until="load")

    @pytest.mark.asyncio
    async def test_navigate_non_ok_response(self, navigator, mock_page):
        """Test navigation with non-OK response."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status = 404
        mock_page.goto.return_value = mock_response

        result = await navigator.navigate_to("https://example.com")

        assert result is False

    @pytest.mark.asyncio
    async def test_navigate_timeout_with_retry(self, navigator, mock_page):
        """Test navigation timeout with retry logic."""
        mock_page.goto.side_effect = [
            PlaywrightTimeoutError("Timeout"),
            PlaywrightTimeoutError("Timeout"),
            MagicMock(ok=True, status=200),
        ]

        result = await navigator.navigate_to("https://example.com")

        assert result is True
        assert mock_page.goto.call_count == 3

    @pytest.mark.asyncio
    async def test_navigate_max_retries_exceeded(self, navigator, mock_page):
        """Test navigation failing after max retries."""
        mock_page.goto.side_effect = PlaywrightTimeoutError("Timeout")

        result = await navigator.navigate_to("https://example.com")

        assert result is False
        assert mock_page.goto.call_count == 3  # Initial + 2 retries

    @pytest.mark.asyncio
    async def test_navigate_exception_with_retry(self, navigator, mock_page):
        """Test navigation exception with retry logic."""
        mock_page.goto.side_effect = [
            Exception("Network error"),
            MagicMock(ok=True, status=200),
        ]

        result = await navigator.navigate_to("https://example.com")

        assert result is True
        assert mock_page.goto.call_count == 2


class TestElementInteractor:
    """Test ElementInteractor class."""

    @pytest.fixture
    def mock_page(self):
        """Create mock page for testing."""
        return AsyncMock()

    @pytest.fixture
    def interactor(self, mock_page):
        """Create ElementInteractor instance for testing."""
        return ElementInteractor(mock_page, default_timeout=5000)

    @pytest.mark.asyncio
    async def test_wait_for_element_success(self, interactor, mock_page):
        """Test successful element waiting."""
        mock_page.wait_for_selector.return_value = None

        result = await interactor.wait_for_element("#test-element")

        assert result is True
        mock_page.wait_for_selector.assert_called_once_with(
            "#test-element", timeout=5000, state="visible"
        )

    @pytest.mark.asyncio
    async def test_wait_for_element_timeout(self, interactor, mock_page):
        """Test element waiting timeout."""
        mock_page.wait_for_selector.side_effect = PlaywrightTimeoutError("Timeout")

        result = await interactor.wait_for_element("#test-element")

        assert result is False

    @pytest.mark.asyncio
    async def test_wait_for_element_custom_params(self, interactor, mock_page):
        """Test element waiting with custom parameters."""
        mock_page.wait_for_selector.return_value = None

        result = await interactor.wait_for_element(
            "#test-element", timeout=10000, state="attached"
        )

        assert result is True
        mock_page.wait_for_selector.assert_called_once_with(
            "#test-element", timeout=10000, state="attached"
        )

    @pytest.mark.asyncio
    async def test_click_element_success(self, interactor, mock_page):
        """Test successful element clicking."""
        mock_page.wait_for_selector.return_value = None
        mock_page.click.return_value = None

        result = await interactor.click_element("#test-button")

        assert result is True
        mock_page.wait_for_selector.assert_called_once()
        mock_page.click.assert_called_once_with(
            "#test-button", timeout=5000, force=False
        )

    @pytest.mark.asyncio
    async def test_click_element_not_found(self, interactor, mock_page):
        """Test clicking element that's not found."""
        mock_page.wait_for_selector.side_effect = PlaywrightTimeoutError("Timeout")

        result = await interactor.click_element("#test-button")

        assert result is False
        mock_page.click.assert_not_called()

    @pytest.mark.asyncio
    async def test_click_element_force(self, interactor, mock_page):
        """Test force clicking element."""
        mock_page.wait_for_selector.return_value = None
        mock_page.click.return_value = None

        result = await interactor.click_element("#test-button", force=True)

        assert result is True
        mock_page.click.assert_called_once_with(
            "#test-button", timeout=5000, force=True
        )

    @pytest.mark.asyncio
    async def test_fill_input_success(self, interactor, mock_page):
        """Test successful input filling."""
        mock_page.wait_for_selector.return_value = None
        mock_page.fill.return_value = None

        result = await interactor.fill_input("#test-input", "test value")

        assert result is True
        mock_page.fill.assert_any_call("#test-input", "")  # Clear first
        mock_page.fill.assert_any_call("#test-input", "test value", timeout=5000)

    @pytest.mark.asyncio
    async def test_fill_input_no_clear(self, interactor, mock_page):
        """Test input filling without clearing first."""
        mock_page.wait_for_selector.return_value = None
        mock_page.fill.return_value = None

        result = await interactor.fill_input(
            "#test-input", "test value", clear_first=False
        )

        assert result is True
        # Should only be called once (not clearing first)
        mock_page.fill.assert_called_once_with(
            "#test-input", "test value", timeout=5000
        )

    @pytest.mark.asyncio
    async def test_select_dropdown_option_success(self, interactor, mock_page):
        """Test successful dropdown selection."""
        mock_page.wait_for_selector.return_value = None
        mock_page.select_option.return_value = None

        result = await interactor.select_dropdown_option("#test-select", "option1")

        assert result is True
        mock_page.select_option.assert_called_once_with(
            "#test-select", "option1", timeout=5000
        )

    @pytest.mark.asyncio
    async def test_select_dropdown_multiple_options(self, interactor, mock_page):
        """Test dropdown selection with multiple options."""
        mock_page.wait_for_selector.return_value = None
        mock_page.select_option.return_value = None

        options = ["option1", "option2"]
        result = await interactor.select_dropdown_option("#test-select", options)

        assert result is True
        mock_page.select_option.assert_called_once_with(
            "#test-select", options, timeout=5000
        )

    @pytest.mark.asyncio
    async def test_get_text_content_success(self, interactor, mock_page):
        """Test successful text content retrieval."""
        mock_page.wait_for_selector.return_value = None
        mock_page.text_content.return_value = "Test content"

        result = await interactor.get_text_content("#test-element")

        assert result == "Test content"
        mock_page.text_content.assert_called_once_with("#test-element", timeout=5000)

    @pytest.mark.asyncio
    async def test_get_text_content_not_found(self, interactor, mock_page):
        """Test text content retrieval when element not found."""
        mock_page.wait_for_selector.side_effect = PlaywrightTimeoutError("Timeout")

        result = await interactor.get_text_content("#test-element")

        assert result is None
        mock_page.text_content.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_elements_text_success(self, interactor, mock_page):
        """Test successful multiple elements text retrieval."""
        mock_element1 = AsyncMock()
        mock_element1.text_content.return_value = "Text 1"
        mock_element2 = AsyncMock()
        mock_element2.text_content.return_value = "  Text 2  "
        mock_element3 = AsyncMock()
        mock_element3.text_content.return_value = None

        mock_page.wait_for_selector.return_value = None
        mock_page.query_selector_all.return_value = [
            mock_element1,
            mock_element2,
            mock_element3,
        ]

        result = await interactor.get_elements_text(".test-elements")

        assert result == ["Text 1", "Text 2"]  # Stripped and filtered
        mock_page.query_selector_all.assert_called_once_with(".test-elements")

    @pytest.mark.asyncio
    async def test_get_elements_text_no_elements(self, interactor, mock_page):
        """Test multiple elements text retrieval when no elements found."""
        mock_page.wait_for_selector.side_effect = PlaywrightTimeoutError("Timeout")

        result = await interactor.get_elements_text(".test-elements")

        assert result == []
        mock_page.query_selector_all.assert_not_called()


class TestGetBrowserManager:
    """Test get_browser_manager context manager."""

    @pytest.mark.asyncio
    async def test_context_manager_success(self):
        """Test successful context manager usage."""
        with patch("src.scraper.browser.BrowserManager") as MockBrowserManager:
            mock_manager = AsyncMock()
            MockBrowserManager.return_value = mock_manager

            async with get_browser_manager() as browser_manager:
                assert browser_manager == mock_manager

            # Verify initialization and cleanup were called
            mock_manager.initialize.assert_called_once()
            mock_manager.cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager_with_config(self):
        """Test context manager with custom config."""
        config = BrowserConfig(headless=False)

        with patch("src.scraper.browser.BrowserManager") as MockBrowserManager:
            mock_manager = AsyncMock()
            MockBrowserManager.return_value = mock_manager

            async with get_browser_manager(config) as browser_manager:
                assert browser_manager == mock_manager

            # Verify manager was created with config
            MockBrowserManager.assert_called_once_with(config)

    @pytest.mark.asyncio
    async def test_context_manager_cleanup_on_exception(self):
        """Test context manager cleanup when exception occurs."""
        with patch("src.scraper.browser.BrowserManager") as MockBrowserManager:
            mock_manager = AsyncMock()
            MockBrowserManager.return_value = mock_manager

            with pytest.raises(ValueError):
                async with get_browser_manager():
                    raise ValueError("Test exception")

            # Verify cleanup was still called
            mock_manager.cleanup.assert_called_once()
