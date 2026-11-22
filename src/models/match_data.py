"""
Match data model for RabbitMQ message submission.

This model validates match data before sending to the queue.
It must match the JSON schema defined in missing-table/docs/08-integrations/match-message-schema.json.

NOTE: This is a duplicate of the model in missing-table/backend/models/match_data.py.
This is INTENTIONAL to avoid cross-repo dependencies. The contract is enforced
via the JSON schema and contract tests, not shared Python code.
"""

from datetime import date as DateType
from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel,
    Field,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
    model_validator,
)

# Competitions missing-table has a `leagues` row for.
VALID_LEAGUES = ("Homegrown", "Academy", "Flex")

# Present only on a tournament message (SB-1746). missing-table reads a
# message as a tournament message by its tournament_id.
TOURNAMENT_FIELDS = (
    "tournament_id",
    "competition",
    "tournament_group",
    "tournament_round",
    "tournament_round_order",
)


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
    match_time: str | None = Field(
        None,
        pattern=r"^\d{2}:\d{2}$",
        description="Match kick-off time HH:MM (24h)",
    )
    # The feed's exact kick-off instant. match_time is the venue's wall clock
    # with no zone; missing-table prefers this when present (SB-1202/1203).
    scheduled_kickoff: datetime | None = Field(
        None, description="Exact kick-off, ISO 8601 with a UTC offset"
    )
    division: str | None = Field(None, description="Division name")
    division_id: int | None = Field(None, ge=1, description="Division ID")
    league: str | None = Field(None, description="League name (Homegrown or Academy)")
    home_score: int | None = Field(None, ge=0, description="Home team score")
    away_score: int | None = Field(None, ge=0, description="Away team score")
    # An MLS NEXT Flex fixture cannot end level: a regulation draw is decided
    # on penalties (SB-1019). This model is what actually goes on the wire —
    # MatchQueueClient publishes the validated model, not the dict it was
    # handed — so a field missing here is dropped between the builder and the
    # queue however many senders set it (SB-1025).
    home_penalty_score: int | None = Field(
        None,
        ge=0,
        description="Home penalty shootout score, when a level match went to penalties",
    )
    away_penalty_score: int | None = Field(
        None,
        ge=0,
        description="Away penalty shootout score, when a level match went to penalties",
    )
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
    # Tournament matches (SB-1746). tournament_id is what makes a message a
    # tournament message: missing-table files the match on the tournament
    # instead of in a league division. competition and tournament_group are
    # the feed's own values, sent raw — missing-table composes the stored
    # group from them.
    tournament_id: int | None = Field(
        None, ge=1, description="missing-table tournaments.id"
    )
    competition: str | None = Field(
        None, description="The feed's competition name, e.g. 'HD Group Play'"
    )
    tournament_group: str | None = Field(
        None, description="The feed's group label, e.g. 'A'"
    )
    tournament_round: str | None = Field(
        None,
        pattern=r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$",
        max_length=40,
        description="Round key, e.g. 'group_stage', 'round_of_16'",
    )
    tournament_round_order: int | None = Field(
        None, ge=0, description="Position within the round"
    )

    @model_validator(mode="after")
    def validate_tournament(self) -> "MatchData":
        """The rules missing-table drops a tournament message for.

        Checked here for the same reason as the shootout: a message that
        would be recorded as `invalid` on the far side of the queue is
        refused at the sender instead, where it can still be named.
        """
        if self.tournament_id is None:
            sent = [
                name for name in TOURNAMENT_FIELDS if getattr(self, name) is not None
            ]
            if sent:
                raise ValueError(f"{', '.join(sent)} requires tournament_id")
            return self
        if not self.external_match_id:
            raise ValueError("A tournament match requires external_match_id")
        if self.match_type.lower() != "tournament":
            raise ValueError(
                "A tournament match must have match_type 'Tournament', "
                f"not {self.match_type!r}"
            )
        if self.division is not None:
            raise ValueError("A tournament match must not carry a division")
        return self

    @model_serializer(mode="wrap")
    def omit_tournament_fields_on_league_messages(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, object]:
        """Keep a league message byte-for-byte what it was before SB-1746.

        The tournament keys are emitted only on a tournament message, so
        nothing new reaches the league path of a consumer that has not been
        told about them.
        """
        data: dict[str, object] = handler(self)
        if self.tournament_id is None:
            for name in TOURNAMENT_FIELDS:
                data.pop(name, None)
        return data

    @model_validator(mode="after")
    def validate_shootout(self) -> "MatchData":
        """A shootout is a pair, and only exists on a level score.

        Both rules are missing-table's, enforced by CHECK constraints on the
        matches table. Rejecting here means a malformed pair is caught at the
        sender, where the fixture can still be logged with its name, rather
        than at an insert that fails on the far side of a queue.
        """
        home, away = self.home_penalty_score, self.away_penalty_score
        if home is None and away is None:
            return self
        if home is None or away is None:
            raise ValueError(
                f"Penalty scores must be given as a pair: home={home}, away={away}"
            )
        if self.home_score is None or self.away_score is None:
            raise ValueError("Penalty scores require a regulation score")
        if self.home_score != self.away_score:
            raise ValueError(
                "Penalty scores are only valid when regulation ended level, "
                f"but the score was {self.home_score}-{self.away_score}"
            )
        return self

    @field_validator("scheduled_kickoff")
    @classmethod
    def kickoff_has_offset(cls, value: datetime | None) -> datetime | None:
        """A kick-off without a UTC offset is the ambiguity this field ends."""
        if value is not None and value.tzinfo is None:
            raise ValueError("scheduled_kickoff must carry a UTC offset")
        return value

    @field_validator("league")
    @classmethod
    def validate_league(cls, v: str | None) -> str | None:
        """Validate the league is one missing-table has a row for.

        Flex joined in 2026-2027 (SB-836). It is a distinct competition, not a
        variant of Homegrown: missing-table carries it as its own `leagues` row
        so that Flex bracket names can coexist with the Homegrown ones they
        collide with, and so Flex goals do not land in the League Golden Boot.

        This list is duplicated by design in missing-table's own
        models/match_data.py and in match-message-schema.json — the contract is
        enforced by the schema and contract tests, not by shared code. Change
        one, change all three.
        """
        if v is not None and v not in VALID_LEAGUES:
            raise ValueError(f"League must be one of: {', '.join(VALID_LEAGUES)}")
        return v

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
                    "division_id": 41,
                    "league": "Homegrown",
                    "home_score": 2,
                    "away_score": 1,
                    "match_status": "completed",
                    "external_match_id": "mlsnext_12345",
                    "location": "Toyota Park",
                    "source": "match-scraper",
                }
            ]
        }
