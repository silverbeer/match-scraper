"""
Source-agnostic tournament match, and the one builder that turns it into the
message missing-table receives.

A tournament source (modular11 event, assist feed) returns
:class:`TournamentMatch` rows holding only what the feed says. Everything that
decides what goes on the wire — the id, the kick-off instant, the status, the
round key — happens in :meth:`TournamentMatch.to_message`, so two sources
cannot drift apart the way the two league submit paths did (see
``tests/unit/test_submit_paths_agree.py``).

``scraper.models.Match`` is deliberately not reused: its status compares a
naive venue time with ``datetime.now()``, which is the scraping host's clock,
not the venue's.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator

from ..scraper.modular11 import current_season_year, season_label
from ..scraper.tournament.mapping import MappedRound, league_for, map_round
from .match_data import MatchData

# missing-table looks the match type up by this name on a tournament message.
TOURNAMENT_MATCH_TYPE = "Tournament"
# What the live sender writes in `source`; missing-table re-files tournament
# columns on rows carrying it.
MESSAGE_SOURCE = "match-scraper-agent"
# How a feed names a team that is not decided yet (compared case-folded).
PLACEHOLDER_TEAM = "tbd"


class TournamentContext(BaseModel):
    """What a run knows that no single row does."""

    tournament_id: int = Field(..., ge=1, description="missing-table tournaments.id")
    timezone: str = Field(
        default="America/Phoenix",
        description="IANA zone of the venue; localises a source's wall-clock times",
    )
    source: str = Field(
        default=MESSAGE_SOURCE, description="Provenance tag for the message"
    )
    stand_in: bool = Field(
        default=False,
        description="True when tournament_id is a dry run's stand-in, not a real "
        "id. A stand-in context must never be published",
    )
    id_prefix: str = Field(
        default="",
        description="Prepended to the source match id, e.g. 'm11-75-'",
    )

    @field_validator("timezone")
    @classmethod
    def timezone_exists(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Unknown timezone {value!r}") from exc
        return value


class TournamentMatch(BaseModel):
    """One tournament fixture, exactly as its source describes it."""

    source_match_id: str = Field(..., min_length=1, description="The feed's match id")
    age_group: str = Field(..., min_length=1, description="Age group, e.g. U15")
    home_team: str = Field(..., min_length=1, description="Home team, as the feed")
    away_team: str = Field(..., min_length=1, description="Away team, as the feed")
    kickoff_local: datetime = Field(
        ...,
        description="Venue wall clock, naive. Midnight means the time is not set",
    )
    kickoff_utc: datetime | None = Field(
        default=None,
        description="The exact instant, when the source states one (assist)",
    )
    location: str | None = Field(default=None, description="Venue/pitch")
    home_score: int | None = Field(default=None, ge=0, description="Home goals")
    away_score: int | None = Field(default=None, ge=0, description="Away goals")
    home_penalty_score: int | None = Field(
        default=None, ge=0, description="Home shootout"
    )
    away_penalty_score: int | None = Field(
        default=None, ge=0, description="Away shootout"
    )
    competition: str | None = Field(default=None, description="Competition, raw")
    source_division: str | None = Field(default=None, description="Division/group, raw")
    source_round_label: str | None = Field(default=None, description="Round label, raw")
    bracket_position: int | None = Field(
        default=None,
        ge=0,
        description="Position within the round, only when the feed has a unique one",
    )

    @field_validator("kickoff_local")
    @classmethod
    def kickoff_local_is_naive(cls, value: datetime) -> datetime:
        if value.tzinfo is not None:
            raise ValueError("kickoff_local is a wall clock and carries no zone")
        return value

    @field_validator("kickoff_utc")
    @classmethod
    def kickoff_utc_is_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("kickoff_utc must carry a UTC offset")
        return value

    def mapped(self) -> MappedRound:
        """This row's round key and group, per the mapping tables."""
        return map_round(
            self.competition, self.source_division, self.source_round_label
        )

    def teams_known(self) -> bool:
        """False for a fixture the feed lists before its teams are decided.

        Such a row has ``TBD`` for a team. missing-table has a real team row
        of that name, so the match must not be sent: it would be filed on it.
        It is picked up once the feed names the teams.
        """
        return not {self.home_team.casefold(), self.away_team.casefold()} & {
            PLACEHOLDER_TEAM
        }

    def has_score(self) -> bool:
        return self.home_score is not None and self.away_score is not None

    def kickoff(self, ctx: TournamentContext) -> datetime:
        """The kick-off as an aware datetime in UTC."""
        if self.kickoff_utc is not None:
            return self.kickoff_utc.astimezone(timezone.utc)
        local = self.kickoff_local.replace(tzinfo=ZoneInfo(ctx.timezone))
        return local.astimezone(timezone.utc)

    def to_message(
        self, ctx: TournamentContext, *, now: datetime | None = None
    ) -> MatchData:
        """Build the queue message. The only place one is built."""
        mapped = self.mapped()
        kickoff = self.kickoff(ctx)
        # Midnight is the feed's "time not set" (scraper.models.Match applies
        # the same rule): send the date alone rather than a 00:00 kick-off
        # that would overwrite a real one.
        time_set = bool(self.kickoff_local.hour or self.kickoff_local.minute)

        now = now or datetime.now(timezone.utc)
        status: Literal["scheduled", "tbd", "completed"]
        if self.has_score():
            status = "completed"
        else:
            # Never "live": this is a schedule read, not a live score. Without
            # a time the match is not overdue until its day is.
            due = kickoff if time_set else kickoff + timedelta(days=1)
            status = "scheduled" if due > now else "tbd"

        # Penalties only on a level score, and never 0:0 — the feed's way of
        # saying "no shootout" (AssistEvent.shootout, MatchData.validate_shootout).
        home_pens, away_pens = self.home_penalty_score, self.away_penalty_score
        if (
            home_pens is None
            or away_pens is None
            or not self.has_score()
            or self.home_score != self.away_score
            or (home_pens == 0 and away_pens == 0)
        ):
            home_pens = away_pens = None

        match_date = self.kickoff_local.date()
        return MatchData(
            home_team=self.home_team,
            away_team=self.away_team,
            match_date=match_date,
            match_time=self.kickoff_local.strftime("%H:%M") if time_set else None,
            scheduled_kickoff=kickoff if time_set else None,
            season=season_label(current_season_year(match_date)),
            age_group=self.age_group,
            match_type=TOURNAMENT_MATCH_TYPE,
            # missing-table rejects a tournament message that has a division.
            division=None,
            division_id=None,
            league=league_for(self.competition),
            home_score=self.home_score if self.has_score() else None,
            away_score=self.away_score if self.has_score() else None,
            home_penalty_score=home_pens,
            away_penalty_score=away_pens,
            match_status=status,
            external_match_id=f"{ctx.id_prefix}{self.source_match_id}",
            location=self.location,
            notes=None,
            source=ctx.source,
            tournament_id=ctx.tournament_id,
            competition=self.competition,
            tournament_group=mapped.group,
            tournament_round=mapped.round_key,
            tournament_round_order=(
                self.bracket_position if mapped.send_round_order else None
            ),
        )
