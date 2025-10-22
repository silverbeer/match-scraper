"""Unit tests for data models."""

from datetime import datetime, timedelta

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
            match_datetime=datetime(2024, 1, 15, 14, 30),
            location="Stadium A",
            competition="MLS Next",
        )

        assert match.match_id == "12345"
        assert match.home_team == "Team A"
        assert match.away_team == "Team B"
        assert match.location == "Stadium A"
        assert match.competition == "MLS Next"
        assert match.home_score is None
        assert match.away_score is None

    def test_completed_match_with_scores(self):
        """Test creating a completed match with scores."""
        # Use a past date to ensure it's marked as completed
        past_date = datetime.now() - timedelta(days=1)
        match = Match(
            match_id="12345",
            home_team="Team A",
            away_team="Team B",
            match_datetime=past_date,
            location="Stadium A",
            competition="MLS Next",
            home_score=2,
            away_score=1,
        )

        assert match.has_score()
        assert match.is_played()
        # Status is now "played" (not "completed")
        assert match.match_status == "completed"
        assert match.get_score_string() == "2 - 1"

    def test_scheduled_match_status(self):
        """Test match status for future matches."""
        future_date = datetime.now() + timedelta(days=1)
        match = Match(
            match_id="future_123",
            home_team="Team A",
            away_team="Team B",
            match_datetime=future_date,
        )

        assert match.match_status == "scheduled"
        assert not match.is_played()
        assert not match.has_score()
        assert match.get_score_string() is None

    def test_tbd_match_status(self):
        """Test match status with TBD scores."""
        past_date = datetime.now() - timedelta(days=1)
        match = Match(
            match_id="tbd_123",
            home_team="Team A",
            away_team="Team B",
            match_datetime=past_date,
            home_score="TBD",
            away_score="TBD",
        )

        assert match.match_status == "tbd"
        assert not match.is_played()
        assert not match.has_score()
        assert match.get_score_string() is None

    def test_tbd_mixed_scores(self):
        """Test match with one TBD score and one regular score."""
        past_date = datetime.now() - timedelta(days=1)
        match = Match(
            match_id="mixed_123",
            home_team="Team A",
            away_team="Team B",
            match_datetime=past_date,
            home_score=2,
            away_score="TBD",
        )

        assert match.match_status == "tbd"
        assert not match.has_score()

    def test_none_scores_past_match(self):
        """Test match in the past with None scores."""
        past_date = datetime.now() - timedelta(days=1)
        match = Match(
            match_id="none_123",
            home_team="Team A",
            away_team="Team B",
            match_datetime=past_date,
            home_score=None,
            away_score=None,
        )

        assert match.match_status == "tbd"
        assert not match.has_score()

    def test_score_validation_positive_int(self):
        """Test score validation with positive integers."""
        match = Match(
            match_id="valid_123",
            home_team="Team A",
            away_team="Team B",
            match_datetime=datetime.now(),
            home_score=0,
            away_score=5,
        )

        assert match.home_score == 0
        assert match.away_score == 5

    def test_score_validation_string_digits(self):
        """Test score validation with string digits."""
        match = Match(
            match_id="string_123",
            home_team="Team A",
            away_team="Team B",
            match_datetime=datetime.now(),
            home_score="3",
            away_score="1",
        )

        assert match.home_score == 3  # Should be converted to int
        assert match.away_score == 1

    def test_score_validation_tbd_case_insensitive(self):
        """Test TBD score validation is case insensitive."""
        match = Match(
            match_id="tbd_case_123",
            home_team="Team A",
            away_team="Team B",
            match_datetime=datetime.now(),
            home_score="tbd",
            away_score="TbD",
        )

        assert match.home_score == "TBD"  # Should be normalized to uppercase
        assert match.away_score == "TBD"

    def test_score_validation_invalid_negative(self):
        """Test score validation fails for negative integers."""
        with pytest.raises(
            ValidationError, match="Score must be a non-negative integer"
        ):
            Match(
                match_id="invalid_123",
                home_team="Team A",
                away_team="Team B",
                match_datetime=datetime.now(),
                home_score=-1,
                away_score=0,
            )

    def test_score_validation_invalid_string(self):
        """Test score validation fails for invalid strings."""
        with pytest.raises(
            ValidationError, match="Score must be a non-negative integer"
        ):
            Match(
                match_id="invalid_123",
                home_team="Team A",
                away_team="Team B",
                match_datetime=datetime.now(),
                home_score="invalid",
                away_score=0,
            )

    def test_teams_validation_same_teams(self):
        """Test validation fails when home and away teams are the same."""
        with pytest.raises(
            ValidationError, match="home_team and away_team cannot be the same"
        ):
            Match(
                match_id="same_123",
                home_team="Team A",
                away_team="Team A",
                match_datetime=datetime.now(),
            )

    def test_teams_validation_same_teams_case_insensitive(self):
        """Test validation fails for same teams with different cases."""
        with pytest.raises(
            ValidationError, match="home_team and away_team cannot be the same"
        ):
            Match(
                match_id="case_123",
                home_team="Team A",
                away_team="team a",
                match_datetime=datetime.now(),
            )

    def test_teams_validation_same_teams_with_spaces(self):
        """Test validation fails for same teams with extra spaces."""
        with pytest.raises(
            ValidationError, match="home_team and away_team cannot be the same"
        ):
            Match(
                match_id="spaces_123",
                home_team=" Team A ",
                away_team="Team A",
                match_datetime=datetime.now(),
            )

    def test_optional_fields(self):
        """Test that optional fields work correctly."""
        match = Match(
            match_id="optional_123",
            home_team="Team A",
            away_team="Team B",
            match_datetime=datetime.now(),
            location=None,
            competition=None,
        )

        assert match.location is None
        assert match.competition is None

    def test_match_validation_empty_match_id(self):
        """Test validation fails for empty match_id."""
        with pytest.raises(
            ValidationError, match="String should have at least 1 character"
        ):
            Match(
                match_id="",
                home_team="Team A",
                away_team="Team B",
                match_datetime=datetime.now(),
            )

    def test_match_validation_empty_team_names(self):
        """Test validation fails for empty team names."""
        with pytest.raises(
            ValidationError, match="String should have at least 1 character"
        ):
            Match(
                match_id="12345",
                home_team="",  # Empty home team
                away_team="Team B",
                match_datetime=datetime.now(),
            )

        with pytest.raises(
            ValidationError, match="String should have at least 1 character"
        ):
            Match(
                match_id="12345",
                home_team="Team A",
                away_team="",  # Empty away team
                match_datetime=datetime.now(),
            )


