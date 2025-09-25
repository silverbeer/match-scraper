#!/usr/bin/env python3
"""
Quick test script to verify MissingTable API health check functionality.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.api.missing_table_client import MissingTableClient, MissingTableAPIError


async def test_health_check():
    """Test the health check functionality with local API."""
    print("🏥 Testing MissingTable API Health Check...")
    print("-" * 50)

    # Initialize client (will use environment variables)
    client = MissingTableClient()

    print(f"📍 Base URL: {client.base_url}")
    print(f"🔑 Token configured: {'Yes' if client.api_token else 'No'}")

    try:
        # Test basic health check
        print("\n🔍 Testing basic health check (/health)...")
        health = await client.health_check(full=False)
        print(f"✅ Basic Health Check Success!")
        print(f"   Status: {health.status}")
        if health.version:
            print(f"   Version: {health.version}")
        if health.timestamp:
            print(f"   Timestamp: {health.timestamp}")

        # Test full health check
        print("\n🔍 Testing full health check (/health/full)...")
        full_health = await client.health_check(full=True)
        print(f"✅ Full Health Check Success!")
        print(f"   Status: {full_health.status}")
        if full_health.version:
            print(f"   Version: {full_health.version}")
        if full_health.database:
            print(f"   Database: {full_health.database}")
        if full_health.timestamp:
            print(f"   Timestamp: {full_health.timestamp}")

        print(f"\n🎉 All health checks passed! API is ready for integration.")
        return True

    except MissingTableAPIError as e:
        print(f"❌ API Error: {e}")
        if e.status_code:
            print(f"   Status Code: {e.status_code}")
        if e.response_data:
            print(f"   Response: {e.response_data}")
        return False

    except Exception as e:
        print(f"💥 Unexpected error: {e}")
        return False


if __name__ == "__main__":
    # Check environment
    token = os.getenv("MISSING_TABLE_API_TOKEN")
    base_url = os.getenv("MISSING_TABLE_API_BASE_URL", "http://localhost:8000")

    print("🌍 Environment Check:")
    print(f"   MISSING_TABLE_API_BASE_URL: {base_url}")
    print(f"   MISSING_TABLE_API_TOKEN: {'Set ✅' if token else 'Not set ❌'}")

    if not token:
        print("\n⚠️  Warning: MISSING_TABLE_API_TOKEN not set.")
        print("   Health check doesn't require auth, but other operations will.")

    success = asyncio.run(test_health_check())
    sys.exit(0 if success else 1)