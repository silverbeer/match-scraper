"""Data models for MLS Match Scraper.

Contains Pydantic models for match data, metrics, and validation methods.
"""

import re
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class Match(BaseModel):
    """Represents a soccer match with all relevant information.

    Attributes:
        match_id: Unique identifier for the match
        home_team: Name of the home team
        away_team: Name of the away team
        match_date: Date and time of the match
        match_time: Optional time string (e.g., "3:00 PM")
        venue: Optional venue name where match is played
        age_group: Age group category (e.g., "U14")
        division: Division name (e.g., "Northeast")
        competition: Optional competition name
        status: Match status ("scheduled", "in_progress", "completed")
        home_score: Optional home team score (for completed matches)
        away_score: Optional away team score (for completed matches)
    """

    match_id: str = Field(
        ..., min_length=1, description="Unique identifier for the match"
    )
    home_team: str = Field(..., min_length=1, description="Name of the home team")
    away_team: str = Field(..., min_length=1, description="Name of the away team")
    match_date: datetime = Field(..., description="Date and time of the match")
    match_time: Optional[str] = Field(None, description="Time string (e.g., '3:00 PM')")
    venue: Optional[str] = Field(None, description="Venue name where match is played")
    age_group: Literal["U13", "U14", "U15", "U16", "U17", "U18", "U19"] = Field(
        ..., description="Age group category"
    )
    division: str = Field(..., min_length=1, description="Division name")
    competition: Optional[str] = Field(None, description="Competition name")
    status: Literal["scheduled", "in_progress", "completed"] = Field(
        ..., description="Match status"
    )
    home_score: Optional[int] = Field(None, ge=0, description="Home team score")
    away_score: Optional[int] = Field(None, ge=0, description="Away team score")

    @field_validator("match_time")
    @classmethod
    def validate_match_time(cls, v: Optional[str]) -> Optional[str]:
        """Validate match_time format."""
        if v is None:
            return v

        time_pattern = r"^(1[0-2]|0?[1-9]):[0-5][0-9]\s?(AM|PM)$"
        if not re.match(time_pattern, v, re.IGNORECASE):
            raise ValueError(
                f"Invalid match_time format: {v}. Expected format: 'H:MM AM/PM'"
            )
        return v

    @model_validator(mode="after")
    def validate_teams_different(self) -> "Match":
        """Validate that home and away teams are different."""
        if self.home_team.strip().lower() == self.away_team.strip().lower():
            raise ValueError("home_team and away_team cannot be the same")
        return self

    @model_validator(mode="after")
    def validate_score_consistency(self) -> "Match":
        """Validate score consistency with match status."""
        if self.status == "completed":
            if self.home_score is None or self.away_score is None:
                raise ValueError(
                    "Completed matches must have both home_score and away_score"
                )
        elif self.status == "scheduled":
            if self.home_score is not None or self.away_score is not None:
                raise ValueError("Scheduled matches cannot have scores")
        return self

    def has_score(self) -> bool:
        """Check if the match has score information.

        Returns:
            bool: True if both home and away scores are available
        """
        return self.home_score is not None and self.away_score is not None

    def is_completed(self) -> bool:
        """Check if the match is completed.

        Returns:
            bool: True if match status is completed
        """
        return self.status == "completed"

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
