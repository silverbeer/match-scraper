"""Unit tests for data models."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from src.scraper.models import Match, ScrapingMetrics


class TestMatch:
    """Test cases for Match Pydantic model."""

    def test_valid_match_creation(self):
        """Test creating a valid match object."""
        match = Match(
            match_id="12345",
            home_team="Team A",
            away_team="Team B",
            match_date=datetime(2024, 1, 15, 14, 30),
            match_time="2:30 PM",
            venue="Stadium A",
            age_group="U14",
            division="Northeast",
            competition="MLS Next",
            status="scheduled",
        )

        assert match.match_id == "12345"
        assert match.home_team == "Team A"
        assert match.away_team == "Team B"
        assert match.age_group == "U14"
        assert match.status == "scheduled"
        assert match.home_score is None
        assert match.away_score is None

    def test_completed_match_with_scores(self):
        """Test creating a completed match with scores."""
        match = Match(
            match_id="12345",
            home_team="Team A",
            away_team="Team B",
            match_date=datetime(2024, 1, 15, 14, 30),
            match_time="2:30 PM",
            venue="Stadium A",
            age_group="U14",
            division="Northeast",
            competition="MLS Next",
            status="completed",
            home_score=2,
            away_score=1,
        )

        assert match.has_score()
        assert match.is_completed()
        assert match.get_score_string() == "2 - 1"

    def test_match_validation_empty_match_id(self):
        """Test validation fails for empty match_id."""
        with pytest.raises(
            ValidationError, match="String should have at least 1 character"
        ):
            Match(
                match_id="",
                home_team="Team A",
                away_team="Team B",
                match_date=datetime(2024, 1, 15, 14, 30),
                match_time="2:30 PM",
                venue="Stadium A",
                age_group="U14",
                division="Northeast",
                competition="MLS Next",
                status="scheduled",
            )

    def test_match_validation_empty_home_team(self):
        """Test validation fails for empty home_team."""
        with pytest.raises(
            ValidationError, match="String should have at least 1 character"
        ):
            Match(
                match_id="12345",
                home_team="",
                away_team="Team B",
                match_date=datetime(2024, 1, 15, 14, 30),
                match_time="2:30 PM",
                venue="Stadium A",
                age_group="U14",
                division="Northeast",
                competition="MLS Next",
                status="scheduled",
            )

    def test_match_validation_empty_away_team(self):
        """Test validation fails for empty away_team."""
        with pytest.raises(
            ValidationError, match="String should have at least 1 character"
        ):
            Match(
                match_id="12345",
                home_team="Team A",
                away_team="",
                match_date=datetime(2024, 1, 15, 14, 30),
                match_time="2:30 PM",
                venue="Stadium A",
                age_group="U14",
                division="Northeast",
                competition="MLS Next",
                status="scheduled",
            )

    def test_match_validation_same_teams(self):
        """Test validation fails when home and away teams are the same."""
        with pytest.raises(
            ValueError, match="home_team and away_team cannot be the same"
        ):
            Match(
                match_id="12345",
                home_team="Team A",
                away_team="Team A",
                match_date=datetime(2024, 1, 15, 14, 30),
                match_time="2:30 PM",
                venue="Stadium A",
                age_group="U14",
                division="Northeast",
                competition="MLS Next",
                status="scheduled",
            )

    def test_match_validation_invalid_age_group(self):
        """Test validation fails for invalid age_group."""
        with pytest.raises(ValidationError, match="Input should be"):
            Match(
                match_id="12345",
                home_team="Team A",
                away_team="Team B",
                match_date=datetime(2024, 1, 15, 14, 30),
                match_time="2:30 PM",
                venue="Stadium A",
                age_group="U12",  # Invalid age group
                division="Northeast",
                competition="MLS Next",
                status="scheduled",
            )

    def test_match_validation_invalid_status(self):
        """Test validation fails for invalid status."""
        with pytest.raises(ValidationError, match="Input should be"):
            Match(
                match_id="12345",
                home_team="Team A",
                away_team="Team B",
                match_date=datetime(2024, 1, 15, 14, 30),
                match_time="2:30 PM",
                venue="Stadium A",
                age_group="U14",
                division="Northeast",
                competition="MLS Next",
                status="invalid_status",
            )

    def test_match_validation_invalid_time_format(self):
        """Test validation fails for invalid match_time format."""
        with pytest.raises(ValueError, match="Invalid match_time format"):
            Match(
                match_id="12345",
                home_team="Team A",
                away_team="Team B",
                match_date=datetime(2024, 1, 15, 14, 30),
                match_time="25:00 PM",  # Invalid time
                venue="Stadium A",
                age_group="U14",
                division="Northeast",
                competition="MLS Next",
                status="scheduled",
            )

    def test_match_validation_negative_scores(self):
        """Test validation fails for negative scores."""
        with pytest.raises(
            ValidationError, match="Input should be greater than or equal to 0"
        ):
            Match(
                match_id="12345",
                home_team="Team A",
                away_team="Team B",
                match_date=datetime(2024, 1, 15, 14, 30),
                match_time="2:30 PM",
                venue="Stadium A",
                age_group="U14",
                division="Northeast",
                competition="MLS Next",
                status="completed",
                home_score=-1,
                away_score=2,
            )

    def test_match_validation_completed_without_scores(self):
        """Test validation fails for completed match without scores."""
        with pytest.raises(
            ValueError,
            match="Completed matches must have both home_score and away_score",
        ):
            Match(
                match_id="12345",
                home_team="Team A",
                away_team="Team B",
                match_date=datetime(2024, 1, 15, 14, 30),
                match_time="2:30 PM",
                venue="Stadium A",
                age_group="U14",
                division="Northeast",
                competition="MLS Next",
                status="completed",
            )

    def test_match_validation_scheduled_with_scores(self):
        """Test validation fails for scheduled match with scores."""
        with pytest.raises(ValueError, match="Scheduled matches cannot have scores"):
            Match(
                match_id="12345",
                home_team="Team A",
                away_team="Team B",
                match_date=datetime(2024, 1, 15, 14, 30),
                match_time="2:30 PM",
                venue="Stadium A",
                age_group="U14",
                division="Northeast",
                competition="MLS Next",
                status="scheduled",
                home_score=2,
                away_score=1,
            )

    def test_match_has_score_method(self):
        """Test has_score method."""
        # Match without scores
        match_no_score = Match(
            match_id="12345",
            home_team="Team A",
            away_team="Team B",
            match_date=datetime(2024, 1, 15, 14, 30),
            match_time="2:30 PM",
            venue="Stadium A",
            age_group="U14",
            division="Northeast",
            competition="MLS Next",
            status="scheduled",
        )
        assert not match_no_score.has_score()

        # Match with scores
        match_with_score = Match(
            match_id="12345",
            home_team="Team A",
            away_team="Team B",
            match_date=datetime(2024, 1, 15, 14, 30),
            match_time="2:30 PM",
            venue="Stadium A",
            age_group="U14",
            division="Northeast",
            competition="MLS Next",
            status="completed",
            home_score=2,
            away_score=1,
        )
        assert match_with_score.has_score()

    def test_match_is_completed_method(self):
        """Test is_completed method."""
        # Scheduled match
        scheduled_match = Match(
            match_id="12345",
            home_team="Team A",
            away_team="Team B",
            match_date=datetime(2024, 1, 15, 14, 30),
            match_time="2:30 PM",
            venue="Stadium A",
            age_group="U14",
            division="Northeast",
            competition="MLS Next",
            status="scheduled",
        )
        assert not scheduled_match.is_completed()

        # Completed match
        completed_match = Match(
            match_id="12345",
            home_team="Team A",
            away_team="Team B",
            match_date=datetime(2024, 1, 15, 14, 30),
            match_time="2:30 PM",
            venue="Stadium A",
            age_group="U14",
            division="Northeast",
            competition="MLS Next",
            status="completed",
            home_score=2,
            away_score=1,
        )
        assert completed_match.is_completed()

    def test_match_get_score_string_method(self):
        """Test get_score_string method."""
        # Match without scores
        match_no_score = Match(
            match_id="12345",
            home_team="Team A",
            away_team="Team B",
            match_date=datetime(2024, 1, 15, 14, 30),
            match_time="2:30 PM",
            venue="Stadium A",
            age_group="U14",
            division="Northeast",
            competition="MLS Next",
            status="scheduled",
        )
        assert match_no_score.get_score_string() is None

        # Match with scores
        match_with_score = Match(
            match_id="12345",
            home_team="Team A",
            away_team="Team B",
            match_date=datetime(2024, 1, 15, 14, 30),
            match_time="2:30 PM",
            venue="Stadium A",
            age_group="U14",
            division="Northeast",
            competition="MLS Next",
            status="completed",
            home_score=3,
            away_score=0,
        )
        assert match_with_score.get_score_string() == "3 - 0"

    def test_match_valid_time_formats(self):
        """Test various valid time formats."""
        valid_times = ["12:00 PM", "1:30 AM", "11:59 PM", "12:01 AM", "9:15 AM"]

        for time_str in valid_times:
            match = Match(
                match_id="12345",
                home_team="Team A",
                away_team="Team B",
                match_date=datetime(2024, 1, 15, 14, 30),
                match_time=time_str,
                venue="Stadium A",
                age_group="U14",
                division="Northeast",
                competition="MLS Next",
                status="scheduled",
            )
            assert match.match_time == time_str

    def test_match_optional_fields(self):
        """Test match creation with optional fields as None."""
        match = Match(
            match_id="12345",
            home_team="Team A",
            away_team="Team B",
            match_date=datetime(2024, 1, 15, 14, 30),
            match_time=None,
            venue=None,
            age_group="U14",
            division="Northeast",
            competition=None,
            status="scheduled",
        )

        assert match.match_time is None
        assert match.venue is None
        assert match.competition is None


class TestScrapingMetrics:
    """Test cases for ScrapingMetrics Pydantic model."""

    def test_valid_metrics_creation(self):
        """Test creating valid metrics object."""
        metrics = ScrapingMetrics(
            games_scheduled=10,
            games_scored=8,
            api_calls_successful=15,
            api_calls_failed=2,
            execution_duration_ms=5000,
            errors_encountered=1,
        )

        assert metrics.games_scheduled == 10
        assert metrics.games_scored == 8
        assert metrics.api_calls_successful == 15
        assert metrics.api_calls_failed == 2
        assert metrics.execution_duration_ms == 5000
        assert metrics.errors_encountered == 1

    def test_metrics_validation_negative_values(self):
        """Test validation fails for negative values."""
        with pytest.raises(
            ValidationError, match="Input should be greater than or equal to 0"
        ):
            ScrapingMetrics(
                games_scheduled=-1,
                games_scored=8,
                api_calls_successful=15,
                api_calls_failed=2,
                execution_duration_ms=5000,
                errors_encountered=1,
            )

    def test_metrics_validation_non_integer_values(self):
        """Test validation fails for non-integer values."""
        with pytest.raises(ValidationError, match="Input should be a valid integer"):
            ScrapingMetrics(
                games_scheduled=10.5,
                games_scored=8,
                api_calls_successful=15,
                api_calls_failed=2,
                execution_duration_ms=5000,
                errors_encountered=1,
            )

    def test_metrics_validation_games_scored_exceeds_scheduled(self):
        """Test validation fails when games_scored exceeds games_scheduled."""
        with pytest.raises(
            ValueError, match="games_scored cannot exceed games_scheduled"
        ):
            ScrapingMetrics(
                games_scheduled=5,
                games_scored=10,  # More scored than scheduled
                api_calls_successful=15,
                api_calls_failed=2,
                execution_duration_ms=5000,
                errors_encountered=1,
            )

    def test_metrics_get_success_rate_method(self):
        """Test get_success_rate method."""
        # Normal case
        metrics = ScrapingMetrics(
            games_scheduled=10,
            games_scored=8,
            api_calls_successful=15,
            api_calls_failed=5,
            execution_duration_ms=5000,
            errors_encountered=1,
        )
        assert metrics.get_success_rate() == 75.0  # 15/(15+5) * 100

        # No API calls
        metrics_no_calls = ScrapingMetrics(
            games_scheduled=10,
            games_scored=8,
            api_calls_successful=0,
            api_calls_failed=0,
            execution_duration_ms=5000,
            errors_encountered=1,
        )
        assert metrics_no_calls.get_success_rate() == 0.0

        # All successful
        metrics_all_success = ScrapingMetrics(
            games_scheduled=10,
            games_scored=8,
            api_calls_successful=20,
            api_calls_failed=0,
            execution_duration_ms=5000,
            errors_encountered=0,
        )
        assert metrics_all_success.get_success_rate() == 100.0

    def test_metrics_get_total_api_calls_method(self):
        """Test get_total_api_calls method."""
        metrics = ScrapingMetrics(
            games_scheduled=10,
            games_scored=8,
            api_calls_successful=15,
            api_calls_failed=5,
            execution_duration_ms=5000,
            errors_encountered=1,
        )
        assert metrics.get_total_api_calls() == 20

    def test_metrics_has_errors_method(self):
        """Test has_errors method."""
        # With errors
        metrics_with_errors = ScrapingMetrics(
            games_scheduled=10,
            games_scored=8,
            api_calls_successful=15,
            api_calls_failed=5,
            execution_duration_ms=5000,
            errors_encountered=3,
        )
        assert metrics_with_errors.has_errors()

        # Without errors
        metrics_no_errors = ScrapingMetrics(
            games_scheduled=10,
            games_scored=8,
            api_calls_successful=15,
            api_calls_failed=5,
            execution_duration_ms=5000,
            errors_encountered=0,
        )
        assert not metrics_no_errors.has_errors()

    def test_metrics_zero_values(self):
        """Test metrics with all zero values."""
        metrics = ScrapingMetrics(
            games_scheduled=0,
            games_scored=0,
            api_calls_successful=0,
            api_calls_failed=0,
            execution_duration_ms=0,
            errors_encountered=0,
        )

        assert metrics.get_success_rate() == 0.0
        assert metrics.get_total_api_calls() == 0
        assert not metrics.has_errors()
