"""
Cookie consent handling for MLS website scraping.

This module handles cookie consent banners and privacy notices that appear
on the MLS website before the main content is accessible.
"""

import asyncio

from playwright.async_api import Page

from ..utils.logger import get_logger
from .browser import ElementInteractor

logger = get_logger()


class ConsentHandlerError(Exception):
    """Custom exception for consent handling failures."""

    pass


class MLSConsentHandler:
    """
    Handles cookie consent and privacy banners on the MLS website.

    The MLS website uses OneTrust consent management which shows a modal
    that must be accepted before accessing the main page content.
    """

    # OneTrust consent selectors
    ONETRUST_BANNER_SELECTOR = "#onetrust-consent-sdk"
    ONETRUST_ACCEPT_BUTTON_SELECTORS = [
        "#onetrust-accept-btn-handler",
        "#ot-sdk-btn",  # Found in actual page structure
        "button[id*='accept']",
        "button[class*='accept']",
        "button:has-text('Accept')",
        "button:has-text('Accept & Continue')",
        "button:has-text('Accept All')",
        ".ot-sdk-show-settings button",
        "#accept-recommended-btn-handler",
    ]

    # Alternative consent selectors
    CONSENT_MODAL_SELECTORS = [
        ".consent-modal",
        ".cookie-banner",
        ".privacy-banner",
        "[data-testid*='consent']",
        "[data-testid*='cookie']",
        "#ot-sdk-btn",  # OneTrust SDK button
        ".ot-sdk-show-settings",  # OneTrust settings
        "[id*='onetrust']",  # Any OneTrust element
        "[class*='onetrust']",  # Any OneTrust element
    ]

    ACCEPT_BUTTON_SELECTORS = [
        "button:has-text('Accept')",
        "button:has-text('Continue')",
        "button:has-text('Agree')",
        "button:has-text('OK')",
        ".accept-btn",
        ".continue-btn",
        ".agree-btn",
    ]

    def __init__(self, page: Page, timeout: int = 10000):
        """
        Initialize consent handler.

        Args:
            page: Playwright page instance
            timeout: Default timeout for operations in milliseconds
        """
        self.page = page
        self.timeout = timeout
        self.interactor = ElementInteractor(page, timeout)

    async def handle_consent_banner(self) -> bool:
        """
        Handle cookie consent banner if present.

        Returns:
            True if consent was handled (or no banner present), False if failed
        """
        try:
            logger.info("Checking for cookie consent banner")

            # First check if OneTrust banner is present
            if await self._handle_onetrust_consent():
                return True

            # Check for other consent modals
            if await self._handle_generic_consent():
                return True

            # No consent banner found - this is also success
            logger.info("No consent banner detected")
            return True

        except Exception as e:
            logger.error(
                "Error handling consent banner",
                extra={"error": str(e), "error_type": type(e).__name__},
            )
            return False

    async def _handle_onetrust_consent(self) -> bool:
        """
        Handle OneTrust consent banner specifically.

        Returns:
            True if OneTrust banner was handled, False if not present or failed
        """
        try:
            # Check if OneTrust banner is present (try multiple selectors)
            banner_found = False
            onetrust_selectors = [
                self.ONETRUST_BANNER_SELECTOR,
                "#ot-sdk-btn",
                ".ot-sdk-show-settings",
                "[id*='onetrust']",
                "[class*='onetrust']",
            ]

            for selector in onetrust_selectors:
                if await self.interactor.wait_for_element(selector, timeout=3000):
                    logger.info(f"OneTrust element detected: {selector}")
                    banner_found = True
                    break

            if not banner_found:
                logger.debug("OneTrust banner not found")
                return False

            logger.info("OneTrust consent banner detected")

            # Try to find and click accept button
            for selector in self.ONETRUST_ACCEPT_BUTTON_SELECTORS:
                logger.debug(f"Trying OneTrust accept button: {selector}")

                if await self.interactor.wait_for_element(selector, timeout=2000):
                    if await self.interactor.click_element(selector):
                        logger.info(f"Clicked OneTrust accept button: {selector}")

                        # Wait for banner to disappear
                        await self._wait_for_banner_disappear(
                            self.ONETRUST_BANNER_SELECTOR
                        )
                        return True

            logger.warning("OneTrust banner found but no accept button worked")
            return False

        except Exception as e:
            logger.debug(f"Error handling OneTrust consent: {e}")
            return False

    async def _handle_generic_consent(self) -> bool:
        """
        Handle generic consent modals.

        Returns:
            True if consent modal was handled, False if not present or failed
        """
        try:
            # Check for generic consent modals
            consent_modal_found = False

            for modal_selector in self.CONSENT_MODAL_SELECTORS:
                if await self.interactor.wait_for_element(modal_selector, timeout=2000):
                    logger.info(f"Generic consent modal detected: {modal_selector}")
                    consent_modal_found = True
                    break

            if not consent_modal_found:
                logger.debug("No generic consent modal found")
                return False

            # Try to find and click accept button
            for selector in self.ACCEPT_BUTTON_SELECTORS:
                logger.debug(f"Trying generic accept button: {selector}")

                if await self.interactor.wait_for_element(selector, timeout=2000):
                    if await self.interactor.click_element(selector):
                        logger.info(f"Clicked generic accept button: {selector}")

                        # Wait a moment for modal to disappear
                        await asyncio.sleep(1)
                        return True

            logger.warning("Generic consent modal found but no accept button worked")
            return False

        except Exception as e:
            logger.debug(f"Error handling generic consent: {e}")
            return False

    async def _wait_for_banner_disappear(
        self, banner_selector: str, timeout: int = 5000
    ) -> bool:
        """
        Wait for consent banner to disappear.

        Args:
            banner_selector: CSS selector for the banner
            timeout: Timeout in milliseconds

        Returns:
            True if banner disappeared, False if still present
        """
        try:
            # Wait for banner to become hidden
            await self.interactor.wait_for_element(
                banner_selector, timeout=timeout, state="hidden"
            )
            logger.info("Consent banner disappeared")
            return True
        except Exception:
            logger.debug("Consent banner still present after timeout")
            return False

    async def wait_for_page_ready(self, timeout: int = 10000) -> bool:
        """
        Wait for page to be ready after consent handling.

        Args:
            timeout: Timeout in milliseconds

        Returns:
            True if page appears ready, False otherwise
        """
        try:
            logger.info("Waiting for page to be ready after consent handling")

            # Wait for common page elements to appear
            ready_indicators = [
                "body",
                "main",
                ".main-content",
                "#main",
                "nav",
                "header",
            ]

            for indicator in ready_indicators:
                if await self.interactor.wait_for_element(indicator, timeout=2000):
                    logger.info(f"Page ready indicator found: {indicator}")

                    # Additional wait for JavaScript to load
                    await asyncio.sleep(2)
                    return True

            logger.warning("No page ready indicators found")
            return False

        except Exception as e:
            logger.debug(f"Error waiting for page ready: {e}")
            return False


