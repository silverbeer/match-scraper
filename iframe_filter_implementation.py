#!/usr/bin/env python3
"""
Practical implementation of iframe filter interaction based on investigation findings.

This script demonstrates how to:
1. Access the iframe using the discovered pattern
2. Apply various filters using multiple strategies
3. Handle Bootstrap Select elements properly
4. Implement robust error handling and fallbacks
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.scraper.browser import BrowserConfig, get_browser_manager
from src.scraper.consent_handler import MLSConsentHandler
from src.utils.logger import get_logger

logger = get_logger()


class MLSIframeFilterHandler:
    """Handles filter interactions within the MLS iframe."""
    
    # Age group value mappings discovered during investigation
    AGE_GROUP_VALUES = {
        "U13": "21",
        "U14": "22", 
        "U15": "33",
        "U16": "14",
        "U17": "15",
        "U19": "26"
    }
    
    def __init__(self, page):
        self.page = page
        self.iframe_content = None
        
    async def initialize_iframe_access(self, url: str) -> bool:
        """
        Initialize access to the iframe and handle consent.
        
        Args:
            url: URL to navigate to
            
        Returns:
            True if iframe access successful, False otherwise
        """
        try:
            logger.info(f"Navigating to {url}")
            await self.page.goto(url, wait_until="load")
            
            # Handle consent banner
            consent_handler = MLSConsentHandler(self.page)
            await consent_handler.handle_consent_banner()
            await consent_handler.wait_for_page_ready()
            
            # Access iframe using discovered pattern
            logger.info("Accessing iframe content")
            main_element = await self.page.wait_for_selector('main[role="main"]', timeout=10000)
            iframe = await main_element.query_selector("iframe")
            
            if not iframe:
                logger.error("Iframe not found in main element")
                return False
                
            self.iframe_content = await iframe.content_frame()
            if not self.iframe_content:
                logger.error("Could not access iframe content frame")
                return False
                
            await self.iframe_content.wait_for_load_state('load')
            logger.info("Iframe access successful")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize iframe access: {e}")
            return False
    
    async def apply_age_group_filter(self, age_group: str) -> bool:
        """
        Apply age group filter using Bootstrap interaction.
        
        Args:
            age_group: Age group to filter by (e.g., "U14")
            
        Returns:
            True if filter applied successfully, False otherwise
        """
        if not self.iframe_content:
            logger.error("Iframe not initialized")
            return False
            
        try:
            logger.info(f"Applying age group filter: {age_group}")
            
            # Strategy 1: Bootstrap dropdown interaction (Primary)
            try:
                # Find the age group dropdown trigger
                age_label = await self.iframe_content.query_selector('label:has-text("Age Group")')
                if age_label:
                    # Look for the bootstrap dropdown next to the label
                    dropdown_trigger = await self.iframe_content.query_selector(
                        'label:has-text("Age Group") + div .dropdown-toggle'
                    )
                    
                    if dropdown_trigger:
                        await dropdown_trigger.click()
                        logger.info("Age group dropdown opened")
                        
                        # Wait for dropdown to be visible
                        await asyncio.sleep(0.5)
                        
                        # Click the specific age group option
                        option_selector = f'span.text:has-text("{age_group}")'
                        option = await self.iframe_content.query_selector(option_selector)
                        
                        if option:
                            await option.click()
                            logger.info(f"Selected age group option: {age_group}")
                            await asyncio.sleep(1)  # Wait for filter to apply
                            return True
                        else:
                            logger.warning(f"Age group option not found: {age_group}")
                
            except Exception as e:
                logger.debug(f"Bootstrap interaction failed: {e}")
            
            # Strategy 2: Direct select interaction (Fallback)
            try:
                if age_group in self.AGE_GROUP_VALUES:
                    value = self.AGE_GROUP_VALUES[age_group]
                    select_element = await self.iframe_content.query_selector('select[js-age]')
                    
                    if select_element:
                        await select_element.select_option(value=value)
                        logger.info(f"Applied age group filter via direct select: {age_group}")
                        await asyncio.sleep(1)
                        return True
                
            except Exception as e:
                logger.debug(f"Direct select interaction failed: {e}")
            
            # Strategy 3: Role-based selector (Alternative)
            try:
                option = await self.iframe_content.get_by_role("option", name=age_group).first
                if option:
                    await option.click()
                    logger.info(f"Applied age group filter via role selector: {age_group}")
                    await asyncio.sleep(1)
                    return True
                    
            except Exception as e:
                logger.debug(f"Role-based interaction failed: {e}")
            
            logger.error(f"All strategies failed for age group filter: {age_group}")
            return False
            
        except Exception as e:
            logger.error(f"Error applying age group filter: {e}")
            return False
    
    async def apply_club_filter(self, club_name: str) -> bool:
        """
        Apply club filter with search functionality.
        
        Args:
            club_name: Club name to filter by
            
        Returns:
            True if filter applied successfully, False otherwise
        """
        if not self.iframe_content:
            logger.error("Iframe not initialized")
            return False
            
        try:
            logger.info(f"Applying club filter: {club_name}")
            
            # Find club dropdown (one with search box)
            club_dropdown = await self.iframe_content.query_selector(
                'div.bootstrap-select:has(.bs-searchbox) .dropdown-toggle'
            )
            
            if not club_dropdown:
                # Try alternative selector
                club_dropdown = await self.iframe_content.query_selector(
                    '.bootstrap-select .dropdown-toggle'
                )
            
            if club_dropdown:
                await club_dropdown.click()
                logger.info("Club dropdown opened")
                await asyncio.sleep(0.5)
                
                # Use search box if available
                search_box = await self.iframe_content.query_selector('.bs-searchbox input')
                if search_box:
                    await search_box.fill(club_name)
                    logger.info(f"Searched for club: {club_name}")
                    await asyncio.sleep(0.5)  # Wait for search results
                
                # Try to click the option
                option_selectors = [
                    f'span.text:has-text("{club_name}")',
                    f'li:has-text("{club_name}") a',
                    f'[role="option"]:has-text("{club_name}")'
                ]
                
                for selector in option_selectors:
                    try:
                        option = await self.iframe_content.query_selector(selector)
                        if option:
                            await option.click()
                            logger.info(f"Selected club: {club_name}")
                            await asyncio.sleep(1)
                            return True
                    except:
                        continue
                
                # Try role-based selector
                try:
                    option = await self.iframe_content.get_by_role("option", name=club_name).first
                    if option:
                        await option.click()
                        logger.info(f"Selected club via role selector: {club_name}")
                        await asyncio.sleep(1)
                        return True
                except:
                    pass
            
            logger.error(f"Failed to apply club filter: {club_name}")
            return False
            
        except Exception as e:
            logger.error(f"Error applying club filter: {e}")
            return False
    
    async def apply_date_filter(self, start_date: str, end_date: str) -> bool:
        """
        Apply date range filter.
        
        Args:
            start_date: Start date in MM/DD/YYYY format
            end_date: End date in MM/DD/YYYY format
            
        Returns:
            True if filter applied successfully, False otherwise
        """
        if not self.iframe_content:
            logger.error("Iframe not initialized")
            return False
            
        try:
            logger.info(f"Applying date filter: {start_date} - {end_date}")
            
            date_input = await self.iframe_content.query_selector('input[name="datefilter"]')
            if not date_input:
                date_input = await self.iframe_content.query_selector('.input-datapicker')
            
            if date_input:
                date_range = f"{start_date} - {end_date}"
                await date_input.fill(date_range)
                
                # Trigger change events
                await date_input.press('Tab')
                await asyncio.sleep(1)
                
                logger.info(f"Applied date filter: {date_range}")
                return True
            else:
                logger.error("Date input field not found")
                return False
                
        except Exception as e:
            logger.error(f"Error applying date filter: {e}")
            return False
    
    async def wait_for_results_update(self, timeout: int = 10000) -> bool:
        """
        Wait for filter results to update.
        
        Args:
            timeout: Timeout in milliseconds
            
        Returns:
            True if results updated, False if timeout
        """
        try:
            # Wait for any loading indicators to disappear
            loading_selectors = ['.loading', '.spinner', '[data-loading="true"]']
            
            for selector in loading_selectors:
                try:
                    await self.iframe_content.wait_for_selector(
                        selector, state='hidden', timeout=3000
                    )
                except:
                    continue
            
            # Wait for content to be present
            content_selectors = [
                '.match-row',
                '.schedule-results',
                'table tbody tr',
                '.container-match-info'
            ]
            
            for selector in content_selectors:
                try:
                    await self.iframe_content.wait_for_selector(selector, timeout=5000)
                    logger.info(f"Results updated - found content with selector: {selector}")
                    return True
                except:
                    continue
            
            # Generic wait as fallback
            await asyncio.sleep(2)
            return True
            
        except Exception as e:
            logger.debug(f"Wait for results failed: {e}")
            return False
    
    async def get_current_results_count(self) -> int:
        """
        Get the current number of match results displayed.
        
        Returns:
            Number of matches displayed
        """
        try:
            if not self.iframe_content:
                return 0
                
            # Look for match rows or similar result elements
            result_selectors = [
                '.match-row',
                '.container-match-info',
                'table tbody tr',
                '.schedule-item'
            ]
            
            for selector in result_selectors:
                elements = await self.iframe_content.query_selector_all(selector)
                if elements:
                    count = len(elements)
                    logger.info(f"Found {count} results using selector: {selector}")
                    return count
            
            return 0
            
        except Exception as e:
            logger.error(f"Error counting results: {e}")
            return 0


async def demo_filter_interactions():
    """Demonstrate filter interactions with the MLS iframe."""
    url = "https://www.mlssoccer.com/mlsnext/schedule/homegrown-division/"
    
    print("🎯 MLS Iframe Filter Implementation Demo")
    print("=" * 50)
    
    try:
        browser_config = BrowserConfig(
            headless=False,  # Keep visible to see interactions
            timeout=30000,
            viewport_width=1280,
            viewport_height=720,
        )
        
        async with get_browser_manager(browser_config) as browser_manager:
            async with browser_manager.get_page() as page:
                # Initialize filter handler
                filter_handler = MLSIframeFilterHandler(page)
                
                # Initialize iframe access
                if not await filter_handler.initialize_iframe_access(url):
                    print("❌ Failed to initialize iframe access")
                    return
                
                print("✅ Iframe access initialized")
                
                # Get initial results count
                initial_count = await filter_handler.get_current_results_count()
                print(f"📊 Initial results count: {initial_count}")
                
                # Test age group filter
                print("\n🔽 Testing Age Group Filter...")
                if await filter_handler.apply_age_group_filter("U14"):
                    await filter_handler.wait_for_results_update()
                    u14_count = await filter_handler.get_current_results_count()
                    print(f"✅ U14 filter applied - Results: {u14_count}")
                else:
                    print("❌ Failed to apply U14 filter")
                
                # Test club filter (if we have a known club)
                print("\n🏢 Testing Club Filter...")
                # You can replace with an actual club name found in the dropdown
                test_club = "Southern States Soccer Club"
                if await filter_handler.apply_club_filter(test_club):
                    await filter_handler.wait_for_results_update()
                    club_count = await filter_handler.get_current_results_count()
                    print(f"✅ Club filter applied - Results: {club_count}")
                else:
                    print(f"❌ Failed to apply club filter: {test_club}")
                
                # Test date filter
                print("\n📅 Testing Date Filter...")
                if await filter_handler.apply_date_filter("09/01/2025", "09/30/2025"):
                    await filter_handler.wait_for_results_update()
                    date_count = await filter_handler.get_current_results_count()
                    print(f"✅ Date filter applied - Results: {date_count}")
                else:
                    print("❌ Failed to apply date filter")
                
                print("\n🎉 Filter interaction demo completed!")
                print("\nFilter interaction patterns demonstrated:")
                print("  ✅ Iframe access using main[role='main'] iframe pattern")
                print("  ✅ Bootstrap Select dropdown interaction")
                print("  ✅ Age group filter with value mapping")
                print("  ✅ Club filter with search functionality")
                print("  ✅ Date range filter")
                print("  ✅ Results update waiting")
                print("  ✅ Multiple fallback strategies")
                
                # Keep browser open for manual inspection
                input("\nPress Enter to close browser and exit...")
                
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        return False
    
    return True


if __name__ == "__main__":
    success = asyncio.run(demo_filter_interactions())
    sys.exit(0 if success else 1)