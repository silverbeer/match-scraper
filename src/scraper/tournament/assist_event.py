"""
Read a tournament from the Kitman assist feeds.

The other possible home for MLS NEXT Fest 2026. No tournament has been
published on the assist platform yet, so this adapter is built on what the
league documents are known to carry and is explicit about the part that
cannot be known until a real tournament feed exists.

**Determinable now**, from the v2 standings document :class:`AssistClient`
already reads: the match id (``game_key``), the exact kick-off (``start_time``
in UTC, ``local_timezone``), club names, venue, scores, the shootout, the
competition name, and — through ``competition_bracket_id`` — the bracket and
stage each fixture sits in, with the bracket's age group.

**Not determinable**: what a tournament's stages and brackets will be *called*.
That is one seam, :func:`stage_round_label`. A stage name is passed on as a
round label only when it is a label the mapping already knows, or is listed in
:data:`ASSIST_STAGE_LABELS`. Any other stage name sends no label and is
counted in ``unmapped`` — it is never guessed into a round. Bracket names go
through the mapping's division rules unchanged, which report what they do not
recognise the same way.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from ...models.tournament import TournamentMatch
from ...utils.logger import get_logger
from ..assist_client import (
    SCHEDULE_URL,
    AssistClient,
    AssistEvent,
    AssistFeedError,
    AssistSchedule,
)
from ..modular11 import AGE_GROUP_IDS
from .mapping import KNOWN_LABELS, collapse

logger = get_logger()

# Stage name (lower-cased, spaces collapsed) -> the round label it means.
# Empty until a tournament feed shows what the platform calls its stages; a
# stage that is not here and is not already a known label is reported.
ASSIST_STAGE_LABELS: dict[str, str] = {}

_KNOWN_LABELS_BY_LOWER = {label.lower(): label for label in KNOWN_LABELS}
_AGE = re.compile(r"^U\d{2}\b")


class AssistBracket(BaseModel):
    """Where a fixture sits in a v2 standings document."""

    stage: str | None = Field(default=None, description="Name of the enclosing stage")
    name: str | None = Field(default=None, description="Bracket name")
    age_group: str | None = Field(default=None, description="The bracket's age group")


def stage_round_label(stage: str | None) -> str | None:
    """The round label a stage name stands for, or None when it is not known.

    THE open seam of this adapter (see the module docstring). Recognises only
    what is certain: a stage named exactly like a label the mapping knows, or
    one listed in :data:`ASSIST_STAGE_LABELS`.

    >>> stage_round_label("round of 16")
    'Round of 16'
    >>> stage_round_label("Knockout Stage") is None
    True
    """
    key = collapse(stage).lower()
    if not key:
        return None
    return ASSIST_STAGE_LABELS.get(key) or _KNOWN_LABELS_BY_LOWER.get(key)


def brackets_by_event(payload: dict) -> dict[int, AssistBracket]:
    """Event id -> its bracket, for every fixture of a v2 document that has one."""
    season = payload.get("competition_season") or {}
    ages = {age.get("id"): age.get("name") for age in season.get("age_groups") or []}
    brackets: dict[int, AssistBracket] = {}
    for stage in season.get("competition_season_stages") or []:
        for bracket in stage.get("competition_brackets") or []:
            brackets[bracket.get("id")] = AssistBracket(
                stage=stage.get("name"),
                name=bracket.get("name"),
                age_group=(bracket.get("age_group") or {}).get("name")
                or ages.get(bracket.get("age_group_id")),
            )
    return {
        raw["id"]: brackets[raw.get("competition_bracket_id")]
        for raw in season.get("events") or []
        if raw.get("id") is not None and raw.get("competition_bracket_id") in brackets
    }


class AssistEventSource:
    """All matches of one assist competition season, as tournament matches."""

    name = "assist"
    # The league path sends the bare game_key; a tournament does the same.
    id_prefix = ""

    def __init__(
        self,
        key: str,
        *,
        timezone_name: str = "America/Phoenix",
        save_raw: Path | None = None,
        client: AssistClient | None = None,
    ) -> None:
        self.key = key
        self.timezone_name = timezone_name
        self.save_raw = save_raw
        self._client = client
        self.failures: dict[str, str] = {}
        self.unmapped: dict[str, int] = {}

    async def fetch(
        self, age_groups: Sequence[str], start: date, end: date
    ) -> list[TournamentMatch]:
        """Every match for ``age_groups``; a feed that cannot be read fails them all."""
        self.failures = {}
        self.unmapped = {}
        client = self._client or AssistClient()
        try:
            payload = await client._standings_doc(self.key)
            schedule = AssistSchedule.from_standings(payload)
            if schedule is None:
                # A v1 standings document carries no fixtures or stages; the
                # schedule feed has the fixtures, with nothing to place them.
                payload = await client._fetch_json(SCHEDULE_URL.format(key=self.key))
                schedule = AssistSchedule.model_validate(payload)
                self._count("standings document has no stages: no group or round")
        except AssistFeedError as exc:
            self.failures = dict.fromkeys(age_groups, str(exc))
            return []
        finally:
            if self._client is None:
                await client.aclose()

        self._save(payload)
        return self.tournament_matches(
            schedule.events, brackets_by_event(payload), age_groups, start, end
        )

    def tournament_matches(
        self,
        events: Sequence[AssistEvent],
        brackets: dict[int, AssistBracket],
        age_groups: Sequence[str],
        start: date,
        end: date,
    ) -> list[TournamentMatch]:
        """Convert feed events, keeping the requested ages and dates."""
        wanted = set(age_groups)
        matches: list[TournamentMatch] = []
        for event in sorted(events, key=lambda e: (e.start_time, e.game_key)):
            bracket = brackets.get(event.id, AssistBracket())
            age_group = bracket.age_group or _squad_age(event)
            if age_group is None:
                self._count(f"age group of squad {event.home_squad_name!r}")
                continue
            if age_group not in AGE_GROUP_IDS:
                # Not "an age group nobody asked for": a name this repo does
                # not know ("Under 15"). Dropping it silently would drop the
                # whole feed if that is how the feed names them all.
                self._count(f"age group {age_group!r}")
                continue
            if age_group not in wanted:
                continue
            kickoff_utc, kickoff_local = self._kickoff(event)
            if not start <= kickoff_local.date() <= end:
                continue
            home = event.home_organisation.name if event.home_organisation else None
            away = event.away_organisation.name if event.away_organisation else None
            if not home or not away:
                self._count("fixture with no club name")
                continue

            label = stage_round_label(bracket.stage)
            if bracket.stage and label is None:
                self._count(f"stage {collapse(bracket.stage)!r}")
            home_pens, away_pens = event.shootout()
            matches.append(
                TournamentMatch(
                    source_match_id=event.game_key,
                    age_group=age_group,
                    home_team=home,
                    away_team=away,
                    kickoff_local=kickoff_local,
                    kickoff_utc=kickoff_utc,
                    location=event.event_location.name
                    if event.event_location
                    else None,
                    home_score=event.home_score,
                    away_score=event.away_score,
                    home_penalty_score=home_pens,
                    away_penalty_score=away_pens,
                    competition=event.competition.name if event.competition else None,
                    source_division=bracket.name,
                    source_round_label=label,
                    # round_number exists on the event, but whether it is a
                    # bracket slot is unknown — not sent until it is.
                    bracket_position=None,
                )
            )
        return matches

    def _kickoff(self, event: AssistEvent) -> tuple[datetime, datetime]:
        """``(instant in UTC, venue wall clock)`` for one event."""
        aware = event.start_time
        if aware.tzinfo is None:
            aware = aware.replace(tzinfo=timezone.utc)
        if event.local_timezone:
            return aware, event.local_datetime
        # No zone on the event: the tournament's venue zone, not UTC.
        local = aware.astimezone(ZoneInfo(self.timezone_name))
        return aware, local.replace(tzinfo=None)

    def _count(self, what: str) -> None:
        self.unmapped[what] = self.unmapped.get(what, 0) + 1

    def _save(self, payload: dict) -> None:
        if self.save_raw is None:
            return
        self.save_raw.mkdir(parents=True, exist_ok=True)
        (self.save_raw / f"assist_{self.key}.json").write_text(json.dumps(payload))


def _squad_age(event: AssistEvent) -> str | None:
    """The age group a squad name starts with: ``U14 AD`` -> ``U14``."""
    found = _AGE.match(collapse(event.home_squad_name))
    return found.group(0) if found else None
