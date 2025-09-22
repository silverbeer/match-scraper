"""
Integration tests for Pydantic models with logging and metrics infrastructure.

Tests that Pydantic models serialize properly with the logging system
and work correctly with the metrics collection.
"""

import json
from datetime import datetime
from unittest.mock import patch

from src.scraper.models import Match, ScrapingMetrics
from src.utils.logger import MLSScraperLogger


class TestPydanticIntegration:
    """Test cases for Pydantic model integration with infrastructure."""

    def test_match_serialization_in_logging(self):
        """Test that Match models serialize properly in logging."""
        logger = MLSScraperLogger()

        match = Match(
            match_id="12345",
            match_datetime=datetime(2024, 1, 15, 14, 30),
            location="Stadium A",
            competition="MLS Next",
            home_team="Team A",
            away_team="Team B",
        )

        with patch.object(logger._logger, "info") as mock_info:
            logger._logger.info(
                "Match created", extra={"match": match, "operation": "test"}
            )

            # Verify the call was made
            mock_info.assert_called_once()
            call_args = mock_info.call_args

            # The match should be serialized properly
            extra_data = call_args[1]["extra"]
            assert "match" in extra_data
            assert "operation" in extra_data
            assert extra_data["operation"] == "test"

    def test_scraping_metrics_serialization_in_logging(self):
        """Test that ScrapingMetrics models serialize properly in logging."""
        logger = MLSScraperLogger()

        metrics = ScrapingMetrics(
            games_scheduled=5,
            games_scored=3,
            api_calls_successful=10,
            api_calls_failed=1,
            execution_duration_ms=1500,
            errors_encountered=0,
        )

        with patch.object(logger._logger, "info") as mock_info:
            logger.log_scraping_complete({"metrics": metrics})

            # Verify the call was made
            mock_info.assert_called_once()
            call_args = mock_info.call_args

            # The metrics should be included in the log
            extra_data = call_args[1]["extra"]
            assert "metrics" in extra_data
            assert extra_data["operation"] == "scraping_complete"

    def test_match_model_dump_json(self):
        """Test that Match models can be serialized to JSON."""
        match = Match(
            match_id="12345",
            match_datetime=datetime(2024, 1, 15, 14, 30),
            competition="MLS Next",
            home_team="Team A",
            away_team="Team B",
            home_score=2,
            away_score=1,
        )

        # Should serialize to valid JSON
        json_str = match.model_dump_json()
        parsed = json.loads(json_str)

        assert parsed["match_id"] == "12345"
        assert parsed["home_team"] == "Team A"
        assert parsed["away_team"] == "Team B"
        assert parsed["match_status"] == "completed"
        assert parsed["home_score"] == 2
        assert parsed["away_score"] == 1

    def test_scraping_metrics_model_dump_json(self):
        """Test that ScrapingMetrics models can be serialized to JSON."""
        metrics = ScrapingMetrics(
            games_scheduled=10,
            games_scored=8,
            api_calls_successful=15,
            api_calls_failed=2,
            execution_duration_ms=5000,
            errors_encountered=1,
        )

        # Should serialize to valid JSON
        json_str = metrics.model_dump_json()
        parsed = json.loads(json_str)

        assert parsed["games_scheduled"] == 10
        assert parsed["games_scored"] == 8
        assert parsed["api_calls_successful"] == 15
        assert parsed["api_calls_failed"] == 2
        assert parsed["execution_duration_ms"] == 5000
        assert parsed["errors_encountered"] == 1

    def test_match_model_validation_with_custom_serializer(self):
        """Test that custom serializer handles Pydantic models correctly."""
        match = Match(
            match_id="12345",
            match_datetime=datetime(2024, 1, 15, 14, 30),
            competition="MLS Next",
            home_team="Team A",
            away_team="Team B",
        )

        # Test the custom serializer directly
        serialized = MLSScraperLogger._custom_serializer(match)

        # Should return a dictionary (from model_dump())
        assert isinstance(serialized, dict)
        assert serialized["match_id"] == "12345"
        assert serialized["home_team"] == "Team A"
        assert serialized["competition"] == "MLS Next"

    def test_datetime_serialization_with_custom_serializer(self):
        """Test that custom serializer still handles datetime objects."""
        dt = datetime(2024, 1, 15, 14, 30)

        # Test the custom serializer directly
        serialized = MLSScraperLogger._custom_serializer(dt)

        # Should return ISO format string
        assert serialized == "2024-01-15T14:30:00"
