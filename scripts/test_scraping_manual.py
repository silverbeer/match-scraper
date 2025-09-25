#!/usr/bin/env python3
"""
Manual testing script for MLS scraper functionality.

This script allows manual testing of the scraping workflow to verify
that match parsing and extraction is working correctly.
"""

import asyncio
import os
import sys
from datetime import date, timedelta

# Add project root to path for imports
project_root = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, project_root)

from src.scraper.config import ScrapingConfig  # noqa: E402
from src.scraper.mls_scraper import MLSScraper, MLSScraperError  # noqa: E402


async def test_scraping_workflow():
    """Test the complete scraping workflow with detailed logging."""

    print("🚀 Starting MLS Scraper Manual Test")
    print("=" * 50)

    # Create test configuration
    config = ScrapingConfig(
        age_group="U14",
        club="",  # Empty to get all clubs
        competition="",  # Empty to get all competitions
        division="Northeast",  # Focus on Northeast division
        look_back_days=7,  # Look back 7 days
        start_date=date.today() - timedelta(days=7),
        end_date=date.today(),
        missing_table_api_url="https://api.missing-table.com",  # Dummy URL for now
        missing_table_api_key="test-key",  # Dummy key for now
        log_level="INFO",
    )

    print("📋 Test Configuration:")
    print(f"   Age Group: {config.age_group}")
    print(f"   Division: {config.division}")
    print(f"   Date Range: {config.start_date} to {config.end_date}")
    print(f"   Club Filter: {config.club or 'All clubs'}")
    print(f"   Competition Filter: {config.competition or 'All competitions'}")
    print()

    try:
        # Create and run scraper
        scraper = MLSScraper(config)

        print("🔍 Starting scraping workflow...")
        matches = await scraper.scrape_matches()

        print("\n" + "=" * 50)
        print("✅ SCRAPING COMPLETED SUCCESSFULLY!")
        print("=" * 50)

        # Get execution metrics
        metrics = scraper.get_execution_metrics()

        print("📊 Execution Metrics:")
        print(f"   Total Matches Found: {len(matches)}")
        print(f"   Games Scheduled: {metrics.games_scheduled}")
        print(f"   Games with Scores: {metrics.games_scored}")
        print(f"   Execution Duration: {metrics.execution_duration_ms}ms")
        print(f"   Errors Encountered: {metrics.errors_encountered}")
        print()

        if matches:
            print("🎯 Quick Match Summary:")
            for _i, match in enumerate(matches[:5], 1):  # Show first 5 matches
                status_emoji = (
                    "⏰"
                    if match.status == "scheduled"
                    else "✅"
                    if match.status == "completed"
                    else "🔄"
                )
                score_text = (
                    f" ({match.get_score_string()})" if match.has_score() else ""
                )
                print(
                    f"   {status_emoji} {match.home_team} vs {match.away_team}{score_text}"
                )

            if len(matches) > 5:
                print(f"   ... and {len(matches) - 5} more matches")
        else:
            print("⚠️  No matches found. This could indicate:")
            print("   - No matches in the specified date range")
            print("   - Website structure has changed")
            print("   - Parsing logic needs adjustment")
            print("   - Network or website access issues")

        return True

    except MLSScraperError as e:
        print("\n" + "=" * 50)
        print("❌ SCRAPING FAILED!")
        print("=" * 50)
        print(f"Error: {e}")
        print("\nThis could be due to:")
        print("- Website structure changes")
        print("- Network connectivity issues")
        print("- Browser initialization problems")
        print("- Parsing logic issues")
        return False

    except Exception as e:
        print("\n" + "=" * 50)
        print("💥 UNEXPECTED ERROR!")
        print("=" * 50)
        print(f"Error Type: {type(e).__name__}")
        print(f"Error Message: {e}")
        return False


async def test_different_configurations():
    """Test scraping with different configurations to verify flexibility."""

    print("\n🔬 Testing Different Configurations")
    print("=" * 50)

    test_configs = [
        {
            "name": "U16 Southwest (Last 3 days)",
            "age_group": "U16",
            "division": "Southwest",
            "days": 3,
        },
        {
            "name": "U15 Central (Last 5 days)",
            "age_group": "U15",
            "division": "Central",
            "days": 5,
        },
    ]

    for test_config in test_configs:
        print(f"\n🧪 Testing: {test_config['name']}")
        print("-" * 30)

        config = ScrapingConfig(
            age_group=test_config["age_group"],
            club="",
            competition="",
            division=test_config["division"],
            look_back_days=test_config["days"],
            start_date=date.today() - timedelta(days=test_config["days"]),
            end_date=date.today(),
            missing_table_api_url="https://api.missing-table.com",
            missing_table_api_key="test-key",
            log_level="INFO",
        )

        try:
            scraper = MLSScraper(config)
            matches = await scraper.scrape_matches()
            metrics = scraper.get_execution_metrics()

            print(
                f"   ✅ Success: {len(matches)} matches, {metrics.games_scored} with scores"
            )

        except Exception as e:
            print(f"   ❌ Failed: {e}")


def main():
    """Main function to run manual tests."""

    print("⚽ MLS Match Scraper - Manual Testing Tool")
    print("This tool helps verify that match parsing is working correctly")
    print()

    # Check if we're in the right directory
    if not os.path.exists("src/scraper"):
        print("❌ Error: Please run this script from the project root directory")
        print("   Example: python scripts/test_scraping_manual.py")
        sys.exit(1)

    # Set environment variables for testing
    os.environ.setdefault("LOG_LEVEL", "INFO")
    os.environ.setdefault("MISSING_TABLE_API_URL", "https://api.missing-table.com")
    os.environ.setdefault("MISSING_TABLE_API_KEY", "test-key")

    try:
        # Run the main test
        success = asyncio.run(test_scraping_workflow())

        if success:
            # If main test succeeded, try different configurations
            asyncio.run(test_different_configurations())

            print("\n🎉 All tests completed!")
            print("Check the detailed logs above to verify match parsing accuracy.")
        else:
            print(
                "\n🔧 Main test failed. Fix issues before testing other configurations."
            )

    except KeyboardInterrupt:
        print("\n\n⏹️  Test interrupted by user")
    except Exception as e:
        print(f"\n💥 Unexpected error running tests: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
