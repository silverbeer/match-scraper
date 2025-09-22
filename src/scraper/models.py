"""Data models for MLS Match Scraper.

Contains Pydantic models for match data, metrics, and validation methods.
"""

import re
from datetime import datetime
from typing import Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator, computed_field


class Match(BaseModel):
    """Represents a soccer match with all relevant information.

    Attributes:
        match_id: Unique identifier for the match
        match_datetime: Date and time of the match
        location: Venue/location where match is played
        competition: Competition name
        home_team: Name of the home team
        away_team: Name of the away team
        home_score: Optional home team score (for completed matches)
        away_score: Optional away team score (for completed matches)
        match_status: Calculated status based on datetime and scores
    """

    match_id: str = Field(
        ..., min_length=1, description="Unique identifier for the match"
    )
    match_datetime: datetime = Field(..., description="Date and time of the match")
    location: Optional[str] = Field(None, description="Venue/location where match is played")
    competition: Optional[str] = Field(None, description="Competition name")
    home_team: str = Field(..., min_length=1, description="Name of the home team")
    away_team: str = Field(..., min_length=1, description="Name of the away team")
    home_score: Optional[Union[int, str]] = Field(None, description="Home team score or 'TBD'")
    away_score: Optional[Union[int, str]] = Field(None, description="Away team score or 'TBD'")

    @computed_field
    @property
    def match_status(self) -> Literal["scheduled", "completed", "TBD"]:
        """Calculate match status based on datetime and scores.

        Rules:
        - If match_datetime is in the past and both scores exist: "completed"
        - If match_datetime is in the past and TBD detected in scores: "TBD"
        - If match_datetime is in the future: "scheduled"
        """
        now = datetime.now(self.match_datetime.tzinfo) if self.match_datetime.tzinfo else datetime.now()

        if self.match_datetime > now:
            return "scheduled"

        # Match is in the past
        if (self.home_score is not None and self.away_score is not None and
            isinstance(self.home_score, int) and isinstance(self.away_score, int)):
            return "completed"

        # Check for TBD in scores
        if (str(self.home_score).upper() == "TBD" or str(self.away_score).upper() == "TBD" or
            self.home_score is None or self.away_score is None):
            return "TBD"

        return "completed"

    @field_validator("home_score", "away_score")
    @classmethod
    def validate_score(cls, v: Optional[Union[int, str]]) -> Optional[Union[int, str]]:
        """Validate score field - can be int, 'TBD', or None."""
        if v is None:
            return v
        if isinstance(v, int) and v >= 0:
            return v
        if isinstance(v, str) and v.upper() == "TBD":
            return v.upper()
        if isinstance(v, str) and v.isdigit():
            return int(v)
        raise ValueError(f"Score must be a non-negative integer or 'TBD', got: {v}")

    @model_validator(mode="after")
    def validate_teams_different(self) -> "Match":
        """Validate that home and away teams are different."""
        if self.home_team.strip().lower() == self.away_team.strip().lower():
            raise ValueError("home_team and away_team cannot be the same")
        return self

    def has_score(self) -> bool:
        """Check if the match has score information.

        Returns:
            bool: True if both home and away scores are available and not TBD
        """
        return (self.home_score is not None and self.away_score is not None and
                isinstance(self.home_score, int) and isinstance(self.away_score, int))

    def is_completed(self) -> bool:
        """Check if the match is completed.

        Returns:
            bool: True if match status is completed
        """
        return self.match_status == "completed"

    def get_score_string(self) -> Optional[str]:
        """Get formatted score string.

        Returns:
            Optional[str]: Score in format "home_score - away_score" or None if no scores
        """
        if self.has_score():
            return f"{self.home_score} - {self.away_score}"
        return None


class ScrapingMetrics(BaseModel):
    """Metrics for tracking scraping execution performance.

    Attributes:
        games_scheduled: Number of scheduled games found
        games_scored: Number of games with scores found
        api_calls_successful: Number of successful API calls
        api_calls_failed: Number of failed API calls
        execution_duration_ms: Total execution time in milliseconds
        errors_encountered: Number of errors encountered during scraping
    """

    games_scheduled: int = Field(
        ..., ge=0, description="Number of scheduled games found"
    )
    games_scored: int = Field(
        ..., ge=0, description="Number of games with scores found"
    )
    api_calls_successful: int = Field(
        ..., ge=0, description="Number of successful API calls"
    )
    api_calls_failed: int = Field(..., ge=0, description="Number of failed API calls")
    execution_duration_ms: int = Field(
        ..., ge=0, description="Total execution time in milliseconds"
    )
    errors_encountered: int = Field(
        ..., ge=0, description="Number of errors encountered during scraping"
    )

    @model_validator(mode="after")
    def validate_games_scored_not_exceed_scheduled(self) -> "ScrapingMetrics":
        """Validate that games_scored does not exceed games_scheduled."""
        if self.games_scored > self.games_scheduled:
            raise ValueError("games_scored cannot exceed games_scheduled")
        return self

    def get_success_rate(self) -> float:
        """Calculate API call success rate.

        Returns:
            float: Success rate as a percentage (0.0 to 100.0)
        """
        total_calls = self.api_calls_successful + self.api_calls_failed
        if total_calls == 0:
            return 0.0
        return (self.api_calls_successful / total_calls) * 100.0

    def get_total_api_calls(self) -> int:
        """Get total number of API calls made.

        Returns:
            int: Sum of successful and failed API calls
        """
        return self.api_calls_successful + self.api_calls_failed

    def has_errors(self) -> bool:
        """Check if any errors were encountered.

        Returns:
            bool: True if errors_encountered > 0
        """
        return self.errors_encountered > 0
