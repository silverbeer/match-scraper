"""
Detect whether MLS Next has published its schedule for a season.

Reads the assist feeds the MLS Next schedule page itself reads, so the probe
sees exactly what the site shows. One download per competition season covers
every age group and division, because the feed holds the whole season.

Before publication the platform has no feed for the season's key at all and
answers with the SPA's HTML shell; afterwards the JSON carries an ``events``
array. That difference is the whole signal.

The modular11 probe this replaced kept answering "not published" forever once
MLS Next moved (SB-883): it is retained behind ``source="modular11"`` because
it is still the only reader for 2025-2026 and earlier, which the assist
platform does not host.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import date, datetime, timezone

import httpx
from bs4 import BeautifulSoup

from ..models.schedule_release import DivisionRelease, ReleaseProbe, ReleaseState
from ..utils.logger import get_logger
from .assist_client import AssistClient, AssistSeasonNotPublished
from .modular11 import (
    AGE_GROUP_IDS,
    DIVISION_GROUP_IDS,
    PRIORITY_AGE_GROUPS,
    PRIORITY_DIVISIONS,
    TOURNAMENT_ID,
    current_season_year,
    fall_segment_window,
    season_label,
    season_window,
)

logger = get_logger()

# The endpoint returns this fragment when the season has no fixtures yet.
EMPTY_MARKER = "no data available"

# Each fixture row carries this attribute; counting them counts matches.
MATCH_ROW_SELECTOR = "[js-match-game]"


class ReleaseDetectorError(Exception):
    """Raised when a probe cannot be completed at all."""


class ScheduleReleaseDetector:
    """
    Polls modular11 for published fixtures across age groups and divisions.

    Usage::

        detector = ScheduleReleaseDetector()
        probe = await detector.probe()
        if probe.is_released:
            ...
    """

    ENDPOINT_URL = "https://www.modular11.com/public_schedule/league/get_matches"

    REQUEST_TIMEOUT = 30.0
    MAX_RETRIES = 3
    RETRY_DELAY_BASE = 1.0
    RETRY_BACKOFF_MULTIPLIER = 2.0

    # Keep concurrent requests modest — this runs unattended against someone
    # else's server, and a release-day poll is not latency-sensitive.
    MAX_CONCURRENCY = 4

    #: Where the fixtures are read from. "assist" is where MLS Next publishes
    #: now; "modular11" reaches 2025-2026 and earlier, which assist does not host.
    DEFAULT_SOURCE = "assist"

    def __init__(
        self,
        age_groups: Iterable[str] | None = None,
        divisions: Iterable[str] | None = None,
        season_year: int | None = None,
        fall_only: bool = True,
        source: str | None = None,
    ) -> None:
        self.age_groups = list(age_groups or PRIORITY_AGE_GROUPS)
        self.divisions = list(divisions or PRIORITY_DIVISIONS)
        self.source = (source or self.DEFAULT_SOURCE).strip().lower()
        if self.source not in ("assist", "modular11"):
            raise ReleaseDetectorError(
                f"Unknown source {self.source!r}. Known: assist, modular11"
            )
        self.season_year = (
            season_year if season_year is not None else current_season_year()
        )
        self.fall_only = fall_only

        unknown_ages = [a for a in self.age_groups if a not in AGE_GROUP_IDS]
        if unknown_ages:
            raise ReleaseDetectorError(
                f"Unknown age groups: {unknown_ages}. Known: {sorted(AGE_GROUP_IDS)}"
            )

        unknown_divs = [d for d in self.divisions if d not in DIVISION_GROUP_IDS]
        if unknown_divs:
            raise ReleaseDetectorError(
                f"Unknown divisions: {unknown_divs}. "
                f"Known: {sorted(DIVISION_GROUP_IDS)}"
            )

    @property
    def window(self) -> tuple[date, date]:
        """The date range searched for fixtures."""
        if self.fall_only:
            return fall_segment_window(self.season_year)
        return season_window(self.season_year)

    async def probe(self) -> ReleaseProbe:
        """Check every age group/division pair and return the combined result."""
        start, end = self.window
        targets = [(a, d) for d in self.divisions for a in self.age_groups]

        logger.info(
            "Starting schedule release probe",
            extra={
                "season": season_label(self.season_year),
                "source": self.source,
                "targets": len(targets),
                "window_start": start.isoformat(),
                "window_end": end.isoformat(),
            },
        )

        if self.source == "assist":
            results = await self._probe_assist(targets, start, end)
        else:
            results = await self._probe_modular11(targets, start, end)

        probe = ReleaseProbe(
            season=season_label(self.season_year),
            window_start=start,
            window_end=end,
            checked_at=datetime.now(tz=timezone.utc),
            results=list(results),
        )

        logger.info(
            "Schedule release probe completed",
            extra={
                "season": probe.season,
                "source": self.source,
                "released": probe.is_released,
                "live_targets": len(probe.live),
                "error_targets": len(probe.errors),
                "total_matches": probe.total_matches,
            },
        )

        return probe

    async def _probe_assist(
        self,
        targets: list[tuple[str, str]],
        start: date,
        end: date,
    ) -> list[DivisionRelease]:
        """Probe every target from the assist feeds, at one download per feed.

        The client caches each feed it fetches, so the cost here is the feed,
        not the target count — the opposite of the modular11 path.
        """
        async with AssistClient(season_year=self.season_year) as client:
            results: list[DivisionRelease] = []
            for age_group, division in targets:
                try:
                    events = await client.get_events(
                        division=division,
                        age_group=age_group,
                        start_date=start,
                        end_date=end,
                    )
                except AssistSeasonNotPublished:
                    # No feed for this season yet. That is the state we are
                    # waiting in, not a failure — reporting it as ERROR would
                    # page someone every 30 minutes all summer.
                    results.append(
                        DivisionRelease(
                            age_group=age_group,
                            division=division,
                            state=ReleaseState.EMPTY,
                            match_count=0,
                        )
                    )
                    continue
                except Exception as exc:  # noqa: BLE001 — one target must not sink the probe
                    logger.warning(
                        "Release probe target failed",
                        extra={
                            "age_group": age_group,
                            "division": division,
                            "error": str(exc),
                            "error_type": type(exc).__name__,
                        },
                    )
                    results.append(
                        DivisionRelease(
                            age_group=age_group,
                            division=division,
                            state=ReleaseState.ERROR,
                            error=f"{type(exc).__name__}: {exc}",
                        )
                    )
                    continue

                results.append(
                    DivisionRelease(
                        age_group=age_group,
                        division=division,
                        state=ReleaseState.LIVE if events else ReleaseState.EMPTY,
                        match_count=len(events),
                    )
                )
            return results

    async def _probe_modular11(
        self,
        targets: list[tuple[str, str]],
        start: date,
        end: date,
    ) -> list[DivisionRelease]:
        """Probe every target from modular11, one HTTP request each."""
        semaphore = asyncio.Semaphore(self.MAX_CONCURRENCY)

        async with httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT) as client:

            async def run(age_group: str, division: str) -> DivisionRelease:
                async with semaphore:
                    return await self._check_target(
                        client, age_group, division, start, end
                    )

            return list(await asyncio.gather(*(run(age, div) for age, div in targets)))

    async def _check_target(
        self,
        client: httpx.AsyncClient,
        age_group: str,
        division: str,
        start: date,
        end: date,
    ) -> DivisionRelease:
        """Probe a single age group/division pair, converting failure to a result."""
        try:
            html = await self._fetch(client, age_group, division, start, end)
        except Exception as exc:  # noqa: BLE001 — a failed target must not sink the probe
            logger.warning(
                "Release probe target failed",
                extra={
                    "age_group": age_group,
                    "division": division,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            )
            return DivisionRelease(
                age_group=age_group,
                division=division,
                state=ReleaseState.ERROR,
                error=f"{type(exc).__name__}: {exc}",
            )

        count = count_matches(html)
        return DivisionRelease(
            age_group=age_group,
            division=division,
            state=ReleaseState.LIVE if count else ReleaseState.EMPTY,
            match_count=count,
        )

    async def _fetch(
        self,
        client: httpx.AsyncClient,
        age_group: str,
        division: str,
        start: date,
        end: date,
    ) -> str:
        """GET the fixtures fragment for one target, with backoff."""
        params = [
            ("open_page", "0"),
            ("academy", "0"),
            ("tournament", TOURNAMENT_ID),
            ("gender", "0"),
            ("age[]", AGE_GROUP_IDS[age_group]),
            ("brackets", ""),
            ("groups[]", DIVISION_GROUP_IDS[division]),
            ("group", ""),
            ("match_number", "0"),
            # The endpoint rejects anything outside all/scheduled/pending.
            ("status", "all"),
            ("match_type", "2"),
            ("schedule", "0"),
            ("teamPlayer", "0"),
            ("location", "0"),
            ("as_referee", "0"),
            ("report_status", "0"),
            ("start_date", f"{start.isoformat()} 00:00:00"),
            ("end_date", f"{end.isoformat()} 23:59:59"),
        ]
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; mls-match-scraper/release-detector)",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "text/html,*/*",
        }

        last_exc: Exception | None = None
        for attempt in range(self.MAX_RETRIES):
            try:
                resp = await client.get(
                    self.ENDPOINT_URL, params=params, headers=headers
                )
                resp.raise_for_status()
                return resp.text
            except (httpx.HTTPError, httpx.RequestError) as exc:
                last_exc = exc
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(
                        self.RETRY_DELAY_BASE * (self.RETRY_BACKOFF_MULTIPLIER**attempt)
                    )

        raise ReleaseDetectorError(
            f"get_matches failed after {self.MAX_RETRIES} attempts: {last_exc}"
        ) from last_exc


def count_matches(html: str) -> int:
    """
    Count fixture rows in a ``get_matches`` HTML fragment.

    Returns 0 for the pre-release "No data available." response, so callers can
    treat "empty" and "not yet published" as the same thing.

    The endpoint paginates at 25 rows, so a full division saturates this count.
    It answers "are there fixtures?", not "how many fixtures are there?".
    """
    if not html or not html.strip():
        return 0
    if EMPTY_MARKER in html.lower():
        return 0
    return len(BeautifulSoup(html, "html.parser").select(MATCH_ROW_SELECTOR))
