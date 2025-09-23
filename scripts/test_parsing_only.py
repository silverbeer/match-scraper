#!/usr/bin/env python3
"""
Test script for match parsing logic only (without browser automation).

This script allows testing the match parsing logic with sample HTML
to verify that the extraction algorithms are working correctly.
"""

import os
import sys

# Add project root to path for imports
project_root = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, project_root)

from src.scraper.match_extraction import MLSMatchExtractor  # noqa: E402


def create_sample_html_table():
    """Create sample HTML table for testing parsing logic."""
    return """
    <table class="matches-table">
        <tbody>
            <tr>
                <td class="date">12/19/2024</td>
                <td class="time">3:00 PM</td>
                <td class="home-team">FC Dallas Youth</td>
                <td class="away-team">Houston Dynamo Academy</td>
                <td class="score">2 - 1</td>
                <td class="venue">Toyota Stadium</td>
                <td class="status">completed</td>
            </tr>
            <tr>
                <td class="date">12/20/2024</td>
                <td class="time">10:00 AM</td>
                <td class="home-team">Austin FC Academy</td>
                <td class="away-team">San Antonio FC Youth</td>
                <td class="score">vs</td>
                <td class="venue">St. David's Performance Center</td>
                <td class="status">scheduled</td>
            </tr>
            <tr>
                <td class="date">12/18/2024</td>
                <td class="time">1:30 PM</td>
                <td class="home-team">Real Salt Lake Academy</td>
                <td class="away-team">Colorado Rapids Youth</td>
                <td class="score">0 - 3</td>
                <td class="venue">Zions Bank Training Center</td>
                <td class="status">completed</td>
            </tr>
        </tbody>
    </table>
    """


def create_sample_html_cards():
    """Create sample HTML cards for testing parsing logic."""
    return """
    <div class="matches-container">
        <div class="match-card">
            <div class="date">December 19, 2024</div>
            <div class="time">3:00 PM</div>
            <div class="home-team">FC Dallas Youth</div>
            <div class="away-team">Houston Dynamo Academy</div>
            <div class="score">2 - 1</div>
            <div class="venue">Toyota Stadium</div>
            <div class="status">Final</div>
        </div>
        <div class="match-card">
            <div class="date">December 20, 2024</div>
            <div class="time">10:00 AM</div>
            <div class="home-team">Austin FC Academy</div>
            <div class="away-team">San Antonio FC Youth</div>
            <div class="score">vs</div>
            <div class="venue">St. David's Performance Center</div>
            <div class="status">Scheduled</div>
        </div>
    </div>
    """


def test_date_parsing():
    """Test date parsing functionality."""
    print("🗓️  Testing Date Parsing")
    print("-" * 30)

    extractor = MLSMatchExtractor(None)  # No page needed for parsing tests

    test_cases = [
        ("12/19/2024", "3:00 PM"),
        ("2024-12-19", "15:00"),
        ("December 19, 2024", "3:00 PM"),
        ("Dec 19, 2024", "10:30 AM"),
        ("12/19/24", ""),
    ]

    for date_str, time_str in test_cases:
        try:
            parsed_date = extractor._parse_match_datetime(date_str, time_str)
            if parsed_date:
                print(f"   ✅ '{date_str}' + '{time_str}' → {parsed_date}")
            else:
                print(f"   ❌ '{date_str}' + '{time_str}' → Failed to parse")
        except Exception as e:
            print(f"   💥 '{date_str}' + '{time_str}' → Error: {e}")


def test_score_parsing():
    """Test score and status parsing functionality."""
    print("\n⚽ Testing Score Parsing")
    print("-" * 30)

    extractor = MLSMatchExtractor(None)

    test_cases = [
        ("2 - 1", "completed"),
        ("0-3", "final"),
        ("vs", "scheduled"),
        ("1 – 2", "finished"),  # Different dash character
        ("TBD", "upcoming"),
        ("Live: 1-0", "in progress"),
    ]

    for score_text, status_text in test_cases:
        try:
            home_score, away_score, status = extractor._parse_score_and_status(
                score_text, status_text
            )
            print(
                f"   ✅ '{score_text}' + '{status_text}' → {home_score}-{away_score} ({status})"
            )
        except Exception as e:
            print(f"   💥 '{score_text}' + '{status_text}' → Error: {e}")


def test_text_parsing():
    """Test parsing match data from raw text."""
    print("\n📝 Testing Text Parsing")
    print("-" * 30)

    extractor = MLSMatchExtractor(None)

    test_cases = [
        "12/19/2024 3:00 PM FC Dallas Youth Houston Dynamo Academy 2-1 Toyota Stadium",
        "Dec 20, 2024 Austin FC Academy vs San Antonio FC Youth 10:00 AM",
        "Real Salt Lake Academy Colorado Rapids Youth 0-3 Final",
    ]

    for text in test_cases:
        try:
            parsed_data = extractor._parse_row_text(text)
            print(f"   ✅ Text: '{text}'")
            for key, value in parsed_data.items():
                print(f"      {key}: {value}")
        except Exception as e:
            print(f"   💥 Text: '{text}' → Error: {e}")


async def test_match_creation():
    """Test creating Match objects from parsed data."""
    print("\n🏗️  Testing Match Creation")
    print("-" * 30)

    extractor = MLSMatchExtractor(None)

    test_data = {
        "date": "12/19/2024",
        "time": "3:00 PM",
        "home_team": "FC Dallas Youth",
        "away_team": "Houston Dynamo Academy",
        "score": "2 - 1",
        "venue": "Toyota Stadium",
        "status": "completed",
    }

    try:
        match = await extractor._create_match_from_data(
            test_data,
            index=0,
            age_group="U14",
            division="Southwest",
            competition="MLS Next",
        )

        if match:
            print(f"   ✅ Created match: {match.home_team} vs {match.away_team}")
            print(f"      ID: {match.match_id}")
            print(f"      Date: {match.match_date}")
            print(f"      Status: {match.status}")
            print(f"      Score: {match.get_score_string()}")
            print(f"      Venue: {match.venue}")
        else:
            print("   ❌ Failed to create match object")

    except Exception as e:
        print(f"   💥 Error creating match: {e}")


async def main():
    """Main function to run parsing tests."""

    print("🧪 MLS Match Parsing - Unit Testing Tool")
    print("This tool tests the parsing logic without browser automation")
    print("=" * 60)

    # Test individual parsing functions
    test_date_parsing()
    test_score_parsing()
    test_text_parsing()
    await test_match_creation()

    print("\n" + "=" * 60)
    print("✅ Parsing tests completed!")
    print("\nNext steps:")
    print("1. Run full scraping test: python scripts/test_scraping_manual.py")
    print("2. Check logs for detailed match extraction results")
    print("3. Verify that parsed data matches expected format")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
