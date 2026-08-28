"""
HTTP client for the Kitman "assist" feeds that now back the MLS Next schedule.

For the 2026-2027 season MLS Next replaced the modular11 iframe with a SPA that
reads two static JSON documents per competition season — no browser, no filters,
no pagination::

    https://mls-assist.theintelligenceplatform.com/data/schedule/<key>.json
    https://mls-assist.theintelligenceplatform.com/data/standings/<key>.json

The **schedule** feed holds every fixture of the season in one file (7-13 MB).
Its ``division`` field is useless for the Homegrown league — every event reports
``MLS Next`` — so it cannot answer "which matches belong to Florida U14?".

The **standings** feed can. It lists ``competition_brackets``: one per
conference x age group (``Florida``/U14, ``Northeast``/U16, ...), each naming
its teams with a ``squad_id`` that also appears on every schedule event. Joining
the two gives an exact division + age-group assignment with no name matching,
which is what :class:`AssistIndex` does.

That join replaces the hand-maintained ID tables in :mod:`.modular11`, which had
to be re-read off a live ``<select>`` element every season.

Usage::

    async with AssistClient() as client:
        matches = await client.get_matches(
            division="Florida", age_group="U14", start_date=..., end_date=...
        )

Feeds are fetched once per client instance and reused, so scraping many targets
in one run costs one download per feed.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from collections.abc import Iterable, Sequence
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from pydantic import BaseModel, ConfigDict, Field

from ..utils.logger import get_logger
from .models import Match
from .modular11 import current_season_year

logger = get_logger()

BASE_URL = "https://mls-assist.theintelligenceplatform.com"
SCHEDULE_URL = BASE_URL + "/data/schedule/{key}.json"
STANDINGS_URL = BASE_URL + "/data/standings/{key}.json"

# Competition-season key templates. ``{season}`` is the two-digit season label
# ("26-27"). Verified live on 2026-08-24; no prior-season keys exist on this
# platform — it went live with 2026-2027.
FEED_KEY_TEMPLATES: dict[str, str] = {
    "league": "mls-next-league-{season}",
    "flex": "mls-next-flex-{season}",
    "academy": "mls-next-2-academy-division-{season}",
}

# Which feeds make up each league as the CLI/orchestrator names them. Flex is a
# distinct competition season with its own conference brackets; the MLS Next
# site shows it alongside the league on the Homegrown page, but we keep it
# opt-in so an existing Homegrown scrape does not silently grow new fixtures.
LEAGUE_FEEDS: dict[str, tuple[str, ...]] = {
    "Homegrown": ("league",),
    "Academy": ("academy",),
    # Flex is its own competition season with its own conference brackets,
    # played by the SAME teams as Homegrown: 563 of its 567 squads also appear
    # in the league feed, and none appear in Academy. It stays a separate
    # league name rather than being folded into Homegrown so that an existing
    # Homegrown scrape does not silently grow new fixtures, and so MT can scope
    # its division lookup — four Flex bracket names collide with Homegrown ones
    # (Florida, Frontier, Northwest, Southeast).
    "Flex": ("flex",),
}

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; mls-match-scraper/assist-client)",
    "Accept": "application/json",
}


class AssistFeedError(Exception):
    """Raised when a feed cannot be fetched or parsed."""


class AssistSeasonNotPublished(AssistFeedError):
    """Raised when a competition-season key has no feed on the platform.

    The platform answers an unknown key with the SPA's HTML shell and a 200,
    so this is what "MLS Next has not published this season" looks like from
    the outside. It is a normal state to wait in, not a transport failure —
    the release detector distinguishes the two (SB-883).
    """


def season_suffix(year: int | None = None) -> str:
    """
    Return the two-digit season label used in feed keys.

    >>> season_suffix(2026)
    '26-27'
    """
    start = current_season_year() if year is None else year
    return f"{start % 100:02d}-{(start + 1) % 100:02d}"


def feed_key(feed: str, year: int | None = None) -> str:
    """Return the competition-season key for a feed name."""
    try:
        template = FEED_KEY_TEMPLATES[feed]
    except KeyError:
        raise AssistFeedError(
            f"Unknown feed {feed!r}. Known: {sorted(FEED_KEY_TEMPLATES)}"
        ) from None
    return template.format(season=season_suffix(year))


def league_feeds(league: str) -> tuple[str, ...]:
    """Return the feed names that make up a league."""
    try:
        return LEAGUE_FEEDS[league]
    except KeyError:
        raise AssistFeedError(
            f"Unknown league {league!r}. Known: {sorted(LEAGUE_FEEDS)}"
        ) from None


class AssistOrganisation(BaseModel):
    """A club as the assist platform names it."""

    model_config = ConfigDict(extra="ignore")

    id: int = Field(..., description="Assist organisation ID")
    name: str = Field(..., description="Club name as displayed on the site")
    logo_full_path: str | None = Field(None, description="Club crest URL")


class AssistNamedRef(BaseModel):
    """An ``{id, name}`` pair — competition, division or venue."""

    model_config = ConfigDict(extra="ignore")

    id: int | None = Field(None, description="Assist ID")
    name: str | None = Field(None, description="Display name")


class AssistEvent(BaseModel):
    """One fixture from a schedule feed."""

    model_config = ConfigDict(extra="ignore")

    id: int = Field(..., description="Assist internal event ID")
    game_key: str = Field(..., description="Public match ID shown on the site")
    start_time: datetime = Field(..., description="Kick-off in UTC")
    local_timezone: str | None = Field(
        None, description="IANA zone of the venue, e.g. America/New_York"
    )
    home_squad_id: int | None = Field(None, description="Home squad ID")
    away_squad_id: int | None = Field(None, description="Away squad ID")
    home_squad_name: str | None = Field(
        None, description="Age-group label, e.g. 'U14' or 'U14 AD'"
    )
    away_squad_name: str | None = Field(None, description="Away age-group label")
    competition: AssistNamedRef | None = Field(None, description="Competition")
    completed: bool = Field(False, description="Whether the match has been played")
    home_organisation: AssistOrganisation | None = Field(None)
    away_organisation: AssistOrganisation | None = Field(None)
    home_score: int | None = Field(None, description="Home goals, null if unplayed")
    away_score: int | None = Field(None, description="Away goals, null if unplayed")
    home_penalty_shootout_score: int | None = Field(None)
    away_penalty_shootout_score: int | None = Field(None)
    event_location: AssistNamedRef | None = Field(None, description="Venue/pitch")
    division: AssistNamedRef | None = Field(
        None, description="Platform division — 'MLS Next' for every league event"
    )
    round_number: int | None = Field(None)

    @property
    def local_datetime(self) -> datetime:
        """
        Kick-off as a naive datetime in the venue's local time.

        The Playwright scraper read the site's rendered local time, so matches
        keep the same wall-clock value they have always had downstream.
        """
        aware = self.start_time
        if aware.tzinfo is None:
            aware = aware.replace(tzinfo=timezone.utc)
        if self.local_timezone:
            try:
                aware = aware.astimezone(ZoneInfo(self.local_timezone))
            except (ZoneInfoNotFoundError, ValueError):
                logger.warning(
                    "Unknown venue timezone; falling back to UTC",
                    extra={"timezone": self.local_timezone, "game_key": self.game_key},
                )
        return aware.replace(tzinfo=None)

    def to_match(self) -> Match:
        """Convert to the scraper's :class:`Match` model."""
        home = self.home_organisation.name if self.home_organisation else None
        away = self.away_organisation.name if self.away_organisation else None
        if not home or not away:
            raise AssistFeedError(
                f"Event {self.game_key} is missing a club name "
                f"(home={home!r}, away={away!r})"
            )
        return Match(
            match_id=self.game_key,
            match_datetime=self.local_datetime,
            location=self.event_location.name if self.event_location else None,
            competition=self.competition.name if self.competition else None,
            home_team=home,
            away_team=away,
            home_score=self.home_score,
            away_score=self.away_score,
        )


