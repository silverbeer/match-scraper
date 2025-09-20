#!/usr/bin/env python3
"""
Simple script to test Playwright installation and basic functionality.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.scraper.browser import BrowserConfig, get_browser_manager


async def test_playwright():
    """Test Playwright installation and basic browser functionality."""
    print("🧪 Testing Playwright Installation")
    print("=" * 50)
    
    try:
        # Test 1: Import check
        print("1. Testing imports...")
        from playwright.async_api import async_playwright
        print("   ✅ Playwright imports successful")
        
        # Test 2: Browser path check
        print("2. Checking browser installation...")
        async with async_playwright() as p:
            path = p.chromium.executable_path
            print(f"   ✅ Chromium found at: {path}")
        
        # Test 3: Browser launch test
        print("3. Testing browser launch...")
        browser_config = BrowserConfig(headless=True, timeout=10000)
        
        async with get_browser_manager(browser_config) as browser_manager:
            async with browser_manager.get_page() as page:
                # Test navigation to a simple page
                await page.goto("data:text/html,<h1>Test Page</h1>")
                title = await page.title()
                print(f"   ✅ Browser launched and navigated successfully")
                print(f"   ✅ Page title: '{title}'")
        
        print("\n🎉 All tests passed! Playwright is working correctly.")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        print("\n💡 To fix this, try:")
        print("   uv run playwright install chromium")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_playwright())
    sys.exit(0 if success else 1)