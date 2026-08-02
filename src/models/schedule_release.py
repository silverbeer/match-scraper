"""
Models describing whether an MLS Next schedule has been published yet.

A release probe answers one question per (age group, division) pair: has MLS
Next published fixtures for this season? The page is up year-round, so "up" is
not the signal — fixture count is. The probe distinguishes three states so an
unattended poller can stay quiet on the boring ones:

* ``EMPTY``   — endpoint healthy, zero fixtures. The normal pre-release state.
* ``LIVE``    — fixtures published. This is the state worth waking someone for.
* ``ERROR``   — endpoint unreachable or unparseable. Worth alerting on only if
  it persists, since a single blip is not news.
"""

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class ReleaseState(str, Enum):
    """Publication state of a single age-group/division schedule."""

    EMPTY = "empty"
    LIVE = "live"
    ERROR = "error"


class DivisionRelease(BaseModel):
    """Publication state for one age group within one division."""

    age_group: str = Field(..., description="Age group, e.g. 'U15'")
    division: str = Field(..., description="Division name, e.g. 'Northeast'")
    state: ReleaseState = Field(..., description="Publication state")
    match_count: int = Field(
        default=0,
        ge=0,
        description=(
            "Fixtures on the first page of results. The endpoint paginates at "
            "25 rows, so this is a lower bound on the season total, not the "
            "total itself — enough to decide 'published or not', not enough to "
            "report volume."
        ),
    )
    error: Optional[str] = Field(
        default=None, description="Failure detail when state is 'error'"
    )

    @field_validator("age_group")
    @classmethod
    def normalize_age_group(cls, v: str) -> str:
        v = v.strip().upper()
        if not v:
            raise ValueError("age_group cannot be empty")
        return v

    @field_validator("division")
    @classmethod
    def normalize_division(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("division cannot be empty")
        return v

    @property
    def is_live(self) -> bool:
        """True when fixtures have been published for this target."""
        return self.state is ReleaseState.LIVE

    @property
    def label(self) -> str:
        """Human-readable target name, e.g. ``'U15 Northeast'``."""
        return f"{self.age_group} {self.division}"

    class Config:
        json_schema_extra = {
            "example": {
                "age_group": "U15",
                "division": "Northeast",
                "state": "live",
                "match_count": 128,
                "error": None,
            }
        }


class ReleaseProbe(BaseModel):
    """The full result of one poll across every target."""

    season: str = Field(..., description="Season identifier, e.g. '2026-2027'")
    window_start: date = Field(..., description="First date searched for fixtures")
    window_end: date = Field(..., description="Last date searched for fixtures")
    checked_at: datetime = Field(..., description="When the poll ran (UTC)")
    results: list[DivisionRelease] = Field(
        default_factory=list, description="One entry per age group/division probed"
    )

    @property
    def live(self) -> list[DivisionRelease]:
        """Targets whose fixtures have been published."""
        return [r for r in self.results if r.state is ReleaseState.LIVE]

    @property
    def errors(self) -> list[DivisionRelease]:
        """Targets whose probe failed."""
        return [r for r in self.results if r.state is ReleaseState.ERROR]

    @property
    def total_matches(self) -> int:
        """Fixtures found across all targets."""
        return sum(r.match_count for r in self.results)

    @property
    def is_released(self) -> bool:
        """True when at least one target has published fixtures."""
        return bool(self.live)

    @property
    def all_failed(self) -> bool:
        """
        True when every target errored.

        Distinguishes "MLS Next is down" from "the schedule isn't out yet" —
        an all-empty probe is expected, an all-error probe is not.
        """
        return bool(self.results) and len(self.errors) == len(self.results)

    def summary(self) -> str:
        """One-line human summary suitable for a log or a Telegram message."""
        if self.all_failed:
            return f"{self.season}: all {len(self.results)} targets failed to probe"
        if not self.is_released:
            return f"{self.season}: no fixtures yet across {len(self.results)} targets"
        parts = [f"{r.label} ({r.match_count})" for r in self.live]
        return (
            f"{self.season}: fixtures live for {len(self.live)}/{len(self.results)} "
            f"targets — {', '.join(parts)}"
        )

    class Config:
        json_schema_extra = {
            "example": {
                "season": "2026-2027",
                "window_start": "2026-08-01",
                "window_end": "2026-12-31",
                "checked_at": "2026-08-07T12:00:00Z",
                "results": [
                    {
                        "age_group": "U15",
                        "division": "Northeast",
                        "state": "live",
                        "match_count": 128,
                        "error": None,
                    }
                ],
            }
        }