class AssistSchedule(BaseModel):
    """A parsed schedule feed."""

    model_config = ConfigDict(extra="ignore")

    events: list[AssistEvent] = Field(default_factory=list)
    synced_at: datetime | None = Field(
        None, description="When the platform last refreshed this feed"
    )


class AssistIndex(BaseModel):
    """
    Conference x age-group membership, built from a standings feed.

    A bracket is keyed by ``(division, age_group)`` and holds the squad IDs of
    its teams. Membership is asked per bracket rather than resolved per squad,
    because a club can appear in two brackets (FC Dallas U17 is in both
    ``Frontier`` and ``Southeast (Pro Player Pathway)`` for 2026-2027).
    """

    model_config = ConfigDict(extra="ignore")

    key: str = Field(..., description="Competition-season key this index covers")
    brackets: dict[tuple[str, str], frozenset[int]] = Field(
        default_factory=dict,
        description="(division, age_group) -> squad IDs",
    )

    @classmethod
    def from_standings(cls, key: str, payload: dict) -> AssistIndex:
        """Build an index from a raw standings document."""
        season = payload.get("competition_season") or {}
        brackets: dict[tuple[str, str], frozenset[int]] = {}
        for bracket in season.get("competition_brackets") or []:
            name = bracket.get("name")
            age_group = (bracket.get("age_group") or {}).get("name")
            if not name or not age_group:
                continue
            squads = {
                (row.get("team") or {}).get("squad_id")
                for row in bracket.get("standings") or []
            }
            brackets[(name, age_group)] = frozenset(s for s in squads if s is not None)
        if not brackets:
            raise AssistFeedError(f"Standings feed {key} declared no brackets")
        return cls(key=key, brackets=brackets)

    def squads(self, division: str, age_group: str) -> frozenset[int]:
        """Squad IDs in one bracket, or an empty set if it does not exist."""
        return self.brackets.get((division, age_group), frozenset())

    def divisions(self) -> list[str]:
        """Every division/conference name in this competition season."""
        return sorted({division for division, _ in self.brackets})

    def age_groups(self, division: str | None = None) -> list[str]:
        """Age groups present, optionally restricted to one division."""
        return sorted(
            {age for div, age in self.brackets if division is None or div == division}
        )


