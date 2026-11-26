"""Official results that never reached missing-table (SB-1786).

Every other part of the orchestrator decides what to scrape from what MT
already holds: a target is scraped when MT says it has nothing yet
(FULL_SYNC), a played match without a score, or a kick-off to fill in. That
is blind to one shape of failure. A fixture the feed published *after* its
bracket's one FULL_SYNC never got an MT row, and a row that does not exist
cannot make its target due — so it was never scraped, and nothing said so.
121 completed Flex results from 2026-09-06 to 2026-10-04 went missing that
way (SB-1779).

This module asks the question the other way round: start from the official
feed, and list every completed result whose ``game_key`` is not an MT
``match_id``. :func:`diff` is pure; the two readers around it do the I/O.

Nothing here deletes. An MT row the feed does not know is reported, never
removed — the feed drops fixtures for reasons of its own, and a scraped
result is not ours to throw away on its say-so.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlsplit

import structlog
from pydantic import BaseModel, Field

from src.scraper.models import Match

if TYPE_CHECKING:
    import httpx

    from src.scraper.assist_client import AssistClient, AssistEvent, AssistIndex

logger = structlog.get_logger()

# League, as the orchestrator names it -> (assist feed, MT match_type).
#
# Both read the one league standings document; the feed name picks the
# stage. Pathway brackets sit in the League stage and stay League.
LEAGUES: dict[str, tuple[str, str]] = {
    "Homegrown": ("league", "League"),
    "Flex": ("flex", "Flex"),
}

# PostgREST caps a response at max_rows, 1000 on missing-table. A page of
# exactly that many has almost certainly been cut short, and a short read
# here reads as "missing", which would resubmit — and alert on — matches MT
# already has. So it is an error, never a page.
MT_PAGE_CAP = 1000

# /api/matches takes no limit or offset, so a page cannot be continued — only
# made smaller. A page this full is split in half and both halves re-read, so
# the guard does not rest on the cap being exactly 1000: a lower cap shows up
# as pages that keep splitting, not as rows silently lost. A single day this
# full is kept (it cannot be split) and logged.
MT_SPLIT_AT = 500

# The production pair. A backfill publishes what it found missing in one MT
# to a queue whose workers write to some MT; if those are not the same MT,
# the diff is against the wrong database and every "gap" is a guess.
PROD_API_HOST = "api.missingtable.com"
PROD_QUEUE = "matches.prod"

_COUNTED = frozenset({"completed", "forfeit"})


class FeedEvent(BaseModel):
    """One official fixture, placed in the bracket missing-table files it under."""

    game_key: str = Field(..., min_length=1, description="Official match id")
    league: str = Field(..., description="'Homegrown' or 'Flex'")
    match_type: str = Field(..., description="MT match_type: 'League' or 'Flex'")
    division: str | None = Field(
        None, description="Bracket name; None when no bracket could be found"
    )
    age_group: str | None = Field(None, description="Bracket age group, e.g. 'U15'")
    match_date: date = Field(..., description="Venue-local date")
    completed: bool = Field(..., description="The feed's own 'played' flag")
    on_placeholder: bool = Field(
        False, description="Dated on the feed's postponement placeholder"
    )
    match: Match = Field(..., description="The fixture, ready for build_match_dict")

    @property
    def has_result(self) -> bool:
        return self.completed and self.match.has_score()

    def target(self) -> dict[str, str]:
        """The target config build_match_dict files this fixture under."""
        return {
            "league": self.league,
            "division": self.division or "",
            "age_group": self.age_group or "",
        }

    class Config:
        json_schema_extra = {
            "example": {
                "game_key": "28630",
                "league": "Flex",
                "match_type": "Flex",
                "division": "Turnpike",
                "age_group": "U15",
                "match_date": "2026-10-14",
                "completed": True,
                "on_placeholder": False,
            }
        }


class MtRow(BaseModel):
    """The fields of a missing-table match row this check reads."""

    id: int = Field(..., description="MT matches.id")
    match_id: str | None = Field(None, description="External (official) match id")
    match_date: date | None = Field(None)
    match_status: str | None = Field(None)
    match_type_name: str | None = Field(None)
    league_name: str | None = Field(None)
    division_name: str | None = Field(None)
    age_group_name: str | None = Field(None)
    home_team_name: str | None = Field(None)
    away_team_name: str | None = Field(None)
    home_score: int | None = Field(None)
    away_score: int | None = Field(None)

    class Config:
        json_schema_extra = {
            "example": {
                "id": 7357,
                "match_id": "30925",
                "match_date": "2026-11-22",
                "match_status": "completed",
                "match_type_name": "League",
                "league_name": "Homegrown",
                "division_name": "Southwest (North)",
                "age_group_name": "U15",
            }
        }


class Gap(BaseModel):
    """A disagreement between the feed and MT about whether a result exists."""

    action: Literal["create", "report"] = Field(
        ...,
        description="'create': official result absent from MT, safe to send. "
        "'report': MT holds a result the feed does not — never deleted",
    )
    game_key: str = Field(..., description="Official match id / MT match_id")
    league: str | None = Field(None)
    match_type: str | None = Field(None)
    division: str | None = Field(None)
    age_group: str | None = Field(None)
    match_date: date | None = Field(None)
    home_team: str = Field("")
    away_team: str = Field("")
    score: str = Field("", description="'h-a', with '(p h-a)' for a shootout")
    event: FeedEvent | None = Field(None, description="Set for 'create'")
    mt_id: int | None = Field(None, description="Set for 'report'")

    def line(self) -> str:
        """One line for the dry run and the logs."""
        return (
            f"{self.game_key}  {self.match_date}  {self.league} "
            f"{self.division or '(no bracket)'} {self.age_group or '?'}  "
            f"{self.home_team} v {self.away_team}  {self.score}  "
            f"action={self.action}"
        )


def _score(match: Match) -> str:
    score = f"{match.home_score}-{match.away_score}"
    if match.home_penalty_score is not None:
        score += f" (p {match.home_penalty_score}-{match.away_penalty_score})"
    return score


def diff(
    feed_events: Iterable[FeedEvent],
    mt_rows: Iterable[MtRow],
    feed_keys: Iterable[str] = (),
) -> list[Gap]:
    """Completed official results MT does not have, and MT results the feed lacks.

    * ``create`` — the feed says the match was played, with a score, and no MT
      row of any league or type carries its ``game_key``. A row filed under
      the wrong competition still exists, and resending is the wrong fix for
      that; it is a different finding (SB-1779's ``wrong_league_or_type``).
    * ``report`` — an MT row counted as played (completed/forfeit) in one of
      the competitions the feed covers, whose ``match_id`` is no fixture the
      feed holds, played or not. Reported only: nothing here deletes.

    Unplayed fixtures are never a gap — MT learns of those from the ordinary
    scrape, and the planner handles them.

    ``feed_keys`` adds game keys the feed holds but that could not become a
    :class:`FeedEvent` (no club name, say): they are still in the feed, so an
    MT row carrying one is not MT-only.
    """
    events = list(feed_events)
    rows = list(mt_rows)
    in_mt = {row.match_id for row in rows if row.match_id}
    in_feed = {event.game_key for event in events} | set(feed_keys)
    covered = {(event.league, event.match_type) for event in events}
    scope = {match_type for _, match_type in covered}

    gaps: list[Gap] = []
    for event in events:
        if not event.has_result or event.game_key in in_mt:
            continue
        gaps.append(
            Gap(
                action="create",
                game_key=event.game_key,
                league=event.league,
                match_type=event.match_type,
                division=event.division,
                age_group=event.age_group,
                match_date=event.match_date,
                home_team=event.match.home_team,
                away_team=event.match.away_team,
                score=_score(event.match),
                event=event,
            )
        )

    leagues = {league for league, _ in covered}
    for row in rows:
        if not row.match_id or row.match_id in in_feed:
            continue
        if row.match_status not in _COUNTED:
            continue
        if row.match_type_name not in scope or row.league_name not in leagues:
            continue
        gaps.append(
            Gap(
                action="report",
                game_key=row.match_id,
                league=row.league_name,
                match_type=row.match_type_name,
                division=row.division_name,
                age_group=row.age_group_name,
                match_date=row.match_date,
                home_team=row.home_team_name or "",
                away_team=row.away_team_name or "",
                score=f"{row.home_score}-{row.away_score}",
                mt_id=row.id,
            )
        )

    gaps.sort(key=lambda g: (g.action, str(g.match_date), g.game_key))
    return gaps


def in_window(event: FeedEvent, start: date, end: date) -> bool:
    """Whether a fixture belongs to a run over start..end.

    A result on the postponement placeholder counts whatever the window: the
    feed parks fixtures there months ahead, and the few that carry a score
    (forfeits, mostly) were really decided long before that date.
    """
    if event.on_placeholder and event.has_result:
        return True
    return start <= event.match_date <= end


def counts(gaps: Iterable[Gap]) -> dict[tuple[str, str, str], int]:
    """Gaps per (league, division, age group), sorted."""
    tally: Counter[tuple[str, str, str]] = Counter(
        (g.league or "?", g.division or "(no bracket)", g.age_group or "?")
        for g in gaps
    )
    return dict(sorted(tally.items()))


class Triage(BaseModel):
    """What a run can do about each missing result."""

    send: list[Gap] = Field(default_factory=list, description="Safe to publish")
    no_bracket: list[Gap] = Field(
        default_factory=list, description="Not sendable: no bracket found"
    )
    placeholder: list[Gap] = Field(
        default_factory=list,
        description="Needs a person: a result dated on the postponement placeholder",
    )


def triage(creates: Iterable[Gap]) -> Triage:
    """Split missing results into the sendable and the ones that need a person.

    * No bracket: MT would have to guess the division, and four Flex bracket
      names are also Homegrown ones.
    * On the placeholder date: the feed parks a fixture months ahead with a
      result on it (a forfeit, mostly). Sent, it would land dated in June,
      where no run looks, and the real date is not in the feed to fix it.
    """
    out = Triage()
    for gap in creates:
        event = gap.event
        if event is not None and event.on_placeholder:
            out.placeholder.append(gap)
        elif event is None or not event.division:
            out.no_bracket.append(gap)
        else:
            out.send.append(gap)
    return out


# --- The feed -------------------------------------------------------------


class FeedRead(BaseModel):
    """One read of the official feed."""

    events: list[FeedEvent] = Field(default_factory=list)
    placeholders: frozenset[date] = Field(
        default_factory=frozenset, description="Postponement placeholder dates"
    )
    game_keys: frozenset[str] = Field(
        default_factory=frozenset,
        description="Every game key in the schedule, including fixtures that "
        "could not be read into an event",
    )

    def result_days(self) -> frozenset[date]:
        """Dates holding a played result, placeholder dates excepted — an MT
        page over any of these cannot honestly be empty."""
        return frozenset(
            e.match_date for e in self.events if e.has_result and not e.on_placeholder
        )


def _bracket_of(
    event: AssistEvent, index: AssistIndex
) -> tuple[str | None, str | None]:
    """The (division, age group) MT files a fixture under.

    The fixture's own bracket when it names one. A cross-bracket Flex fixture
    (NYCFC in Empire against CF Montreal in Turnpike) belongs to the bracket
    the feed puts it in, not to whichever target happened to scrape it —
    which is how 25 of them were filed under Turnpike (SB-1779).

    The few bracketless fixtures fall back to the home squad's bracket, then
    the away squad's.
    """
    if event.competition_bracket_id in index.bracket_ids:
        return index.bracket_ids[event.competition_bracket_id]
    for squad in (event.home_squad_id, event.away_squad_id):
        if squad is None:
            continue
        for key in sorted(index.brackets):
            if squad in index.brackets[key]:
                return key
    return None, None


async def read_feed(
    client: AssistClient, leagues: Sequence[str] = tuple(LEAGUES)
) -> FeedRead:
    """Every fixture of the given leagues, and the feed's placeholder dates.

    A fixture with no club name cannot be sent and is skipped with a warning,
    as the scrape does — but its game key is kept, so an MT row carrying it
    is not reported as unknown to the feed.
    """
    from src.scraper.assist_client import AssistFeedError

    events: list[FeedEvent] = []
    placeholders: set[date] = set()
    keys: set[str] = set()
    for league in leagues:
        feed, match_type = LEAGUES[league]
        schedule = await client.schedule(feed)
        index = await client.index(feed)
        parked = schedule.placeholder_dates()
        placeholders |= parked
        skipped = 0
        for raw in schedule.events:
            keys.add(raw.game_key)
            day = raw.local_datetime.date()
            try:
                match = raw.to_match(postponed=day in parked)
            except (AssistFeedError, ValueError):
                skipped += 1
                continue
            division, age_group = _bracket_of(raw, index)
            events.append(
                FeedEvent(
                    game_key=raw.game_key,
                    league=league,
                    match_type=match_type,
                    division=division,
                    age_group=age_group,
                    match_date=day,
                    completed=raw.completed,
                    on_placeholder=day in parked,
                    match=match,
                )
            )
        if skipped:
            logger.warning("completeness.feed_skipped", league=league, skipped=skipped)
    return FeedRead(
        events=events, placeholders=frozenset(placeholders), game_keys=frozenset(keys)
    )


# --- missing-table --------------------------------------------------------


class MtReadError(RuntimeError):
    """missing-table could not be read completely. Nothing may be sent on it."""


class MtPageFull(MtReadError):
    """A page of /api/matches came back at the PostgREST row cap."""


def mt_pages(
    start: date, end: date, extra_days: Iterable[date] = (), page_days: int = 7
) -> list[tuple[date, date]]:
    """The inclusive date ranges to read: start..end a week at a time, plus
    one single-day page for each extra day outside it."""
    pages: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        last = min(cursor + timedelta(days=page_days - 1), end)
        pages.append((cursor, last))
        cursor = last + timedelta(days=1)
    pages += [(day, day) for day in sorted(set(extra_days)) if not start <= day <= end]
    return pages


def fetch_mt_rows(
    api_url: str,
    api_key: str,
    pages: Iterable[tuple[date, date]],
    *,
    expect_days: Iterable[date] = (),
    client: httpx.Client | None = None,
) -> list[MtRow]:
    """Every MT match dated on the given pages, de-duplicated by MT id.

    Raises :class:`MtReadError` — never returns a short read, because a short
    read here is indistinguishable from missing results, and would resend
    and alert on matches MT already has:

    * on any HTTP failure;
    * on a page of :data:`MT_PAGE_CAP` rows or more (:class:`MtPageFull`);
    * on an **empty** page over any of ``expect_days``. When its database
      query fails, /api/matches answers ``200 []``, so an empty week that the
      feed says held played results is an outage, not a week of gaps.

    A page of :data:`MT_SPLIT_AT` rows or more is split in half and re-read.
    """
    import httpx

    expected = frozenset(expect_days)
    http = client or httpx.Client(timeout=60.0)
    rows: dict[int, MtRow] = {}
    todo = list(pages)
    try:
        while todo:
            first, last = todo.pop(0)
            try:
                resp = http.get(
                    f"{api_url}/api/matches",
                    params={
                        "start_date": first.isoformat(),
                        "end_date": last.isoformat(),
                    },
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                resp.raise_for_status()
                page: list[dict[str, Any]] = resp.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise MtReadError(f"/api/matches {first}..{last}: {exc}") from exc
            if len(page) >= MT_PAGE_CAP:
                raise MtPageFull(
                    f"/api/matches {first}..{last} returned {len(page)} rows, the "
                    f"PostgREST cap: the page is truncated, so MT cannot be read "
                    f"completely."
                )
            if len(page) >= MT_SPLIT_AT and first < last:
                middle = first + (last - first) // 2
                todo[:0] = [(first, middle), (middle + timedelta(days=1), last)]
                continue
            if len(page) >= MT_SPLIT_AT:
                logger.warning(
                    "completeness.mt_page_large", day=first.isoformat(), rows=len(page)
                )
            if not page and any(first <= day <= last for day in expected):
                raise MtReadError(
                    f"/api/matches {first}..{last} returned no rows, but the feed "
                    f"has results played in it: treating it as a failed read"
                )
            for raw in page:
                row = MtRow.model_validate(
                    {k: raw.get(k) for k in MtRow.model_fields}
                    | {"match_id": _text(raw.get("match_id"))}
                )
                rows[row.id] = row
    finally:
        if client is None:
            http.close()
    return list(rows.values())


def _text(value: object) -> str | None:
    return None if value in (None, "") else str(value)


# --- Publish safety -------------------------------------------------------


def api_host(api_url: str) -> str:
    """The host of an MT API URL, for the banner. No credentials, no path."""
    try:
        return urlsplit(api_url).hostname or "(unknown host)"
    except ValueError:
        return "(unreadable API URL)"


def publish_mismatch(api_url: str, queue_name: str, exchange_name: str) -> str | None:
    """Why publishing would be unsafe, or None if it is not.

    The diff is read from one MT and the fix is published to a queue whose
    workers write another. They must be the same database: prod API with the
    prod queue, anything else with anything but the prod queue. A fan-out
    exchange reaches every bound queue, prod included, so it is refused.
    """
    if not queue_name:
        return (
            f"publishing to exchange '{exchange_name}' fans out to every queue "
            "bound to it; backfill publishes only to a named queue"
        )
    prod_api = api_host(api_url) == PROD_API_HOST
    prod_queue = queue_name == PROD_QUEUE
    if prod_queue and not prod_api:
        return (
            f"queue '{queue_name}' feeds production, but gaps were read from "
            f"{api_host(api_url)}, not {PROD_API_HOST}"
        )
    if prod_api and not prod_queue:
        return (
            f"gaps were read from {PROD_API_HOST}, but queue '{queue_name}' "
            f"does not feed production"
        )
    return None
