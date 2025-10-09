#!/usr/bin/env python3
"""Test script to POST a single match to the missing-table API."""

import asyncio
import os
from pathlib import Path

import httpx

# Load .env.dev if available
try:
    from dotenv import load_dotenv

    env_file = Path(__file__).parent / ".env.dev"
    if env_file.exists():
        load_dotenv(env_file)
        print(f"Loaded environment from {env_file}\n")
except ImportError:
    pass

# Get API credentials from environment
API_BASE_URL = os.getenv("MISSING_TABLE_API_BASE_URL", "http://localhost:8000")
API_TOKEN = os.getenv("MISSING_TABLE_API_TOKEN")

if not API_TOKEN:
    print("ERROR: MISSING_TABLE_API_TOKEN environment variable not set")
    exit(1)

# Match data in correct API format
match_data = {
    "match_date": "2025-10-17",
    "home_team_id": 11,
    "away_team_id": 19,
    "home_score": 0,
    "away_score": 0,
    "match_status": "scheduled",
    "season_id": 3,
    "age_group_id": 2,
    "match_type_id": 1,
    "division_id": 1,
}


async def test_post_match():
    """Test posting a single match to the API."""

    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": "match-scraper/1.0",
    }

    url = f"{API_BASE_URL}/api/matches"

    print(f"Testing POST to {url}")
    print(f"Match data: {match_data}")
    print()

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                headers=headers,
                json=match_data,
            )

            print(f"Status Code: {response.status_code}")
            print(f"Response Headers: {dict(response.headers)}")
            print()
            print("Response Body:")
            print(response.text)
            print()

            if response.status_code == 200 or response.status_code == 201:
                print("✓ SUCCESS: Match posted successfully")
                return response.json()
            else:
                print(f"✗ FAILED: Received status {response.status_code}")
                return None

    except httpx.HTTPStatusError as e:
        print(f"✗ HTTP Error: {e.response.status_code}")
        print(f"Response: {e.response.text}")
    except httpx.RequestError as e:
        print(f"✗ Request Error: {e}")
    except Exception as e:
        print(f"✗ Unexpected Error: {e}")


if __name__ == "__main__":
    asyncio.run(test_post_match())
