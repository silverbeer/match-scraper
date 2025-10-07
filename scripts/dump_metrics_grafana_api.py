#!/usr/bin/env -S uv run python
"""
Dump metric names using Grafana API datasource proxy.

This script uses the Grafana API to query Prometheus through the datasource proxy,
which works with standard Grafana API tokens.

Environment Variables:
    GRAFANA_URL: Grafana instance URL (e.g., https://yourorg.grafana.net)
    GRAFANA_TOKEN: Grafana API token (service account or API key)
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional

import requests


def load_env_file(env_file: str = ".env") -> None:
    """Load environment variables from a .env file."""
    env_path = Path(env_file)
    if not env_path.exists():
        return

    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                if key not in os.environ:
                    os.environ[key] = value


def get_prometheus_datasource_uid(grafana_url: str, token: str) -> Optional[str]:
    """
    Get the UID of the Prometheus datasource.

    Args:
        grafana_url: Grafana instance URL
        token: API token

    Returns:
        Datasource UID or None if not found
    """
    url = f"{grafana_url}/api/datasources"
    headers = {"Authorization": f"Bearer {token}"}

    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()

    datasources = response.json()
    for ds in datasources:
        if ds.get("type") == "prometheus":
            print(f"Found Prometheus datasource: {ds.get('name')} (UID: {ds.get('uid')})")
            return ds.get("uid")

    return None


def dump_metrics_via_grafana(
    grafana_url: str,
    token: str,
    datasource_uid: Optional[str] = None,
    output_file: str = "metrics.txt",
) -> None:
    """
    Query metrics through Grafana API datasource proxy.

    Args:
        grafana_url: Grafana instance URL
        token: API token
        datasource_uid: Prometheus datasource UID (auto-detected if not provided)
        output_file: Output file path

    Raises:
        ValueError: If datasource not found
        requests.HTTPError: If API request fails
    """
    grafana_url = grafana_url.rstrip("/")

    # Auto-detect datasource if not provided
    if not datasource_uid:
        print("Auto-detecting Prometheus datasource...")
        datasource_uid = get_prometheus_datasource_uid(grafana_url, token)
        if not datasource_uid:
            raise ValueError("No Prometheus datasource found in Grafana")

    # Query through datasource proxy
    url = f"{grafana_url}/api/datasources/proxy/uid/{datasource_uid}/api/v1/label/__name__/values"
    headers = {"Authorization": f"Bearer {token}"}

    print(f"Querying Grafana API: {url}")

    response = requests.get(url, headers=headers, timeout=60)

    if response.status_code != 200:
        print(f"Response status: {response.status_code}", file=sys.stderr)
        print(f"Response body: {response.text[:500]}", file=sys.stderr)

    response.raise_for_status()

    # Parse response
    data = response.json()
    if data.get("status") != "success":
        print(f"Unexpected API response: {data}", file=sys.stderr)
        sys.exit(1)

    metric_names = sorted(data.get("data", []))

    # Write to file
    with open(output_file, "w") as f:
        f.write("\n".join(metric_names))

    print(f"✓ Wrote {len(metric_names)} metric names to {output_file}")

    # Show match-scraper metrics
    scraper_metrics = [
        m for m in metric_names if "scraper" in m.lower() or "games" in m.lower()
    ]
    if scraper_metrics:
        print(f"\nFound {len(scraper_metrics)} match-scraper related metrics:")
        for metric in scraper_metrics:
            print(f"  - {metric}")


def main() -> None:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Dump metrics using Grafana API datasource proxy"
    )
    parser.add_argument(
        "--env-file",
        help="Path to .env file",
        default=".env",
    )
    parser.add_argument(
        "--grafana-url",
        help="Grafana instance URL (e.g., https://yourorg.grafana.net)",
    )
    parser.add_argument(
        "--datasource-uid",
        help="Prometheus datasource UID (auto-detected if not provided)",
    )
    parser.add_argument(
        "--output",
        help="Output file path (default: metrics.txt)",
        default="metrics.txt",
    )

    args = parser.parse_args()

    # Load environment
    load_env_file(args.env_file)

    grafana_url = args.grafana_url or os.environ.get("GRAFANA_URL")
    token = os.environ.get("GRAFANA_TOKEN")

    if not grafana_url:
        print("Error: GRAFANA_URL required", file=sys.stderr)
        print("\nSet in .env file:", file=sys.stderr)
        print("  GRAFANA_URL=https://yourorg.grafana.net", file=sys.stderr)
        print("  GRAFANA_TOKEN=glsa_xxxxxxxxxxxxx", file=sys.stderr)
        sys.exit(1)

    if not token:
        print("Error: GRAFANA_TOKEN required", file=sys.stderr)
        sys.exit(1)

    try:
        dump_metrics_via_grafana(
            grafana_url=grafana_url,
            token=token,
            datasource_uid=args.datasource_uid,
            output_file=args.output,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
