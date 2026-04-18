from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator


class QoPRanking(BaseModel):
    rank: int = Field(ge=1, description="Team's rank in the division")
    team_name: str = Field(..., description="Full team name as displayed on MLS Next")
    matches_played: int = Field(ge=0, description="Number of matches played")
    att_score: float = Field(description="Attacking score")
    def_score: float = Field(description="Defensive score")
    qop_score: float = Field(description="Overall Quality of Play score")

    @field_validator("team_name")
    @classmethod
    def strip_team_name(cls, v: str) -> str:
        return v.strip()

    class Config:
        json_schema_extra = {
            "example": {
                "rank": 1,
                "team_name": "New York City FC",
                "matches_played": 16,
                "att_score": 89.6,
                "def_score": 83.1,
                "qop_score": 87.6,
            }
        }


class QoPSnapshot(BaseModel):
    """A full snapshot for a division/age-group at a point in time."""

    detected_at: date = Field(
        description=(
            "ISO date the scraper first observed this set of rankings. "
            "MT keys snapshot identity on this date, so a re-scrape on the "
            "same day with the same data is a no-op; a re-scrape with "
            "different data on a later day lands as a new snapshot."
        )
    )
    division: str = Field(description="Division name, e.g. 'Northeast'")
    age_group: str = Field(description="Age group, e.g. 'U14'")
    scraped_at: datetime = Field(description="When the snapshot was taken")
    rankings: list[QoPRanking] = Field(
        default_factory=list, description="Ordered list of team rankings"
    )

    @field_validator("division")
    @classmethod
    def normalize_division(cls, v: str) -> str:
        return v.strip().title()

    @field_validator("age_group")
    @classmethod
    def normalize_age_group(cls, v: str) -> str:
        v = v.strip()
        if v.upper().startswith("U"):
            return "U" + v[1:]
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "detected_at": "2026-04-18",
                "division": "Northeast",
                "age_group": "U14",
                "scraped_at": "2026-04-18T10:00:00Z",
                "rankings": [
                    {
                        "rank": 1,
                        "team_name": "New York City FC",
                        "matches_played": 16,
                        "att_score": 89.6,
                        "def_score": 83.1,
                        "qop_score": 87.6,
                    }
                ],
            }
        }