class FeedCache:
    """Bodies kept between runs so an unchanged feed costs a 304, not 7 MB.

    The schedule feed is ~7 MB and mostly identical from one run to the next —
    it only moves when the platform re-syncs. The response carries a strong
    ETag and Last-Modified, so a conditional request answers "nothing changed"
    in a few hundred bytes (SB-884).

    Every failure here is survivable by design: a miss, an unreadable entry or
    an unwritable directory all mean "fetch it in full", never an error. A
    cache that breaks a scrape would be worse than no cache.
    """

    ENV_VAR = "ASSIST_FEED_CACHE_DIR"

    def __init__(self, directory: str | Path | None = None) -> None:
        configured = directory if directory is not None else os.getenv(self.ENV_VAR)
        self.directory = Path(configured) if configured else None

    @property
    def enabled(self) -> bool:
        return self.directory is not None

    def _path(self, url: str) -> Path | None:
        if self.directory is None:
            return None
        # The key is the URL; the filename is a digest of it so a competition
        # key with a slash or a query string cannot escape the directory.
        digest = hashlib.sha256(url.encode()).hexdigest()[:32]
        return self.directory / f"{digest}.json"

    def load(self, url: str) -> tuple[dict | None, dict[str, str]]:
        """The cached payload and the headers that would revalidate it."""
        path = self._path(url)
        if path is None:
            return None, {}
        try:
            entry = json.loads(path.read_text())
            payload = entry["payload"]
        except (OSError, ValueError, KeyError, TypeError):
            # Absent, truncated, or written by an older shape — refetch.
            return None, {}

        headers: dict[str, str] = {}
        if etag := entry.get("etag"):
            headers["If-None-Match"] = etag
        if last_modified := entry.get("last_modified"):
            headers["If-Modified-Since"] = last_modified
        if not headers:
            # Nothing to revalidate with; a stored body we cannot check is not
            # worth trusting.
            return None, {}
        return payload, headers

    def store(self, url: str, payload: dict, headers: object) -> None:
        """Keep the body against its validators, if the response carries any."""
        path = self._path(url)
        if path is None:
            return
        get = getattr(headers, "get", None)
        etag = get("etag") if get else None
        last_modified = get("last-modified") if get else None
        if not etag and not last_modified:
            return
        try:
            self.directory.mkdir(parents=True, exist_ok=True)  # type: ignore[union-attr]
            # Write-then-rename: a run killed mid-write must not leave a
            # half-written body that the next run reads as valid.
            tmp = path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(
                    {
                        "url": url,
                        "etag": etag,
                        "last_modified": last_modified,
                        "payload": payload,
                    }
                )
            )
            tmp.replace(path)
        except OSError as exc:
            logger.debug(
                "Could not cache assist feed",
                extra={"url": url, "error": str(exc)},
            )


