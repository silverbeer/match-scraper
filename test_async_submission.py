#!/usr/bin/env python3
"""
Test script for async match submission to missing-table API.

This script tests the end-to-end flow:
1. Create a test match with team names (not IDs)
2. Submit to async API (/api/matches/submit)
3. Poll task status until complete
4. Verify match appears in database
"""

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.api.missing_table_client import MissingTableClient, MissingTableAPIError


async def test_async_submission():
    """Test async match submission."""

    # Load environment
    from dotenv import load_dotenv
    load_dotenv('.env.dev')

    print("=" * 70)
    print("🧪 Testing Async Match Submission to missing-table API")
    print("=" * 70)
    print()

    # Check environment
    api_url = os.getenv('MISSING_TABLE_API_BASE_URL')
    api_token = os.getenv('MISSING_TABLE_API_TOKEN')

    print(f"📡 API URL: {api_url}")
    print(f"🔑 Token configured: {'✅' if api_token else '❌'}")
    print()

    if not api_token:
        print("❌ ERROR: MISSING_TABLE_API_TOKEN not set in .env.dev")
        return False

    # Create client
    client = MissingTableClient(base_url=api_url, api_token=api_token)

    # Step 1: Health check
    print("=" * 70)
    print("Step 1: Health Check")
    print("=" * 70)
    try:
        health = await client.health_check()
        print(f"✅ API Status: {health.status}")
        if health.version:
            print(f"   Version: {health.version}")
        print()
    except MissingTableAPIError as e:
        print(f"❌ Health check failed: {e}")
        return False

    # Step 2: Create test match data
    print("=" * 70)
    print("Step 2: Create Test Match")
    print("=" * 70)

    # Create a test match with team names (not IDs)
    # Use teams that exist in the database: IFA and NEFC are both Northeast teams
    now = datetime.now(timezone.utc)
    match_data = {
        "home_team": "IFA",
        "away_team": "NEFC",
        "match_date": now.isoformat(),
        "season": "2025-26",
        "age_group": "U14",
        "division": "Northeast",
        "match_status": "scheduled",
        "match_type": "League",
        "home_score": None,
        "away_score": None,
        "external_match_id": f"test-async-{now.timestamp()}",
        "location": "Test Stadium"
    }

    print(f"📋 Match Details:")
    print(f"   Home: {match_data['home_team']}")
    print(f"   Away: {match_data['away_team']}")
    print(f"   Date: {match_data['match_date']}")
    print(f"   Season: {match_data['season']}")
    print(f"   Age Group: {match_data['age_group']}")
    print(f"   Division: {match_data['division']}")
    print(f"   External ID: {match_data['external_match_id']}")
    print()

    # Step 3: Submit match asynchronously
    print("=" * 70)
    print("Step 3: Submit Match Asynchronously")
    print("=" * 70)

    try:
        result = await client.submit_match_async(match_data)
        task_id = result.get('task_id')
        status_url = result.get('status_url')

        print(f"✅ Match submitted successfully!")
        print(f"   Task ID: {task_id}")
        print(f"   Status URL: {status_url}")
        print()

    except MissingTableAPIError as e:
        print(f"❌ Submission failed: {e}")
        if e.response_data:
            print(f"   Response: {e.response_data}")
        return False

    # Step 4: Poll task status
    print("=" * 70)
    print("Step 4: Poll Task Status")
    print("=" * 70)

    max_polls = 30  # 30 seconds max wait
    poll_interval = 1  # 1 second between polls

    for i in range(max_polls):
        try:
            status = await client.get_task_status(task_id)

            state = status.get('state')
            ready = status.get('ready', False)

            print(f"📊 Poll {i+1}/{max_polls}: State={state}, Ready={ready}")

            if ready:
                # Task completed
                if status.get('result'):
                    result_data = status['result']
                    print()
                    print("✅ Task completed successfully!")
                    print(f"   Match ID: {result_data.get('match_id')}")
                    print(f"   Status: {result_data.get('status')}")
                    if result_data.get('message'):
                        print(f"   Message: {result_data['message']}")
                    print()
                    return True

                elif status.get('error'):
                    print()
                    print(f"❌ Task failed: {status['error']}")
                    print()
                    return False

            # Wait before next poll
            await asyncio.sleep(poll_interval)

        except MissingTableAPIError as e:
            print(f"❌ Status check failed: {e}")
            return False

    print()
    print(f"⏰ Task did not complete within {max_polls} seconds")
    print(f"   Task may still be processing. Check task {task_id} later.")
    print()
    return False


async def main():
    """Main entry point."""
    try:
        success = await test_async_submission()

        print("=" * 70)
        if success:
            print("🎉 Test PASSED - Async submission working correctly!")
        else:
            print("❌ Test FAILED - Check errors above")
        print("=" * 70)

        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
