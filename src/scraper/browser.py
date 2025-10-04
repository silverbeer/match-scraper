"""
Browser automation utilities using Playwright for MLS website scraping.

This module provides browser initialization, page navigation, element interaction,
and resource cleanup functionality optimized for containerized execution.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Optional, Union

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from ..utils.logger import get_logger

logger = get_logger()


class BrowserConfig:
    """Configuration for browser initialization."""

    def __init__(
        self,
        headless: bool = True,
        timeout: int = 30000,  # 30 seconds
        viewport_width: int = 1280,
        viewport_height: int = 720,
        user_agent: Optional[str] = None,
    ):
        self.headless = headless
        self.timeout = timeout
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.user_agent = user_agent or (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )


class BrowserManager:
    """
    Manages Playwright browser lifecycle with container-optimized configuration.

    Provides browser initialization, page management, and resource cleanup
    with proper error handling and timeout management.
    """

    def __init__(self, config: Optional[BrowserConfig] = None):
        self.config = config or BrowserConfig()
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    async def initialize(self) -> None:
        """Initialize Playwright browser with container-optimized settings."""
        try:
            logger.info(
                "Initializing Playwright browser",
                extra={
                    "headless": self.config.headless,
                    "timeout": self.config.timeout,
                },
            )

            self._playwright = await async_playwright().start()

            # Launch browser with container-optimized settings
            self._browser = await self._playwright.chromium.launch(
                headless=self.config.headless,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--no-first-run",
                    "--no-zygote",
                    "--single-process",
                    "--disable-extensions",
                ],
            )

            # Create browser context with viewport and user agent
            self._context = await self._browser.new_context(
                viewport={
                    "width": self.config.viewport_width,
                    "height": self.config.viewport_height,
                },
                user_agent=self.config.user_agent,
            )

            # Set default timeout
            self._context.set_default_timeout(self.config.timeout)

            logger.info("Browser initialized successfully")

        except Exception as e:
            logger.error(
                "Failed to initialize browser",
                extra={"error": str(e), "error_type": type(e).__name__},
            )
            await self.cleanup()
            raise

    async def new_page(self) -> Page:
        """Create a new page in the browser context."""
        if not self._context:
            raise RuntimeError("Browser not initialized. Call initialize() first.")

        page = await self._context.new_page()
        logger.debug("Created new page")
        return page

    async def cleanup(self) -> None:
        """Clean up browser resources."""
        logger.info("Cleaning up browser resources")

        try:
            if self._context:
                await self._context.close()
                self._context = None

            if self._browser:
                await self._browser.close()
                self._browser = None

            if self._playwright:
                await self._playwright.stop()
                self._playwright = None

            logger.info("Browser cleanup completed")

        except Exception as e:
            logger.error(
                "Error during browser cleanup",
                extra={"error": str(e), "error_type": type(e).__name__},
            )

    @asynccontextmanager
    async def get_page(self):
        """Context manager for page lifecycle management."""
        page = None
        try:
            page = await self.new_page()
            yield page
        finally:
            if page:
                try:
                    await page.close()
                    logger.debug("Page closed")
                except Exception as e:
                    logger.warning("Error closing page", extra={"error": str(e)})


class PageNavigator:
    """
    Handles page navigation with retry logic and timeout management.
    """

    def __init__(self, page: Page, max_retries: int = 3, retry_delay: float = 1.0):
        self.page = page
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    async def navigate_to(self, url: str, wait_until: str = "networkidle") -> bool:
        """
        Navigate to URL with retry logic.

        Args:
            url: Target URL
            wait_until: When to consider navigation complete
                       ("load", "domcontentloaded", "networkidle")

        Returns:
            True if navigation successful, False otherwise
        """
        for attempt in range(self.max_retries + 1):
            try:
                logger.info(
                    "Navigating to URL",
                    extra={
                        "url": url,
                        "attempt": attempt + 1,
                        "wait_until": wait_until,
                    },
                )

                response = await self.page.goto(url, wait_until=wait_until)

                if response and response.ok:
                    logger.info(
                        "Navigation successful",
                        extra={"url": url, "status": response.status},
                    )
                    return True
                else:
                    logger.warning(
                        "Navigation returned non-OK response",
                        extra={
                            "url": url,
                            "status": response.status if response else None,
                        },
                    )

            except PlaywrightTimeoutError as e:
                logger.warning(
                    "Navigation timeout",
                    extra={"url": url, "attempt": attempt + 1, "error": str(e)},
                )

            except Exception as e:
                logger.error(
                    "Navigation error",
                    extra={
                        "url": url,
                        "attempt": attempt + 1,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )

            # Retry with exponential backoff
            if attempt < self.max_retries:
                delay = self.retry_delay * (2**attempt)
                logger.info(
                    "Retrying navigation",
                    extra={"delay_seconds": delay, "next_attempt": attempt + 2},
                )
                await asyncio.sleep(delay)

        logger.error(
            "Navigation failed after all retries",
            extra={"url": url, "max_retries": self.max_retries},
        )
        return False


class ElementInteractor:
    """
    Handles element waiting and interaction with robust error handling.
    """

    def __init__(self, page: Page, default_timeout: int = 10000):
        self.page = page
        self.default_timeout = default_timeout

    async def wait_for_element(
        self, selector: str, timeout: Optional[int] = None, state: str = "visible"
    ) -> bool:
        """
        Wait for element to be in specified state.

        Args:
            selector: CSS selector or text selector
            timeout: Timeout in milliseconds
            state: Element state ("visible", "hidden", "attached", "detached")

        Returns:
            True if element found in specified state, False otherwise
        """
        timeout = timeout or self.default_timeout

        try:
            logger.debug(
                "Waiting for element",
                extra={"selector": selector, "state": state, "timeout": timeout},
            )

            await self.page.wait_for_selector(selector, timeout=timeout, state=state)

            logger.debug("Element found", extra={"selector": selector, "state": state})
            return True

        except PlaywrightTimeoutError:
            logger.warning(
                "Element not found within timeout",
                extra={"selector": selector, "state": state, "timeout": timeout},
            )
            return False

        except Exception as e:
            logger.error(
                "Error waiting for element",
                extra={
                    "selector": selector,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return False

    async def click_element(
        self, selector: str, timeout: Optional[int] = None, force: bool = False
    ) -> bool:
        """
        Click element with wait and error handling.

        Args:
            selector: CSS selector or text selector
            timeout: Timeout in milliseconds
            force: Whether to force click even if element not actionable

        Returns:
            True if click successful, False otherwise
        """
        timeout = timeout or self.default_timeout

        try:
            # Wait for element to be visible and actionable
            if not await self.wait_for_element(selector, timeout, "visible"):
                return False

            logger.debug(
                "Clicking element", extra={"selector": selector, "force": force}
            )

            await self.page.click(selector, timeout=timeout, force=force)

            logger.debug("Element clicked successfully", extra={"selector": selector})
            return True

        except PlaywrightTimeoutError:
            logger.warning(
                "Click timeout", extra={"selector": selector, "timeout": timeout}
            )
            return False

        except Exception as e:
            logger.error(
                "Error clicking element",
                extra={
                    "selector": selector,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return False

    async def fill_input(
        self,
        selector: str,
        value: str,
        timeout: Optional[int] = None,
        clear_first: bool = True,
    ) -> bool:
        """
        Fill input field with value.

        Args:
            selector: CSS selector for input field
            value: Value to fill
            timeout: Timeout in milliseconds
            clear_first: Whether to clear field before filling

        Returns:
            True if fill successful, False otherwise
        """
        timeout = timeout or self.default_timeout

        try:
            # Wait for input to be visible
            if not await self.wait_for_element(selector, timeout, "visible"):
                return False

            logger.debug(
                "Filling input",
                extra={
                    "selector": selector,
                    "value_length": len(value),
                    "clear_first": clear_first,
                },
            )

            if clear_first:
                await self.page.fill(selector, "")

            await self.page.fill(selector, value, timeout=timeout)

            logger.debug("Input filled successfully", extra={"selector": selector})
            return True

        except PlaywrightTimeoutError:
            logger.warning(
                "Fill input timeout", extra={"selector": selector, "timeout": timeout}
            )
            return False

        except Exception as e:
            logger.error(
                "Error filling input",
                extra={
                    "selector": selector,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return False

    async def select_dropdown_option(
        self, selector: str, value: Union[str, list[str]], timeout: Optional[int] = None
    ) -> bool:
        """
        Select option(s) from dropdown.

        Args:
            selector: CSS selector for select element
            value: Value(s) to select
            timeout: Timeout in milliseconds

        Returns:
            True if selection successful, False otherwise
        """
        timeout = timeout or self.default_timeout

        try:
            # Wait for select to be visible
            if not await self.wait_for_element(selector, timeout, "visible"):
                return False

            logger.debug(
                "Selecting dropdown option",
                extra={"selector": selector, "value": value},
            )

            await self.page.select_option(selector, value, timeout=timeout)

            logger.debug(
                "Dropdown option selected successfully",
                extra={"selector": selector, "value": value},
            )
            return True

        except PlaywrightTimeoutError:
            logger.warning(
                "Select dropdown timeout",
                extra={"selector": selector, "timeout": timeout},
            )
            return False

        except Exception as e:
            logger.error(
                "Error selecting dropdown option",
                extra={
                    "selector": selector,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return False

    async def get_text_content(
        self, selector: str, timeout: Optional[int] = None
    ) -> Optional[str]:
        """
        Get text content of element.

        Args:
            selector: CSS selector
            timeout: Timeout in milliseconds

        Returns:
            Text content if found, None otherwise
        """
        timeout = timeout or self.default_timeout

        try:
            # Wait for element to be visible
            if not await self.wait_for_element(selector, timeout, "visible"):
                return None

            text = await self.page.text_content(selector, timeout=timeout)

            logger.debug(
                "Retrieved text content",
                extra={"selector": selector, "text_length": len(text) if text else 0},
            )

            return text

        except PlaywrightTimeoutError:
            logger.warning(
                "Get text content timeout",
                extra={"selector": selector, "timeout": timeout},
            )
            return None

        except Exception as e:
            logger.error(
                "Error getting text content",
                extra={
                    "selector": selector,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return None

    async def get_elements_text(
        self, selector: str, timeout: Optional[int] = None
    ) -> list[str]:
        """
        Get text content of all matching elements.

        Args:
            selector: CSS selector
            timeout: Timeout in milliseconds

        Returns:
            List of text contents
        """
        timeout = timeout or self.default_timeout

        try:
            # Wait for at least one element
            if not await self.wait_for_element(selector, timeout, "visible"):
                return []

            elements = await self.page.query_selector_all(selector)
            texts = []

            for element in elements:
                text = await element.text_content()
                if text:
                    texts.append(text.strip())

            logger.debug(
                "Retrieved multiple text contents",
                extra={"selector": selector, "count": len(texts)},
            )

            return texts

        except Exception as e:
            logger.error(
                "Error getting elements text",
                extra={
                    "selector": selector,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return []


@asynccontextmanager
async def get_browser_manager(config: Optional[BrowserConfig] = None):
    """
    Context manager for browser lifecycle management.

    Usage:
        async with get_browser_manager() as browser_manager:
            async with browser_manager.get_page() as page:
                navigator = PageNavigator(page)
                await navigator.navigate_to("https://example.com")
    """
    browser_manager = BrowserManager(config)
    try:
        await browser_manager.initialize()
        yield browser_manager
    finally:
        await browser_manager.cleanup()
