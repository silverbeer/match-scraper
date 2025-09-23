#!/usr/bin/env python3
"""
Script to run e2e tests for match extraction with various options.

This script provides an easy way to run the e2e tests with different configurations
for debugging and verification purposes.

Usage:
    python scripts/run_e2e_test.py --visible
    python scripts/run_e2e_test.py --headless
    python scripts/run_e2e_test.py --debug
    python scripts/run_e2e_test.py --performance
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path

# Ensure we can import from the src package
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.scraper.browser import BrowserConfig, get_browser_manager  # noqa: E402
from src.scraper.calendar_interaction import MLSCalendarInteractor  # noqa: E402
from src.scraper.filter_application import MLSFilterApplicator  # noqa: E402
from src.scraper.match_extraction import MLSMatchExtractor  # noqa: E402

# Set up simple console logging for the script
logging.basicConfig(
    level=logging.WARNING,  # Only show warnings and errors
    format='%(levelname)s: %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Disable the structured logging from the scraper modules
os.environ["LOG_LEVEL"] = "WARNING"

# Configuration
TEST_MLS_URL = "https://www.mlssoccer.com/mlsnext/schedule/all/"
TEST_TIMEOUT = 30000


# Simple config class for e2e testing
class TestScrapingConfig:
    """Simple configuration class for e2e testing."""

    def __init__(self, age_group: str, division: str, look_back_days: int, club: str = "", competition: str = ""):
        self.age_group = age_group
        self.division = division
        self.look_back_days = look_back_days
        self.club = club
        self.competition = competition


async def check_playwright_installation():
    """Check if Playwright browsers are installed."""
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            # Try to get browser path - this will fail if not installed
            _ = p.chromium.executable_path  # Check if executable exists
            return True
    except Exception:
        return False


def print_setup_instructions():
    """Print setup instructions for common issues."""
    print("\n" + "="*60)
    print("🔧 SETUP REQUIRED")
    print("="*60)
    print("It looks like Playwright browsers are not installed.")
    print("\nTo fix this, run:")
    print("  uv run playwright install")
    print("\nOr if you prefer to install all browsers:")
    print("  uv run playwright install chromium")
    print("\nThen try running the test again:")
    print("  uv run run-e2e-test --visible")
    print("="*60)


async def run_full_extraction_test(
    visible: bool = True,
    slow_mode: int = 1000,
    age_group: str = "U14",
    division: str = "Northeast",
    look_back_days: int = 30,
):
    """
    Run the complete match extraction workflow.

    Args:
        visible: Whether to run with visible browser
        slow_mode: Milliseconds to pause between actions (0 for no pause)
        age_group: Age group to filter by
        division: Division to filter by
        look_back_days: Number of days to look back for matches
    """
    print("\n" + "="*60)
    print("🚀 STARTING MATCH EXTRACTION E2E TEST")
    print("="*60)
    print("Configuration:")
    print(f"  • Visible browser: {visible}")
    print(f"  • Slow mode: {slow_mode}ms")
    print(f"  • Age group: {age_group}")
    print(f"  • Division: {division}")
    print(f"  • Look back days: {look_back_days}")
    print()

    # Check Playwright installation first
    if not await check_playwright_installation():
        print_setup_instructions()
        return False

    # Create browser configuration
    browser_config = BrowserConfig(
        headless=not visible,
        timeout=TEST_TIMEOUT,
        viewport_width=1920,
        viewport_height=1080,
    )

    # Create scraping configuration
    scraping_config = TestScrapingConfig(
        age_group=age_group,
        division=division,
        look_back_days=look_back_days,
        club="",  # Leave empty for broader results
        competition="",  # Leave empty for broader results
    )

    try:
        async with get_browser_manager(browser_config) as browser_manager:
            async with browser_manager.get_page() as page:
                # Step 1: Navigate to MLS website
                print("📍 Step 1: Navigating to MLS website...")
                try:
                    response = await page.goto(TEST_MLS_URL, wait_until="networkidle")

                    if not response or not response.ok:
                        print(f"❌ Failed to navigate to MLS website: {response.status if response else 'No response'}")
                        print("   This could be due to network issues or the website being down.")
                        return False

                    print("✅ Successfully navigated to MLS website")

                except Exception as e:
                    print(f"❌ Navigation failed: {str(e)}")
                    print("   Check your internet connection and try again.")
                    return False

                if slow_mode > 0:
                    await asyncio.sleep(slow_mode / 1000)

                # Step 2: Apply filters
                print("\n🔧 Step 2: Applying filters...")
                try:
                    filter_applicator = MLSFilterApplicator(page, timeout=TEST_TIMEOUT)

                    # Discover available options
                    print("   Discovering available filter options...")
                    available_options = await filter_applicator.discover_available_options()

                    print(f"   • Age groups: {len(available_options.get('age_group', []))}")
                    print(f"   • Clubs: {len(available_options.get('club', []))}")
                    print(f"   • Competitions: {len(available_options.get('competition', []))}")
                    print(f"   • Divisions: {len(available_options.get('division', []))}")

                    # Apply filters
                    print("   Applying filters...")
                    filters_applied = await filter_applicator.apply_all_filters(scraping_config)

                    if filters_applied:
                        print("✅ Filters applied successfully")
                    else:
                        print("⚠️  Some filters may not have been applied (this is often normal)")

                except Exception as e:
                    print(f"⚠️  Filter application had issues: {str(e)}")
                    print("   Continuing anyway - this is often not critical...")

                if slow_mode > 0:
                    await asyncio.sleep(slow_mode / 1000)

                # Step 3: Set date range
                print("\n📅 Step 3: Setting date range...")
                try:
                    calendar_interactor = MLSCalendarInteractor(page, timeout=TEST_TIMEOUT)

                    end_date = date.today()
                    start_date = end_date - timedelta(days=look_back_days)

                    print(f"   Date range: {start_date} to {end_date}")

                    date_filter_applied = await calendar_interactor.set_date_range_filter(
                        start_date, end_date
                    )

                    if date_filter_applied:
                        print("✅ Date range filter applied successfully")
                    else:
                        print("⚠️  Date range filter may not be available (continuing anyway)")

                except Exception as e:
                    print(f"⚠️  Date filter application failed: {str(e)}")
                    print("   This is often normal - many sites don't have date filters")

                if slow_mode > 0:
                    await asyncio.sleep(slow_mode / 1000)

                # Step 4: Extract match data
                print("\n⚽ Step 4: Extracting match data...")
                try:
                    match_extractor = MLSMatchExtractor(page, timeout=TEST_TIMEOUT)

                    matches = await match_extractor.extract_matches(
                        age_group=scraping_config.age_group,
                        division=scraping_config.division,
                        competition=scraping_config.competition,
                    )

                    print(f"✅ Extracted {len(matches)} matches")

                except Exception as e:
                    print(f"❌ Match extraction failed: {str(e)}")
                    print("   This could be due to website changes or network issues.")
                    return False

                # Step 5: Display and validate results
                print("\n📊 Step 5: Displaying results...")
                await display_match_results(matches, scraping_config)

                # Keep browser open for inspection if visible
                if visible and matches:
                    print("\n👀 Browser will remain open for 10 seconds for inspection...")
                    await asyncio.sleep(10)

                print("\n" + "="*60)
                print("🎉 E2E TEST COMPLETED SUCCESSFULLY!")
                print("="*60)
                return True

    except Exception as e:
        print(f"\n❌ E2E test failed with error: {str(e)}")

        # Provide helpful error messages for common issues
        error_str = str(e).lower()
        if "executable doesn't exist" in error_str or "playwright" in error_str:
            print_setup_instructions()
        elif "network" in error_str or "timeout" in error_str:
            print("\n💡 This looks like a network issue. Try:")
            print("   • Check your internet connection")
            print("   • Try again in a few minutes")
            print("   • Use --headless flag if having display issues")
        else:
            print("\n💡 For debugging, try:")
            print("   • Run with --debug flag for step-by-step execution")
            print("   • Check the full error details above")

        return False


async def display_match_results(matches, config):
    """Display detailed match results."""
    print("\n" + "="*60)
    print("📊 MATCH EXTRACTION RESULTS")
    print("="*60)
    print(f"Configuration: {config.age_group}, {config.division}")
    print(f"Total matches found: {len(matches)}")

    if not matches:
        print("\n⚠️  No matches found")
        print("   This could be normal if:")
        print("   • No games are scheduled in the date range")
        print("   • The filters are too restrictive")
        print("   • The website structure has changed")
        return

    # Categorize matches by status
    scheduled_matches = [m for m in matches if m.status == "scheduled"]
    completed_matches = [m for m in matches if m.status == "completed"]
    in_progress_matches = [m for m in matches if m.status == "in_progress"]

    print("\nMatch Status Breakdown:")
    print(f"  📅 Scheduled: {len(scheduled_matches)}")
    print(f"  ✅ Completed: {len(completed_matches)}")
    print(f"  🔴 In Progress: {len(in_progress_matches)}")

    # Display sample matches
    print("\n" + "-"*40)
    print("🏆 SAMPLE MATCHES")
    print("-"*40)

    for i, match in enumerate(matches[:5]):  # Show first 5 matches
        print(f"\nMatch {i+1}:")
        print(f"  🆚 {match.home_team} vs {match.away_team}")
        print(f"  📅 {match.match_date.strftime('%Y-%m-%d %H:%M')}")
        print(f"  📊 Status: {match.status}")
        if match.has_score():
            print(f"  ⚽ Score: {match.get_score_string()}")
        if match.venue:
            print(f"  🏟️  Venue: {match.venue}")

    if len(matches) > 5:
        print(f"\n... and {len(matches) - 5} more matches")

    # Validate match data quality
    print("\n" + "-"*40)
    print("✅ DATA QUALITY CHECK")
    print("-"*40)

    # Check for required fields
    matches_with_teams = sum(1 for m in matches if m.home_team and m.away_team)
    matches_with_dates = sum(1 for m in matches if m.match_date)
    matches_with_scores = sum(1 for m in matches if m.has_score())

    print(f"Team names: {matches_with_teams}/{len(matches)} ({matches_with_teams/len(matches)*100:.1f}%)")
    print(f"Match dates: {matches_with_dates}/{len(matches)} ({matches_with_dates/len(matches)*100:.1f}%)")
    print(f"Score data: {matches_with_scores}/{len(matches)} ({matches_with_scores/len(matches)*100:.1f}%)")

    # Check for data consistency
    if completed_matches:
        completed_with_scores = sum(1 for m in matches if m.status == "completed" and m.has_score())
        print(f"Completed matches with scores: {completed_with_scores}/{len(completed_matches)} ({completed_with_scores/len(completed_matches)*100:.1f}%)")

    if scheduled_matches:
        scheduled_without_scores = sum(1 for m in matches if m.status == "scheduled" and not m.has_score())
        print(f"Scheduled matches without scores: {scheduled_without_scores}/{len(scheduled_matches)} ({scheduled_without_scores/len(scheduled_matches)*100:.1f}%)")

    # Overall quality assessment
    quality_score = (matches_with_teams + matches_with_dates) / (2 * len(matches)) * 100
    if quality_score >= 90:
        print(f"\n🎉 Excellent data quality: {quality_score:.1f}%")
    elif quality_score >= 70:
        print(f"\n👍 Good data quality: {quality_score:.1f}%")
    else:
        print(f"\n⚠️  Data quality needs attention: {quality_score:.1f}%")


async def run_debug_test():
    """Run a step-by-step debug test with user interaction."""
    print("\n" + "="*60)
    print("🐛 STARTING DEBUG MODE")
    print("="*60)
    print("This will run step-by-step with pauses for manual inspection")
    print("Press Ctrl+C at any time to exit")
    print()

    browser_config = BrowserConfig(
        headless=False,  # Always visible for debug
        timeout=60000,   # Longer timeout
        viewport_width=1920,
        viewport_height=1080,
    )

    scraping_config = TestScrapingConfig(
        age_group="U14",
        division="Northeast",
        look_back_days=14,
    )

    async with get_browser_manager(browser_config) as browser_manager:
        async with browser_manager.get_page() as page:
            # Enable browser logging
            page.on("console", lambda msg: logger.info(f"Browser: {msg.text}"))
            page.on("pageerror", lambda error: logger.error(f"Browser error: {error}"))

            # Step 1: Navigate
            logger.info("=== STEP 1: NAVIGATION ===")
            input("Press Enter to navigate to MLS website...")

            response = await page.goto(TEST_MLS_URL, wait_until="networkidle")
            logger.info(f"Navigation response: {response.status if response else 'None'}")

            input("Press Enter to continue to filter discovery...")

            # Step 2: Discover filters
            logger.info("=== STEP 2: FILTER DISCOVERY ===")
            filter_applicator = MLSFilterApplicator(page, timeout=60000)

            available_options = await filter_applicator.discover_available_options()
            logger.info(f"Available options: {available_options}")

            input("Press Enter to apply filters...")

            # Step 3: Apply filters
            logger.info("=== STEP 3: FILTER APPLICATION ===")
            filters_applied = await filter_applicator.apply_all_filters(scraping_config)
            logger.info(f"Filters applied: {filters_applied}")

            input("Press Enter to extract matches...")

            # Step 4: Extract matches
            logger.info("=== STEP 4: MATCH EXTRACTION ===")
            match_extractor = MLSMatchExtractor(page, timeout=60000)

            matches = await match_extractor.extract_matches(
                age_group=scraping_config.age_group,
                division=scraping_config.division,
                competition=scraping_config.competition,
            )

            logger.info(f"Extracted {len(matches)} matches")
            await display_match_results(matches, scraping_config)

            input("Press Enter to finish debug session...")
            print("🎉 DEBUG SESSION COMPLETE")
            return True


async def run_performance_test():
    """Run a performance test to measure extraction speed."""
    print("\n" + "="*60)
    print("⚡ STARTING PERFORMANCE TEST")
    print("="*60)

    import time

    browser_config = BrowserConfig(
        headless=True,  # Headless for performance
        timeout=30000,
    )

    test_configs = [
        TestScrapingConfig(age_group="U14", division="Northeast", look_back_days=7),
        TestScrapingConfig(age_group="U15", division="Southeast", look_back_days=14),
        TestScrapingConfig(age_group="U16", division="Central", look_back_days=21),
    ]

    async with get_browser_manager(browser_config) as browser_manager:
        for i, config in enumerate(test_configs):
            logger.info(f"\n--- Performance Test {i+1}: {config.age_group}, {config.division} ---")

            start_time = time.time()

            async with browser_manager.get_page() as page:
                # Navigate
                await page.goto(TEST_MLS_URL, wait_until="networkidle")

                # Apply filters
                filter_applicator = MLSFilterApplicator(page, timeout=30000)
                await filter_applicator.apply_all_filters(config)

                # Extract matches
                match_extractor = MLSMatchExtractor(page, timeout=30000)
                matches = await match_extractor.extract_matches(
                    age_group=config.age_group,
                    division=config.division,
                    competition=config.competition,
                )

                end_time = time.time()
                duration = end_time - start_time

                print(f"  Extracted {len(matches)} matches in {duration:.2f} seconds")
                if matches:
                    print(f"  Performance: {len(matches)/duration:.2f} matches/second")

    print("🎉 PERFORMANCE TEST COMPLETE")
    return True


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Run e2e tests for match extraction",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run run-e2e-test --visible                    # Run with visible browser
  uv run run-e2e-test --visible --slow 2000       # Run with slow motion
  uv run run-e2e-test --debug                      # Step-by-step debug mode
  uv run run-e2e-test --performance                # Performance benchmarks
        """
    )
    parser.add_argument("--visible", action="store_true", help="Run with visible browser")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode")
    parser.add_argument("--debug", action="store_true", help="Run in debug mode with step-by-step execution")
    parser.add_argument("--performance", action="store_true", help="Run performance test")
    parser.add_argument("--slow", type=int, default=0, help="Slow mode delay in milliseconds")
    parser.add_argument("--age-group", default="U14", help="Age group to test")
    parser.add_argument("--division", default="Northeast", help="Division to test")
    parser.add_argument("--look-back-days", type=int, default=30, help="Days to look back for matches")

    args = parser.parse_args()

    try:
        # Set environment variables for the tests
        if args.visible:
            os.environ["E2E_VISIBLE"] = "true"
        if args.slow > 0:
            os.environ["E2E_SLOW_MO"] = str(args.slow)

        # Determine which test to run
        if args.debug:
            success = asyncio.run(run_debug_test())
        elif args.performance:
            success = asyncio.run(run_performance_test())
        else:
            # Default to full extraction test
            visible = args.visible or not args.headless
            success = asyncio.run(run_full_extraction_test(
                visible=visible,
                slow_mode=args.slow,
                age_group=args.age_group,
                division=args.division,
                look_back_days=args.look_back_days,
            ))

        # Exit with appropriate code
        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print("\n\n⏹️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {str(e)}")
        print("\n💡 If this keeps happening, please report it as a bug.")
        sys.exit(1)


if __name__ == "__main__":
    main()