class TestScrapingMetrics:
    """Test cases for ScrapingMetrics model."""

    def test_valid_metrics_creation(self):
        """Test creating valid ScrapingMetrics."""
        metrics = ScrapingMetrics(
            games_scheduled=10,
            games_scored=5,
            api_calls_successful=8,
            api_calls_failed=2,
            execution_duration_ms=5000,
            errors_encountered=1,
        )

        assert metrics.games_scheduled == 10
        assert metrics.games_scored == 5
        assert metrics.api_calls_successful == 8
        assert metrics.api_calls_failed == 2
        assert metrics.execution_duration_ms == 5000
        assert metrics.errors_encountered == 1

    def test_metrics_validation_negative_values(self):
        """Test that negative values are not allowed."""
        with pytest.raises(ValidationError):
            ScrapingMetrics(
                games_scheduled=-1,
                games_scored=5,
                api_calls_successful=8,
                api_calls_failed=2,
                execution_duration_ms=5000,
                errors_encountered=1,
            )

    def test_metrics_with_zero_values(self):
        """Test that zero values are allowed."""
        metrics = ScrapingMetrics(
            games_scheduled=0,
            games_scored=0,
            api_calls_successful=0,
            api_calls_failed=0,
            execution_duration_ms=0,
            errors_encountered=0,
        )

        assert metrics.games_scheduled == 0
        assert metrics.games_scored == 0
        assert metrics.api_calls_successful == 0
        assert metrics.api_calls_failed == 0

    def test_metrics_games_scored_validation(self):
        """Test that games_scored cannot exceed games_scheduled."""
        with pytest.raises(
            ValidationError, match="games_scored cannot exceed games_scheduled"
        ):
            ScrapingMetrics(
                games_scheduled=5,
                games_scored=10,  # More than scheduled
                api_calls_successful=8,
                api_calls_failed=2,
                execution_duration_ms=5000,
                errors_encountered=1,
            )

    def test_get_success_rate_method(self):
        """Test get_success_rate method."""
        # Test with successful calls
        metrics = ScrapingMetrics(
            games_scheduled=10,
            games_scored=5,
            api_calls_successful=8,
            api_calls_failed=2,
            execution_duration_ms=5000,
            errors_encountered=1,
        )

        assert metrics.get_success_rate() == 80.0  # 8/(8+2) * 100

    def test_get_success_rate_no_calls(self):
        """Test get_success_rate when no API calls were made."""
        metrics = ScrapingMetrics(
            games_scheduled=0,
            games_scored=0,
            api_calls_successful=0,
            api_calls_failed=0,
            execution_duration_ms=0,
            errors_encountered=0,
        )

        assert metrics.get_success_rate() == 0.0
