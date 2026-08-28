"""Check that the assist feeds actually deliver scores.

Nothing has ever proved they do. When the 2026-2027 season was loaded, all
7,765 events carried ``completed: false`` and four null score fields, because
not one fixture had been played yet — the earliest was 2026-09-05. The fields
exist, so the feed is *designed* to carry results, but the platform hosts no
prior season to check the shape of a played event against.

The failure this guards against is silent. If the scores land somewhere the
parser does not read, or ``completed`` never flips, a scrape returns every
fixture, updates nothing and reports success — indistinguishable from a quiet
week. Counting fixtures cannot tell the two apart; only counting *scores* can.

The check is therefore: of the fixtures whose kick-off has passed, how many
came back scored? None, over a window that contains a played matchday, is a
break rather than a quiet week.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from pydantic import BaseModel, ConfigDict, Field

from ..utils.logger import get_logger
from .assist_client import AssistClient, AssistEvent, AssistSeasonNotPublished
from .modular11 import current_season_year, season_label

logger = get_logger()


class ScoreCheck(BaseModel):
    """What one competition feed reported for a window that is already played."""

    model_config = ConfigDict(extra="forbid")

    feed: str = Field(..., description="Competition feed name, e.g. 'league'")
    season: str = Field(..., description="Season label, e.g. '2026-2027'")
    window_start: date
    window_end: date
    kicked_off: int = Field(0, ge=0, description="Fixtures whose kick-off has passed")
    completed: int = Field(0, ge=0, description="Of those, flagged completed")
    scored: int = Field(0, ge=0, description="Of those, carrying a score")
    published: bool = Field(True, description="Whether the season's feed exists")

    @property
    def has_scores(self) -> bool:
        return self.scored > 0

    @property
    def nothing_to_judge(self) -> bool:
        """No fixture in the window has kicked off, so silence proves nothing."""
        return self.kicked_off == 0

    @property
    def verdict(self) -> str:
        if not self.published:
            return "season not published"
        if self.nothing_to_judge:
            return "no fixtures played in window"
        if self.has_scores:
            return f"{self.scored}/{self.kicked_off} played fixtures scored"
        return f"BROKEN: {self.kicked_off} played fixtures, none scored"

    @property
    def completed_without_scores(self) -> int:
        """Flagged played but carrying no score — a half-populated result."""
        return max(self.completed - self.scored, 0)


def _kicked_off(event: AssistEvent, now: datetime) -> bool:
    start = event.start_time
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    return start <= now


def _in_window(event: AssistEvent, start: date, end: date) -> bool:
    day = event.local_datetime.date()
    return start <= day <= end


async def check_feed(
    feed: str = "league",
    *,
    window_start: date | None = None,
    window_end: date | None = None,
    season_year: int | None = None,
    now: datetime | None = None,
    client: AssistClient | None = None,
) -> ScoreCheck:
    """Count scored fixtures in a window that has already been played.

    Defaults to the three days ending yesterday, which covers a weekend when
    run on a Monday.
    """
    now = now or datetime.now(tz=timezone.utc)
    end = window_end or (now.date() - timedelta(days=1))
    start = window_start or (end - timedelta(days=2))
    year = season_year if season_year is not None else current_season_year()

    owned = client is None
    client = client or AssistClient(season_year=year)
    try:
        try:
            schedule = await client.schedule(feed)
        except AssistSeasonNotPublished:
            return ScoreCheck(
                feed=feed,
                season=season_label(year),
                window_start=start,
                window_end=end,
                published=False,
            )

        played = [
            e
            for e in schedule.events
            if _in_window(e, start, end) and _kicked_off(e, now)
        ]
        check = ScoreCheck(
            feed=feed,
            season=season_label(year),
            window_start=start,
            window_end=end,
            kicked_off=len(played),
            completed=sum(1 for e in played if e.completed),
            scored=sum(
                1
                for e in played
                if e.home_score is not None and e.away_score is not None
            ),
        )
    finally:
        if owned:
            await client.aclose()

    logger.info(
        "Score canary checked a feed",
        extra={
            "feed": feed,
            "season": check.season,
            "window": f"{start} to {end}",
            "kicked_off": check.kicked_off,
            "completed": check.completed,
            "scored": check.scored,
            "verdict": check.verdict,
        },
    )
    return check