class AssistClient:
    """
    Fetches and filters the assist schedule feeds.

    One instance caches each feed it downloads, so scraping several targets in
    a run costs a single download per competition season. Instances are not
    thread-safe; concurrent coroutines on one instance are, and share the fetch.
    """

    REQUEST_TIMEOUT = 60.0
    MAX_RETRIES = 3
    RETRY_DELAY_BASE = 1.0
    RETRY_BACKOFF_MULTIPLIER = 2.0

    def __init__(
        self,
        *,
        season_year: int | None = None,
        timeout: float | None = None,
        client: httpx.AsyncClient | None = None,
        cache: FeedCache | None = None,
    ) -> None:
        self.season_year = (
            season_year if season_year is not None else current_season_year()
        )
        self.timeout = timeout if timeout is not None else self.REQUEST_TIMEOUT
        self.cache = cache if cache is not None else FeedCache()
        self._client = client
        self._owns_client = client is None
        self._schedules: dict[str, AssistSchedule] = {}
        self._indexes: dict[str, AssistIndex] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def __aenter__(self) -> AssistClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying HTTP client if this instance created it."""
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout, headers=DEFAULT_HEADERS, follow_redirects=True
            )
        return self._client

    def _lock(self, name: str) -> asyncio.Lock:
        lock = self._locks.get(name)
        if lock is None:
            lock = self._locks[name] = asyncio.Lock()
        return lock

    async def _fetch_json(self, url: str) -> dict:
        """GET a feed with backoff, failing loudly on a non-JSON response.

        Revalidates a cached body rather than re-downloading it: the schedule
        feed is ~7 MB and changes only when the platform re-syncs (SB-884).
        """
        cached, conditional = self.cache.load(url)
        last_exc: Exception | None = None
        for attempt in range(self.MAX_RETRIES):
            try:
                response = await self._http().get(url, headers=conditional or None)
                if response.status_code == 304:
                    if cached is not None:
                        logger.info(
                            "Assist feed unchanged since last run",
                            extra={"url": url},
                        )
                        return cached
                    # Told "unchanged" with nothing to show for it — the body
                    # went missing between load and now. Ask again without the
                    # validators rather than decoding an empty response, which
                    # would surface as "season not published".
                    logger.warning(
                        "Assist feed returned 304 with no cached body; refetching",
                        extra={"url": url},
                    )
                    conditional = {}
                    continue
                response.raise_for_status()
                # An unknown key returns the SPA's HTML shell with a 200, so a
                # decode failure here means "no such competition season", not a
                # transport problem — do not retry it.
                try:
                    payload = response.json()
                except ValueError as exc:
                    raise AssistSeasonNotPublished(
                        f"{url} did not return JSON ({len(response.content)} bytes) — "
                        "the competition season is not published, or the key is wrong"
                    ) from exc
                if not isinstance(payload, dict):
                    raise AssistFeedError(f"{url} returned {type(payload).__name__}")
                self.cache.store(url, payload, response.headers)
                return payload
            except (httpx.HTTPError, httpx.RequestError) as exc:
                last_exc = exc
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(
                        self.RETRY_DELAY_BASE * (self.RETRY_BACKOFF_MULTIPLIER**attempt)
                    )
        raise AssistFeedError(
            f"GET {url} failed after {self.MAX_RETRIES} attempts: {last_exc}"
        ) from last_exc

    async def schedule(self, feed: str) -> AssistSchedule:
        """Fetch (and cache) the schedule feed for one competition season."""
        key = feed_key(feed, self.season_year)
        async with self._lock(f"schedule:{key}"):
            cached = self._schedules.get(key)
            if cached is not None:
                return cached
            payload = await self._fetch_json(SCHEDULE_URL.format(key=key))
            schedule = AssistSchedule.model_validate(payload)
            self._schedules[key] = schedule
            logger.info(
                "Fetched assist schedule feed",
                extra={
                    "feed": feed,
                    "key": key,
                    "events": len(schedule.events),
                    "synced_at": (
                        schedule.synced_at.isoformat() if schedule.synced_at else None
                    ),
                },
            )
            return schedule

    async def index(self, feed: str) -> AssistIndex:
        """Fetch (and cache) the conference index for one competition season."""
        key = feed_key(feed, self.season_year)
        async with self._lock(f"index:{key}"):
            cached = self._indexes.get(key)
            if cached is not None:
                return cached
            payload = await self._fetch_json(STANDINGS_URL.format(key=key))
            index = AssistIndex.from_standings(key, payload)
            self._indexes[key] = index
            logger.info(
                "Built assist conference index",
                extra={
                    "feed": feed,
                    "key": key,
                    "brackets": len(index.brackets),
                    "divisions": len(index.divisions()),
                },
            )
            return index

    async def get_events(
        self,
        *,
        division: str,
        age_group: str,
        start_date: date | None = None,
        end_date: date | None = None,
        league: str = "Homegrown",
        feeds: Sequence[str] | None = None,
    ) -> list[AssistEvent]:
        """
        Return the fixtures for one division/age group, newest last.

        ``start_date``/``end_date`` are inclusive and compared against the
        venue's local date, matching how the site displays a fixture. Omitting
        both returns the whole season.
        """
        names = tuple(feeds) if feeds is not None else league_feeds(league)
        collected: dict[int, AssistEvent] = {}
        for feed in names:
            index = await self.index(feed)
            squads = index.squads(division, age_group)
            if not squads:
                logger.warning(
                    "No bracket for target in assist feed",
                    extra={
                        "feed": feed,
                        "division": division,
                        "age_group": age_group,
                        "known_divisions": index.divisions(),
                    },
                )
                continue
            schedule = await self.schedule(feed)
            for event in schedule.events:
                if event.home_squad_id in squads or event.away_squad_id in squads:
                    collected[event.id] = event

        events = [
            event
            for event in collected.values()
            if _within(event.local_datetime.date(), start_date, end_date)
        ]
        events.sort(key=lambda e: (e.start_time, e.game_key))

        logger.info(
            "Selected assist fixtures",
            extra={
                "division": division,
                "age_group": age_group,
                "league": league,
                "feeds": list(names),
                "matched": len(collected),
                "in_window": len(events),
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None,
            },
        )
        return events

    async def get_matches(
        self,
        *,
        division: str,
        age_group: str,
        start_date: date | None = None,
        end_date: date | None = None,
        league: str = "Homegrown",
        feeds: Sequence[str] | None = None,
    ) -> list[Match]:
        """Return :class:`Match` models for one division/age group."""
        events = await self.get_events(
            division=division,
            age_group=age_group,
            start_date=start_date,
            end_date=end_date,
            league=league,
            feeds=feeds,
        )
        matches: list[Match] = []
        skipped = 0
        for event in events:
            try:
                matches.append(event.to_match())
            except (AssistFeedError, ValueError) as exc:
                # A single malformed fixture must not sink a whole target.
                skipped += 1
                logger.warning(
                    "Skipping unusable assist fixture",
                    extra={"game_key": event.game_key, "error": str(exc)},
                )
        if skipped:
            logger.warning(
                "Assist fixtures skipped",
                extra={"skipped": skipped, "kept": len(matches)},
            )
        return matches

    async def divisions(self, feed: str) -> list[str]:
        """Division/conference names published for one feed."""
        return (await self.index(feed)).divisions()

    async def synced_at(self, feed: str) -> datetime | None:
        """When the platform last refreshed a schedule feed."""
        return (await self.schedule(feed)).synced_at


def _within(value: date, start: date | None, end: date | None) -> bool:
    """Inclusive date-window test that treats ``None`` as unbounded."""
    if start is not None and value < start:
        return False
    if end is not None and value > end:
        return False
    return True


async def fetch_matches(
    division: str,
    age_group: str,
    start_date: date | None = None,
    end_date: date | None = None,
    *,
    league: str = "Homegrown",
    season_year: int | None = None,
    feeds: Iterable[str] | None = None,
) -> list[Match]:
    """
    One-shot convenience wrapper around :class:`AssistClient`.

    Prefer the client directly when scraping several targets — it reuses the
    downloaded feeds instead of re-fetching them per call.
    """
    async with AssistClient(season_year=season_year) as client:
        return await client.get_matches(
            division=division,
            age_group=age_group,
            start_date=start_date,
            end_date=end_date,
            league=league,
            feeds=list(feeds) if feeds is not None else None,
        )
