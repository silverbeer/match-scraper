"""
Example usage of logging and metrics infrastructure.

This module demonstrates how to use the MLSScraperLogger and MLSScraperMetrics
together in a typical scraping operation.
"""

import time
from typing import Any

from .logger import get_logger, scraper_logger
from .metrics import get_metrics


def example_scraping_operation() -> dict[str, Any]:
    """
    Example function demonstrating logging and metrics usage.

    Returns:
        Dictionary with operation results
    """
    get_logger()  # Initialize logger
    metrics = get_metrics()

    # Log operation start
    config = {"age_group": "U14", "division": "Northeast", "look_back_days": 1}
    scraper_logger.log_scraping_start(config)

    # Time the entire operation
    with metrics.time_execution({"version": "1.0.0"}):
        # Simulate browser operations
        with metrics.time_operation("browser_setup"):
            time.sleep(0.1)  # Simulate browser initialization
            scraper_logger.log_browser_operation(
                operation="browser_init", success=True, duration_ms=100.0
            )
            metrics.record_browser_operation(
                operation="browser_init", success=True, duration_seconds=0.1
            )

        # Simulate API calls
        start_time = time.time()
        time.sleep(0.05)  # Simulate API call
        duration = time.time() - start_time

        scraper_logger.log_api_call(
            endpoint="/api/matches",
            method="POST",
            status_code=201,
            duration_ms=duration * 1000,
        )
        metrics.record_api_call(
            endpoint="/api/matches",
            method="POST",
            status_code=201,
            duration_seconds=duration,
        )

        # Record scraped data
        games_scheduled = 5
        games_scored = 3

        metrics.record_games_scheduled(games_scheduled, {"age_group": "U14"})
        metrics.record_games_scored(games_scored, {"age_group": "U14"})

        # Log completion
        operation_metrics = {
            "games_scheduled": games_scheduled,
            "games_scored": games_scored,
            "duration_ms": 150.0,
        }
        scraper_logger.log_scraping_complete(operation_metrics)

        return operation_metrics


if __name__ == "__main__":
    # Example usage
    result = example_scraping_operation()
    print(f"Operation completed: {result}")