# Example usage and testing function
async def test_consent_handling():
    """
    Test consent handling functionality.
    """
    from .browser import BrowserConfig, BrowserManager, PageNavigator

    url = "https://www.mlssoccer.com/mlsnext/schedule/all/"

    try:
        config = BrowserConfig(headless=False, timeout=30000)
        browser_manager = BrowserManager(config)
        await browser_manager.initialize()

        async with browser_manager.get_page() as page:
            # Navigate to page
            navigator = PageNavigator(page)
            success = await navigator.navigate_to(url, wait_until="load")

            if not success:
                print("❌ Navigation failed")
                return

            print("✅ Navigation successful")

            # Handle consent
            consent_handler = MLSConsentHandler(page)
            consent_handled = await consent_handler.handle_consent_banner()

            if consent_handled:
                print("✅ Consent handled successfully")

                # Wait for page to be ready
                page_ready = await consent_handler.wait_for_page_ready()
                if page_ready:
                    print("✅ Page is ready")
                else:
                    print("⚠️  Page readiness uncertain")
            else:
                print("❌ Consent handling failed")

            # Keep browser open for manual inspection
            print("Browser will stay open for 30 seconds for inspection...")
            await asyncio.sleep(30)

        await browser_manager.cleanup()

    except Exception as e:
        print(f"❌ Test failed: {e}")


if __name__ == "__main__":
    asyncio.run(test_consent_handling())
