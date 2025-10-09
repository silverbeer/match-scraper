#!/usr/bin/env python3
"""
Quick e2e test for metrics export to Grafana Cloud.

This script:
1. Initializes the metrics system with OTEL configuration
2. Records some test metrics
3. Explicitly flushes metrics to Grafana Cloud
4. Reports success/failure

Run this to verify metrics are being exported correctly.
"""

import os
import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables from .env.dev if it exists
try:
    from dotenv import load_dotenv

    env_file = project_root / ".env.dev"
    if env_file.exists():
        loaded = load_dotenv(env_file)
        if loaded:
            print(f"📄 Loaded environment from {env_file}\n")
    else:
        print(f"⚠️  No .env.dev file found at {env_file}\n")
except ImportError:
    print("⚠️  python-dotenv not installed, using system environment\n")
except Exception as e:
    print(f"⚠️  Failed to load .env.dev: {e}\n")

from src.utils.metrics import get_metrics  # noqa: E402


def test_metrics_export():
    """Test end-to-end metrics export to Grafana Cloud."""

    print("🧪 Testing metrics export to Grafana Cloud...\n")

    # Check environment variables
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    headers = os.getenv("OTEL_EXPORTER_OTLP_HEADERS")

    if not endpoint:
        print("❌ OTEL_EXPORTER_OTLP_ENDPOINT not set!")
        print(
            "   Set it to: https://otlp-gateway-prod-us-east-2.grafana.net/otlp/v1/metrics"
        )
        return False

    if not headers:
        print("❌ OTEL_EXPORTER_OTLP_HEADERS not set!")
        print("   Set it to: Authorization=Basic <your-token>")
        return False

    print(f"✅ OTEL endpoint configured: {endpoint}")
    print(f"✅ OTEL headers configured: {headers[:50]}...\n")

    # Get metrics instance
    metrics = get_metrics()

    # Record some test metrics
    print("📊 Recording test metrics...")

    # Test counter
    metrics.record_games_scheduled(5, labels={"test": "true", "source": "e2e_test"})
    metrics.record_games_scored(3, labels={"test": "true", "source": "e2e_test"})

    # Test API call metric
    metrics.record_api_call(
        endpoint="/api/test",
        method="POST",
        status_code=200,
        duration_seconds=0.123,
        labels={"test": "true", "source": "e2e_test"},
    )

    # Test browser operation
    metrics.record_browser_operation(
        operation="test_operation",
        success=True,
        duration_seconds=0.456,
        labels={"test": "true", "source": "e2e_test"},
    )

    # Test error metric
    metrics.record_scraping_error(
        error_type="test_error", labels={"test": "true", "source": "e2e_test"}
    )

    print("✅ Test metrics recorded")
    print("   - 5 games scheduled")
    print("   - 3 games scored")
    print("   - 1 API call")
    print("   - 1 browser operation")
    print("   - 1 error\n")

    # Wait a moment for any pending exports
    print("⏳ Waiting 2 seconds for periodic export...")
    time.sleep(2)

    # Explicitly flush metrics
    print("🚀 Flushing metrics to Grafana Cloud...")
    success = metrics.shutdown(timeout_seconds=10)

    if success:
        print("\n✅ SUCCESS! Metrics flushed successfully!")
        print("\nNext steps:")
        print("1. Go to your Grafana Cloud dashboard")
        print("2. Navigate to Explore > Metrics")
        print('3. Search for metrics with labels: test="true", source="e2e_test"')
        print("4. You should see:")
        print("   - games_scheduled_total = 5")
        print("   - games_scored_total = 3")
        print("   - api_calls_total = 1")
        print("   - browser_operations_total = 1")
        print("   - scraping_errors_total = 1")
        return True
    else:
        print("\n❌ FAILED! Metrics flush encountered errors")
        print("Check the logs above for details")
        return False


if __name__ == "__main__":
    try:
        success = test_metrics_export()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
