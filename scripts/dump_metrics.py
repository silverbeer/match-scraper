#!/usr/bin/env -S uv run python
"""
Dump all metric names from Grafana Prometheus for analysis and dashboard creation.

This script queries the Grafana Prometheus API to retrieve all metric names
currently being sent by the match-scraper service. The output is saved to
metrics.txt for review and dashboard configuration.

Environment Variables:
    GRAFANA_PROM_URL: Grafana Prometheus endpoint URL (e.g., https://prometheus-prod-XXX.grafana.net/api/prom)
    GRAFANA_TOKEN: Authentication token for Grafana Cloud
    GRAFANA_PROM_USER: (Optional) Username for Basic Auth (usually your Prometheus instance ID)

Authentication Methods:
    1. Bearer token: GRAFANA_TOKEN=glc_xxxxxxxxxxxxx
    2. Basic Auth: GRAFANA_PROM_USER=123456 GRAFANA_TOKEN=your_api_key

Example .env file:
    GRAFANA_PROM_URL=https://prometheus-prod-us-east-2.grafana.net/api/prom
    GRAFANA_PROM_USER=1361664
    GRAFANA_TOKEN=glc_xxxxxxxxxxxxx
"""

import os
import sys
from pathlib import Path
from typing import Optional

import requests


def load_env_file(env_file: str = ".env") -> None:
    """
    Load environment variables from a .env file.

    Args:
        env_file: Path to .env file
    """
    env_path = Path(env_file)
    if not env_path.exists():
        return

    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                # Only set if not already in environment
                if key not in os.environ:
                    os.environ[key] = value


def dump_metrics(
    base_url: Optional[str] = None,
    token: Optional[str] = None,
    username: Optional[str] = None,
    namespace_filter: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    output_file: str = "metrics.txt",
) -> None:
    """
    Query Grafana Prometheus for all metric names and save to file.

    Args:
        base_url: Grafana Prometheus endpoint URL (defaults to env var)
        token: Authentication token (defaults to env var)
        username: Username for Basic Auth (defaults to env var, optional)
        namespace_filter: Optional namespace filter (e.g., 'match-scraper')
        start_time: Optional start time for metric query (ISO 8601 format)
        end_time: Optional end time for metric query (ISO 8601 format)
        output_file: Output file path for metric names

    Raises:
        ValueError: If required environment variables are not set
        requests.HTTPError: If API request fails
    """
    # Get configuration from environment or parameters
    base_url = base_url or os.environ.get("GRAFANA_PROM_URL")
    token = token or os.environ.get("GRAFANA_TOKEN")
    username = username or os.environ.get("GRAFANA_PROM_USER")

    if not base_url:
        raise ValueError(
            "GRAFANA_PROM_URL environment variable or base_url parameter required"
        )

    if not token:
        raise ValueError(
            "GRAFANA_TOKEN environment variable or token parameter required"
        )

    # Build query parameters
    params = {}

    if namespace_filter:
        params["match[]"] = f'{{namespace="{namespace_filter}"}}'

    if start_time:
        params["start"] = start_time

    if end_time:
        params["end"] = end_time

    # Query Prometheus for all metric names
    # Ensure base_url doesn't end with a slash
    base_url = base_url.rstrip("/")

    # If base_url doesn't include /api/prom, add it
    if not base_url.endswith("/api/prom"):
        base_url = f"{base_url}/api/prom"

    url = f"{base_url}/api/v1/label/__name__/values"

    # Set up authentication - use Basic Auth with username:token for Grafana Cloud Prometheus
    # The username should be your Prometheus instance ID (not org ID)
    # The token should be a Grafana Cloud API token with MetricsPublisher role
    auth = None
    headers = {"X-Scope-OrgID": username} if username else {}

    if username:
        # For Grafana Cloud Prometheus: use Basic Auth with instance_id as username
        # and the API token as password
        auth = (username, token)
        print(f"Using Basic Auth with Prometheus instance ID: {username}")
    else:
        # Try Bearer token as fallback
        headers["Authorization"] = f"Bearer {token}"
        print("Using Bearer token authentication")

    print(f"Querying Grafana Prometheus: {url}")
    print(f"Token prefix: {token[:20]}..." if len(token) > 20 else f"Token: {token}")
    if params:
        print(f"Parameters: {params}")

    try:
        response = requests.get(url, headers=headers, auth=auth, params=params, timeout=60)

        # Debug: print response details on error
        if response.status_code != 200:
            print(f"Response status: {response.status_code}", file=sys.stderr)
            print(f"Response headers: {dict(response.headers)}", file=sys.stderr)
            print(f"Response body: {response.text[:500]}", file=sys.stderr)

        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error querying Grafana Prometheus: {e}", file=sys.stderr)
        sys.exit(1)

    # Parse response and extract metric names
    data = response.json()
    if data.get("status") != "success":
        print(f"Unexpected API response: {data}", file=sys.stderr)
        sys.exit(1)

    metric_names = sorted(data.get("data", []))

    # Write to output file
    with open(output_file, "w") as f:
        f.write("\n".join(metric_names))

    print(f"✓ Wrote {len(metric_names)} metric names to {output_file}")

    # Print match-scraper specific metrics for quick review
    scraper_metrics = [m for m in metric_names if "scraper" in m.lower() or "games" in m.lower()]
    if scraper_metrics:
        print(f"\nFound {len(scraper_metrics)} match-scraper related metrics:")
        for metric in scraper_metrics:
            print(f"  - {metric}")


def main() -> None:
    """Main entry point for metric dumping script."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Dump all metric names from Grafana Prometheus"
    )
    parser.add_argument(
        "--env-file",
        help="Path to .env file with GRAFANA_PROM_URL and GRAFANA_TOKEN",
        default=".env",
    )
    parser.add_argument(
        "--namespace",
        help="Filter metrics by namespace (e.g., match-scraper)",
        default=None,
    )
    parser.add_argument(
        "--start",
        help="Start time for metric query (ISO 8601 format)",
        default=None,
    )
    parser.add_argument(
        "--end",
        help="End time for metric query (ISO 8601 format)",
        default=None,
    )
    parser.add_argument(
        "--output",
        help="Output file path (default: metrics.txt)",
        default="metrics.txt",
    )

    args = parser.parse_args()

    # Load environment file
    load_env_file(args.env_file)

    try:
        dump_metrics(
            namespace_filter=args.namespace,
            start_time=args.start,
            end_time=args.end,
            output_file=args.output,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        print("\nTo use this script, add these to your .env file:", file=sys.stderr)
        print("  GRAFANA_PROM_URL=https://prometheus-prod-XXX.grafana.net/api/prom", file=sys.stderr)
        print("  GRAFANA_TOKEN=glc_xxxxxxxxxxxxx", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
