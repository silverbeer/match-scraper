"""
AWS Lambda handler for MLS match scraper.

This module provides the Lambda entry point for scheduled scraping operations,
with CloudWatch metrics and structured logging.
"""

import asyncio
import json
import os
from datetime import date, timedelta
from typing import Any

from aws_lambda_powertools import Logger, Metrics
from aws_lambda_powertools.metrics import MetricUnit

from src.scraper.config import ScrapingConfig
from src.scraper.mls_scraper import MLSScraper, MLSScraperError

# Initialize Lambda Powertools
logger = Logger()
metrics = Metrics(namespace="MLSScraper")


@logger.inject_lambda_context(log_event=True)
@metrics.log_metrics(capture_cold_start_metric=True)
def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    AWS Lambda handler for MLS match scraping.

    Args:
        event: Lambda event data. Supports configuration overrides:
            - age_group: Age group to scrape (default: from env or U14)
            - division: Division to scrape (default: from env or Northeast)
            - start_offset: Days backward from today (default: 1)
            - end_offset: Days forward from today (default: 1)
            - enable_api_integration: Whether to post to API (default: true)
        context: Lambda context object

    Returns:
        Response dict with status, match count, and execution metrics
    """
    try:
        logger.info("Lambda function invoked", extra={"event": event})

        # Parse configuration from event or environment variables
        config = _create_config_from_event(event)

        # Log configuration
        logger.info(
            "Scraping configuration",
            extra={
                "age_group": config.age_group,
                "division": config.division,
                "date_range": f"{config.start_date} to {config.end_date}",
                "api_integration": event.get("enable_api_integration", True),
            },
        )

        # Run scraper
        enable_api = event.get("enable_api_integration", True)
        matches = asyncio.run(_run_scraper(config, enable_api))

        # Emit CloudWatch metrics
        _emit_metrics(matches, config)

        # Prepare response
        response = {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "status": "success",
                    "matches_found": len(matches),
                    "age_group": config.age_group,
                    "division": config.division,
                    "date_range": f"{config.start_date} to {config.end_date}",
                }
            ),
        }

        logger.info(
            "Lambda execution completed successfully",
            extra={"matches_found": len(matches)},
        )

        return response

    except MLSScraperError as e:
        logger.error(
            "Scraping failed", extra={"error": str(e), "error_type": type(e).__name__}
        )
        metrics.add_metric(name="ScraperErrors", unit=MetricUnit.Count, value=1)

        return {
            "statusCode": 500,
            "body": json.dumps(
                {"status": "error", "error": str(e), "error_type": "MLSScraperError"}
            ),
        }

    except Exception as e:
        logger.exception("Unexpected error in Lambda handler")
        metrics.add_metric(name="LambdaErrors", unit=MetricUnit.Count, value=1)

        return {
            "statusCode": 500,
            "body": json.dumps(
                {"status": "error", "error": str(e), "error_type": type(e).__name__}
            ),
        }


def _create_config_from_event(event: dict[str, Any]) -> ScrapingConfig:
    """
    Create scraping configuration from Lambda event and environment variables.

    Args:
        event: Lambda event containing optional configuration overrides

    Returns:
        ScrapingConfig instance
    """
    # Get configuration from event or environment variables
    age_group = event.get("age_group", os.getenv("AGE_GROUP", "U14"))
    division = event.get("division", os.getenv("DIVISION", "Northeast"))
    start_offset = int(event.get("start_offset", os.getenv("START_OFFSET", "1")))
    end_offset = int(event.get("end_offset", os.getenv("END_OFFSET", "1")))

    # Calculate date range
    today = date.today()
    start_date = today - timedelta(days=start_offset)
    end_date = today + timedelta(days=end_offset)

    # Get API configuration from environment
    api_base_url = os.getenv("MISSING_TABLE_API_BASE_URL", "http://localhost:8000")
    api_token = os.getenv("MISSING_TABLE_API_TOKEN", "")

    # Get team cache configuration
    enable_cache = os.getenv("ENABLE_TEAM_CACHE", "true").lower() == "true"
    cache_refresh = os.getenv("CACHE_REFRESH_ON_MISS", "true").lower() == "true"
    cache_timeout = int(os.getenv("CACHE_PRELOAD_TIMEOUT", "30"))

    return ScrapingConfig(
        age_group=age_group,
        division=division,
        club="",  # Lambda typically scrapes all clubs
        competition="",  # Lambda typically scrapes all competitions
        look_back_days=start_offset,
        start_date=start_date,
        end_date=end_date,
        missing_table_api_url=api_base_url,
        missing_table_api_key=api_token,
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        enable_team_cache=enable_cache,
        cache_refresh_on_miss=cache_refresh,
        cache_preload_timeout=cache_timeout,
    )


async def _run_scraper(config: ScrapingConfig, enable_api_integration: bool) -> list:
    """
    Execute the scraper with proper async handling.

    Args:
        config: Scraping configuration
        enable_api_integration: Whether to post matches to API

    Returns:
        List of scraped matches
    """
    scraper = MLSScraper(
        config,
        headless=True,  # Always headless in Lambda
        enable_api_integration=enable_api_integration,
    )

    matches = await scraper.scrape_matches()
    return matches


def _emit_metrics(matches: list, config: ScrapingConfig) -> None:
    """
    Emit CloudWatch metrics for the scraping operation.

    Args:
        matches: List of scraped matches
        config: Scraping configuration
    """
    # Total matches found
    metrics.add_metric(name="MatchesFound", unit=MetricUnit.Count, value=len(matches))

    # Matches by status
    scheduled = len([m for m in matches if m.match_status == "scheduled"])
    completed = len([m for m in matches if m.match_status == "completed"])
    scored = len([m for m in matches if m.has_score()])

    metrics.add_metric(name="ScheduledMatches", unit=MetricUnit.Count, value=scheduled)

    metrics.add_metric(name="CompletedMatches", unit=MetricUnit.Count, value=completed)

    metrics.add_metric(name="ScoredMatches", unit=MetricUnit.Count, value=scored)

    # Add dimensions for filtering
    metrics.add_dimension(name="AgeGroup", value=config.age_group)
    metrics.add_dimension(name="Division", value=config.division)


# For local testing
if __name__ == "__main__":
    # Test event
    test_event = {
        "age_group": "U14",
        "division": "Northeast",
        "start_offset": 1,
        "end_offset": 1,
        "enable_api_integration": False,
    }

    # Mock context
    class MockContext:
        function_name = "mls-scraper-test"
        memory_limit_in_mb = 1024
        invoked_function_arn = (
            "arn:aws:lambda:us-east-1:123456789012:function:mls-scraper-test"
        )
        aws_request_id = "test-request-id"

    result = lambda_handler(test_event, MockContext())
    print(json.dumps(result, indent=2))
