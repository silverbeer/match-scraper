#!/usr/bin/env python3
"""Test what payload the scraper builds for the API."""

import asyncio
import os
from datetime import datetime

from src.api.missing_table_client import MissingTableClient
from src.scraper.api_integration import MatchAPIIntegrator
from src.scraper.models import Match


# Mock configuration
class MockConfig:
    enable_team_cache = True
    cache_refresh_on_miss = True


async def test_payload_building():
    """Test building the API payload."""

    # Initialize API client
    api_base_url = os.getenv(
        "MISSING_TABLE_API_BASE_URL", "https://dev.missingtable.com"
    )
    api_token = os.getenv("MISSING_TABLE_API_TOKEN")

    if not api_token:
        print("ERROR: MISSING_TABLE_API_TOKEN not set")
        return

    client = MissingTableClient(base_url=api_base_url, api_token=api_token)
    integrator = MatchAPIIntegrator(client, config=MockConfig())

    # Create a test match (Match ID 98966 from screenshot)
    test_match = Match(
        match_id="98966",
        home_team="Bayside FC",
        away_team="Intercontinental Football Academy of New England",
        match_datetime=datetime(2025, 10, 17, 18, 0, 0),  # 10/17/25 06:00pm
        location="Bayside FC Field - Bayside FC Field",
        home_score=None,
        away_score=None,
        match_status="scheduled",
    )

    print("Test Match:")
    print(f"  ID: {test_match.match_id}")
    print(f"  Home: {test_match.home_team}")
    print(f"  Away: {test_match.away_team}")
    print(f"  Date: {test_match.match_datetime}")
    print()

    try:
        # Preload cache and initialize
        print("Preloading teams cache...")
        cache_result = await integrator.preload_teams_cache()
        print(f"Cache result: {cache_result}")
        print()

        # Initialize entity IDs
        print("Initializing entity IDs...")
        await integrator._initialize_entity_ids([test_match], "U14", "Northeast")
        print()

        # Convert match to API format
        print("Converting match to API format...")
        match_data = await integrator._convert_match_to_api_format(
            test_match, "U14", "Northeast"
        )

        if match_data:
            print("✓ Successfully converted match to API format:")
            print()
            import json

            print(json.dumps(match_data, indent=2))
        else:
            print("✗ Failed to convert match to API format")

    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_payload_building())
