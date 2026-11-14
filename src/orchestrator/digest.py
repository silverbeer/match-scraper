"""Daily scores digest for Telegram (SB-1679).

The run report used to go out after every run — about fifty a week — and almost
every one said "nothing to do". The digest replaces that status traffic with
one message a day answering the two questions that matter: how many of today's
matches came back scored, and how many matches have been played but still
have no score.

The counts come from missing-table, not from what one run happened to scrape.
missing-table is where the scores are shown, so "still needs a score" means
"is missing on the site", whichever run did or did not fetch it.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from pydantic import BaseModel, Field
from telegram_notify import escape

logger = structlog.get_logger()

# Mirrors missing-table's match_dao.SCORE_GRACE: a match is not "missing" a
# score until three hours after kick-off, the same rule the planner's
# needs_score count uses, so the digest and the scraper agree on what is late.
SCORE_GRACE = timedelta(hours=3)

# How far back "still needs a score" looks. A week covers last weekend from any
# day; anything older is no longer a scraping problem worth a daily nudge.
LOOKBACK_DAYS = 7

# Only matches the scraper owns. Hand-loaded tournament matches have no feed to
# score them, so counting them would report a gap nothing can close.
SCRAPED_SOURCES = frozenset({"match-scraper", "match-scraper-agent"})

_SCORED = frozenset({"completed", "forfeit"})
_AWAITING = frozenset({"scheduled", "tbd", "live"})

_DISPLAY_TZ = ZoneInfo("America/New_York")
_FETCH_TIMEOUT_SECONDS = 60.0


class DigestSummary(BaseModel):
    """Counts for one day's digest."""

    day: date = Field(..., description="The local (ET) day the digest covers")
    played_today: int = Field(0, ge=0, description="Today's matches past kick-off")
    scored_today: int = Field(0, ge=0, description="Today's matches with a score")
    unscored_today: int = Field(
        0, ge=0, description="Today's matches played but with no score"
    )
    unscored_earlier: int = Field(
        0, ge=0, description="Earlier matches in the lookback still with no score"
    )
    oldest_unscored: date | None = Field(
        None, description="Date of the oldest match still waiting for a score"
    )
    unscored_by_league: dict[str, int] = Field(
        default_factory=dict, description="Unscored matches per league"
    )

    @property
    def unscored_total(self) -> int:
        return self.unscored_today + self.unscored_earlier


def fetch_recent_matches(
    api_url: str, api_key: str, start: date, end: date
) -> list[dict[str, Any]]:
    """Read missing-table's matches dated start..end (inclusive).

    Raises on failure. Unlike the run report's enrichments, the digest has
    nothing to say without this data, and a digest that silently reported zero
    would read as "every score is in".
    """
    import httpx

    resp = httpx.get(
        f"{api_url}/api/matches",
        params={"start_date": start.isoformat(), "end_date": end.isoformat()},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=_FETCH_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json()


def _has_been_played(match: dict[str, Any], now: datetime, today: date) -> bool:
    """True once the grace period after kick-off has passed.

    With no kick-off time, the match counts as played once its day is over.
    """
    kickoff = match.get("scheduled_kickoff")
    if kickoff:
        try:
            return datetime.fromisoformat(kickoff) + SCORE_GRACE <= now
        except ValueError:
            pass
    try:
        return date.fromisoformat(match.get("match_date", "")) < today
    except ValueError:
        return False


def summarize(matches: list[dict[str, Any]], now: datetime) -> DigestSummary:
    """Count today's scored and unscored matches, plus the backlog.

    Args:
        matches: Rows from missing-table's /api/matches.
        now: Timezone-aware current time.
    """
    today = now.astimezone(_DISPLAY_TZ).date()
    earliest = today - timedelta(days=LOOKBACK_DAYS)
    today_str = today.isoformat()

    played_today = scored_today = unscored_today = unscored_earlier = 0
    oldest: date | None = None
    by_league: Counter[str] = Counter()

    for m in matches:
        if m.get("source") not in SCRAPED_SOURCES:
            continue
        try:
            match_day = date.fromisoformat(m.get("match_date", ""))
        except ValueError:
            continue
        if not earliest <= match_day <= today:
            continue

        status = m.get("match_status")
        is_today = m.get("match_date") == today_str

        if status in _SCORED:
            if is_today:
                played_today += 1
                scored_today += 1
            continue
        if status not in _AWAITING or not _has_been_played(m, now, today):
            continue

        by_league[m.get("league_name") or "Unknown"] += 1
        if is_today:
            played_today += 1
            unscored_today += 1
        else:
            unscored_earlier += 1
            if oldest is None or match_day < oldest:
                oldest = match_day

    return DigestSummary(
        day=today,
        played_today=played_today,
        scored_today=scored_today,
        unscored_today=unscored_today,
        unscored_earlier=unscored_earlier,
        oldest_unscored=oldest,
        unscored_by_league=dict(sorted(by_league.items())),
    )


def build_digest_report(summary: DigestSummary) -> str:
    """Build the MarkdownV2 digest message."""
    day_label = escape(summary.day.strftime("%a %-d %b"))
    lines = [f"*Scores digest* · _{day_label}_", ""]

    if summary.played_today:
        lines.append(
            escape(f"✅ Scored today: {summary.scored_today} of {summary.played_today}")
        )
    else:
        lines.append(escape("No matches played today."))

    if summary.unscored_total:
        lines.append(escape(f"⏳ Played, still need a score: {summary.unscored_total}"))
        if summary.unscored_today:
            lines.append(escape(f"  • today: {summary.unscored_today}"))
        if summary.unscored_earlier:
            since = (
                f" (oldest {summary.oldest_unscored.strftime('%a %-d %b')})"
                if summary.oldest_unscored
                else ""
            )
            lines.append(
                escape(f"  • earlier this week: {summary.unscored_earlier}{since}")
            )
        breakdown = " · ".join(
            f"{league} {n}" for league, n in summary.unscored_by_league.items()
        )
        lines.append(escape(f"  {breakdown}"))
    else:
        lines.append(escape("✓ Every played match has a score."))

    return "\n".join(lines)
