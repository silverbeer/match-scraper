"""
Match data model for RabbitMQ message submission.

This model validates match data before sending to the queue.
It must match the JSON schema defined in missing-table/docs/08-integrations/match-message-schema.json.

NOTE: This is a duplicate of the model in missing-table/backend/models/match_data.py.
This is INTENTIONAL to avoid cross-repo dependencies. The contract is enforced
via the JSON schema and contract tests, not shared Python code.
"""

from datetime import date as DateType
from typing import Literal

from pydantic import BaseModel, Field


class MatchData(BaseModel):
    """
    Match data model - must match match-message-schema.json.

    This is used by the producer (match-scraper) to validate messages
    before sending to RabbitMQ.
    """

    # Required fields
    home_team: str = Field(..., min_length=1, description="Home team name")
    away_team: str = Field(..., min_length=1, description="Away team name")
    match_date: DateType = Field(..., description="Match date")
    season: str = Field(..., min_length=1, description="Season identifier")
    age_group: str = Field(..., min_length=1, description="Age group")
    match_type: str = Field(..., min_length=1, description="Match type")

    # Optional fields
    division: str | None = Field(None, description="Division name")
    home_score: int | None = Field(None, ge=0, description="Home team score")
    away_score: int | None = Field(None, ge=0, description="Away team score")
    match_status: (
        Literal["scheduled", "tbd", "completed", "postponed", "cancelled"] | None
    ) = Field(None, description="Match status (tbd = match played, score pending)")
    external_match_id: str | None = Field(
        None, description="External match ID for deduplication"
    )
    location: str | None = Field(None, description="Match location/venue")
    notes: str | None = Field(None, description="Additional notes")
    source: str | None = Field(
        None, description="Data source (e.g., 'match-scraper', 'manual')"
    )

    class Config:
        """Pydantic configuration."""

        json_schema_extra = {
            "examples": [
                {
                    "home_team": "Chicago Fire Juniors",
                    "away_team": "Indiana Fire Academy",
                    "match_date": "2025-10-13",
                    "season": "2024-25",
                    "age_group": "U14",
                    "match_type": "League",
                    "division": "Northeast",
                    "home_score": 2,
                    "away_score": 1,
                    "match_status": "completed",
                    "external_match_id": "mlsnext_12345",
                    "location": "Toyota Park",
                    "source": "match-scraper",
                }
            ]
        }
