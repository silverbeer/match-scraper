#!/usr/bin/env python3
"""
Test script for calendar date range selection.
Tests the calendar interaction logic independently of the full scraper.
"""

import asyncio
from datetime import datetime

from src.scraper.browser import BrowserConfig, BrowserManager
from src.scraper.calendar_interaction import MLSCalendarInteractor
from src.scraper.consent_handler import MLSConsentHandler
from src.utils.logger import get_logger

logger = get_logger()


async def test_calendar_date_range():
    """Test setting date range using calendar interaction."""

    # Test parameters - wider range to test navigation
    FROM_DATE = datetime(2025, 9, 5)  # Sept 5, 2025
    TO_DATE = datetime(2025, 11, 13)  # Nov 13, 2025

    print(f"\n{'=' * 80}")
    print("Testing Calendar Date Range Selection")
    print(f"{'=' * 80}")
    print(f"From Date: {FROM_DATE.strftime('%m/%d/%Y')}")
    print(f"To Date:   {TO_DATE.strftime('%m/%d/%Y')}")
    print(f"{'=' * 80}\n")

    # Create browser config with visible browser and slow motion
    config = BrowserConfig(
        headless=False,
        timeout=30000,
    )

    browser_manager = BrowserManager(config)

    try:
        # Initialize browser
        print("🌐 Initializing browser...")
        await browser_manager.initialize()

        # Create a new page
        page = await browser_manager.new_page()

        # Navigate to MLS NEXT schedule page
        url = "https://www.mlssoccer.com/mlsnext/schedule/all/"
        print(f"📍 Navigating to {url}")
        await page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(3)

        # Handle consent popup
        print("🍪 Handling consent popup...")
        consent_handler = MLSConsentHandler(page)
        await consent_handler.handle_consent_banner()
        print("✅ Consent handled")

        # Wait for page to settle after consent
        await asyncio.sleep(2)

        print("\n📅 Testing calendar date range selection...")

        # Create MLSCalendarInteractor instance (it will find the iframe internally)
        calendar = MLSCalendarInteractor(page)

        # Set date range using the correct method
        success = await calendar.set_date_range_filter(FROM_DATE, TO_DATE)

        if not success:
            print("❌ FAILED: Calendar date range selection returned False")
            return False

        print("✅ Calendar interaction completed successfully")

        # Wait for results to load
        await asyncio.sleep(3)

        print(f"\n{'=' * 80}")
        print("🎉 TEST PASSED!")
        print(f"{'=' * 80}\n")

        # Keep browser open for manual inspection
        print("Browser will stay open for 30 seconds for inspection...")
        await asyncio.sleep(30)

        return True

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback

        traceback.print_exc()

        # Keep browser open on error for debugging
        print("\nBrowser will stay open for 60 seconds for debugging...")
        await asyncio.sleep(60)

        return False

    finally:
        # Cleanup
        await browser_manager.cleanup()


if __name__ == "__main__":
    asyncio.run(test_calendar_date_range())
