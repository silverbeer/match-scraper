"""Pydantic models for division discovery output."""

from pydantic import BaseModel, Field


class DiscoveredTeam(BaseModel):
    """A team discovered within a division, with the age groups it appears in."""

    team_name: str = Field(
        ..., description="Team name as it appears on the MLS Next website"
    )
    league: str = Field(
        default="Homegrown", description="League (Homegrown or Academy)"
    )
    division: str = Field(..., description="Division name (e.g., Florida)")
    age_groups: list[str] = Field(
        default_factory=list, description="Age groups this team appears in"
    )


class DiscoveredClub(BaseModel):
    """A club discovered via division discovery, in clubs.json-compatible format."""

    club_name: str = Field(..., description="Club name")
    location: str = Field(default="", description="City, State")
    website: str = Field(default="", description="Club website URL")
    teams: list[DiscoveredTeam] = Field(
        default_factory=list, description="Teams belonging to this club"
    )
