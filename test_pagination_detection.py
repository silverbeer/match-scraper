#!/usr/bin/env python3
"""
Test script to detect pagination buttons.
"""

import asyncio

from src.scraper.browser import BrowserConfig, BrowserManager
from src.scraper.consent_handler import MLSConsentHandler
from src.utils.logger import get_logger

logger = get_logger()


async def test_pagination_detection():
    """Test pagination button detection."""

    print("\n" + "=" * 80)
    print("Testing Pagination Button Detection")
    print("=" * 80 + "\n")

    config = BrowserConfig(headless=False, timeout=30000)
    browser_manager = BrowserManager(config)

    try:
        await browser_manager.initialize()
        page = await browser_manager.new_page()

        url = "https://www.mlssoccer.com/mlsnext/schedule/all/"
        print(f"Navigating to {url}")
        await page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(3)

        # Handle consent
        consent_handler = MLSConsentHandler(page)
        await consent_handler.handle_consent_banner()
        await asyncio.sleep(2)

        # Get iframe
        iframe_locator = page.frame_locator('main[role="main"] iframe').first
        # iframe_content = iframe_locator.frame_locator("html")  # Reserved for future use

        # Wait a bit for results to load
        await asyncio.sleep(5)

        print("\n=== Looking for pagination buttons ===\n")

        # Try to find pagination container first
        print("Checking for pagination container...")
        pagination_containers = await page.locator(
            ".pagination, .paging, [class*='pag'], nav[aria-label*='pagination']"
        ).count()
        print(
            f"Found {pagination_containers} elements matching pagination container selectors"
        )

        # Try to find page number buttons in iframe
        print("\nChecking for page number buttons in iframe...")
        for page_num in range(1, 6):
            # Try different approaches
            button_locator = iframe_locator.get_by_text(str(page_num), exact=True)
            count = await button_locator.count()
            print(
                f"  Page {page_num}: Found {count} elements with exact text '{page_num}'"
            )

            if count > 0:
                # Get all matching elements and check their properties
                for i in range(min(count, 3)):  # Check up to 3 matches
                    try:
                        element = button_locator.nth(i)
                        tag_name = await element.evaluate("el => el.tagName")
                        class_name = await element.evaluate("el => el.className")
                        parent_tag = await element.evaluate(
                            "el => el.parentElement?.tagName"
                        )
                        print(
                            f"    Match {i + 1}: <{tag_name}> class='{class_name}' parent=<{parent_tag}>"
                        )
                    except Exception as e:
                        print(f"    Match {i + 1}: Error getting details - {e}")

        print("\nBrowser will stay open for 30 seconds for inspection...")
        await asyncio.sleep(30)

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback

        traceback.print_exc()
        await asyncio.sleep(60)

    finally:
        await browser_manager.cleanup()


if __name__ == "__main__":
    asyncio.run(test_pagination_detection())
