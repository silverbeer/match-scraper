#!/usr/bin/env python3
"""
Test script to debug calendar navigation in headful mode.

This script opens the browser in headful mode so you can visually see
the calendar navigation happening step by step.

Run with: python test_calendar_debug.py
"""

import asyncio
from datetime import date

from src.scraper.browser import BrowserConfig, BrowserManager, PageNavigator
from src.scraper.calendar_interaction import MLSCalendarInteractor
from src.scraper.consent_handler import MLSConsentHandler
from src.utils.logger import get_logger

logger = get_logger()


async def test_calendar_navigation():
    """Test calendar navigation with visual browser."""
    # Create browser config with headful mode and longer timeout
    config = BrowserConfig(
        headless=False,  # Show browser window
        timeout=60000,  # 60 seconds timeout
    )

    browser_manager = BrowserManager(config)

    try:
        # Initialize browser
        await browser_manager.initialize()
        logger.info("Browser initialized")

        # Create a new page
        page = await browser_manager.new_page()
        logger.info("Page created")

        # Navigate to MLS website
        navigator = PageNavigator(page)
        url = "https://www.mlssoccer.com/mlsnext/schedule?age_group=u-14&division=northeast"
        # Use 'load' instead of 'networkidle' to avoid timeout on modern websites
        success = await navigator.navigate_to(url, wait_until="load")

        if not success:
            logger.error("Failed to navigate to MLS website")
            return

        logger.info("Successfully navigated to MLS website")

        # Handle cookie consent banner
        consent_handler = MLSConsentHandler(page)
        consent_success = await consent_handler.handle_consent_banner()

        if not consent_success:
            logger.warning("Failed to handle consent banner")
        else:
            logger.info("✅ Cookie consent handled")

        # Wait for page to be ready
        page_ready = await consent_handler.wait_for_page_ready()
        if not page_ready:
            logger.warning("Page readiness check failed")
        else:
            logger.info("✅ Page is ready")

        # Wait a bit to let the page load
        await asyncio.sleep(3)

        # Create calendar interactor
        calendar = MLSCalendarInteractor(page)

        # Test dates: September 1-30, 2025
        start_date = date(2025, 9, 1)
        end_date = date(2025, 9, 30)

        logger.info(f"Testing calendar navigation for {start_date} to {end_date}")

        # Try to set date range (this will trigger our navigation logic)
        success = await calendar.set_date_range_filter(start_date, end_date)

        if success:
            logger.info("✅ Calendar navigation succeeded!")
        else:
            logger.error("❌ Calendar navigation failed")

        # Keep browser open for inspection
        logger.info("Browser will stay open for 30 seconds for inspection...")
        await asyncio.sleep(30)

    except Exception as e:
        logger.error(f"Error during test: {e}", exc_info=True)
    finally:
        # Cleanup
        await browser_manager.cleanup()
        logger.info("Browser cleaned up")


if __name__ == "__main__":
    print("=" * 80)
    print("Calendar Navigation Debug Test")
    print("=" * 80)
    print()
    print("This test will:")
    print("1. Open a browser window (headful mode)")
    print("2. Navigate to MLS Next U14 Northeast page")
    print("3. Handle cookie consent banner")
    print("4. Attempt to set date range to September 1-30, 2025")
    print("5. Show you exactly what happens in the browser")
    print()
    print("Watch the browser window to see calendar navigation in action!")
    print("=" * 80)
    print()

    asyncio.run(test_calendar_navigation())
