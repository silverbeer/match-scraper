#!/usr/bin/env python3
"""
Test Bootstrap Select interaction in iframe
"""
import asyncio
from playwright.async_api import async_playwright

async def test_bootstrap_select():
    """Test Bootstrap Select interaction in MLS iframe"""
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        print("🌐 Navigating to MLS homegrown division page...")
        await page.goto("https://www.mlssoccer.com/mlsnext/schedule/homegrown-division/", wait_until='load')
        
        print("🍪 Handling consent...")
        try:
            # Handle consent banner
            consent_btn = page.locator("#onetrust-accept-btn-handler, #ot-sdk-btn").first()
            if await consent_btn.is_visible():
                await consent_btn.click()
                await asyncio.sleep(2)
                print("✅ Consent accepted")
        except Exception as e:
            print(f"⚠️ Consent handling: {e}")
        
        print("🔍 Looking for iframe...")
        # Find iframe
        iframe_element = await page.wait_for_selector('iframe', timeout=10000)
        iframe_content = await iframe_element.content_frame()
        print("✅ Found iframe")
        
        # Wait for iframe to load
        await asyncio.sleep(3)
        
        print("🎯 Looking for Bootstrap Select elements...")
        
        # Check if Bootstrap Select exists
        bootstrap_selects_count = await iframe_content.locator('.bootstrap-select').count()
        print(f"Found {bootstrap_selects_count} Bootstrap Select elements")
        
        # Check if age select exists
        age_select_count = await iframe_content.locator('select[js-age]').count()
        print(f"Found {age_select_count} age select elements")
        
        if bootstrap_selects_count > 0:
            print("📋 Attempting Bootstrap Select interaction...")
            try:
                print("  - Getting dropdown toggle...")
                dropdown_toggle = iframe_content.locator('.bootstrap-select .dropdown-toggle').first()
                
                print("  - Clicking dropdown toggle...")
                await dropdown_toggle.click()
                await asyncio.sleep(2)
                
                print("  - Checking if dropdown opened...")
                dropdown_menu = iframe_content.locator('.dropdown-menu.open')
                dropdown_count = await dropdown_menu.count()
                print(f"  - Dropdown count: {dropdown_count}")
                
                if dropdown_count > 0:
                    print("  ✅ Dropdown opened!")
                    
                    print("  - Getting options...")
                    options = await iframe_content.locator('.dropdown-menu li .text').all()
                    print(f"  Found {len(options)} options:")
                    for i, option in enumerate(options):
                        text = await option.text_content()
                        print(f"    {i+1}. {text}")
                    
                    # Try to click U14
                    print("  - Looking for U14 option...")
                    u14_option = iframe_content.locator('.dropdown-menu li .text:has-text("U14")').first()
                    print("  - Clicking U14 option...")
                    await u14_option.click()
                    await asyncio.sleep(2)
                    
                    print("  ✅ Clicked U14 option!")
                    
                else:
                    print("  ❌ Dropdown did not open")
                    
            except Exception as e:
                import traceback
                print(f"  ❌ Bootstrap Select interaction failed: {e}")
                print(f"  Traceback: {traceback.format_exc()}")
        
        print("⏱️ Keeping browser open for 30 seconds for inspection...")
        await asyncio.sleep(30)
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_bootstrap_select())