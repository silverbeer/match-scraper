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

The reconcile (SB-1787) asks the next question: of the rows MT does have,
which disagree with the feed — score, home/away, status or date.
:func:`classify` is pure; :func:`read_season` reads MT.

Nothing here deletes. An MT row the feed does not know is reported, never
removed — the feed drops fixtures for reasons of its own, and a scraped
result is not ours to throw away on its say-so.
"""

from __future__ import annotations

import re
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

# Every feed read_feed can read. Academy is here and not in LEAGUES: the
# backfill covers Homegrown and Flex only, and its full-scope check compares
# against LEAGUES. The reconcile reads all three (SB-1787). Academy files a
# conference as its division, and its fixtures are League fixtures.
FEEDS: dict[str, tuple[str, str]] = {
    **LEAGUES,
    "Academy": ("academy", "League"),
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
    league: str = Field(..., description="'Homegrown', 'Flex' or 'Academy'")
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
        feed, match_type = FEEDS[league]
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


# --- Reconcile (SB-1787) --------------------------------------------------
#
# The backfill asks which official results have no MT row. The reconcile asks
# the next question: of the rows MT does have, which disagree with the feed?
# Nothing re-checked a match after its first scrape, so a corrected score, a
# result that arrived after the row went quiet, a home/away reversal or a
# re-dated postponement stayed wrong for good (SB-1779: 35 wrong scores, 14
# completed but still scheduled, 42 re-dated to 2027).

# The competitions the reconcile compares. Tournament and friendly rows are
# not the feed's.
RECONCILE_TYPES = frozenset({"League", "Flex"})

# Classes that send a correction, in report order; ``voided`` never sends.
Klass = Literal["score", "swap", "status", "redate", "voided"]
SENDABLE = ("score", "swap", "status", "redate")
CLASSES = (*SENDABLE, "voided")

# The rows /api/agent/season-matches returns per page. Its maximum is 1000.
SEASON_PAGE_SIZE = 500

# More pages than this is a paging bug, not a season: stop rather than loop.
SEASON_MAX_PAGES = 200

_UNPLAYED = frozenset({"scheduled", "tbd"})
# Statuses a person sets; the MT worker holds them unless the feed brings a
# score or a new date (match_tasks._incoming_status, SB-1135).
_HELD = frozenset({"postponed", "cancelled"})


class SeasonRow(BaseModel):
    """One row of missing-table's /api/agent/season-matches."""

    id: int = Field(..., description="MT matches.id")
    match_id: str | None = Field(None, description="External (official) match id")
    match_date: date | None = Field(None)
    match_status: str | None = Field(None)
    home_team_id: int | None = Field(None)
    home_team_name: str | None = Field(None)
    away_team_id: int | None = Field(None)
    away_team_name: str | None = Field(None)
    home_score: int | None = Field(None)
    away_score: int | None = Field(None)
    home_penalty_score: int | None = Field(None)
    away_penalty_score: int | None = Field(None)
    division_id: int | None = Field(None)
    league_id: int | None = Field(None)
    league: str | None = Field(
        None, description="League name, from league_id; set by the reader"
    )
    match_type: str | None = Field(None, description="Match type name")
    source: str | None = Field(None)
    entered_by_person: bool = Field(
        False, description="source is not one the feed writes: a person's row"
    )
    score_locked: bool = Field(False, description="MT holds this row's result")

    def score(self) -> str:
        return _score_text(
            self.home_score,
            self.away_score,
            self.home_penalty_score,
            self.away_penalty_score,
        )

    class Config:
        json_schema_extra = {
            "example": {
                "id": 7482,
                "match_id": "28249",
                "match_date": "2026-10-04",
                "match_status": "completed",
                "home_team_name": "Miami Futbol Academy Rush",
                "away_team_name": "Sol SC Florida",
                "home_score": 1,
                "away_score": 0,
                "league_id": 1,
                "league": "Homegrown",
                "match_type": "League",
                "source": "match-scraper-agent",
                "entered_by_person": False,
                "score_locked": False,
            }
        }


class Change(BaseModel):
    """One way an MT row disagrees with the feed, and what the run does about it."""

    game_key: str = Field(..., description="Official match id / MT match_id")
    mt_id: int = Field(..., description="MT matches.id")
    klass: Klass = Field(..., description="What differs")
    action: Literal["send", "report"] = Field(
        ..., description="'send': publish the feed's fixture. 'report': list only"
    )
    league: str = Field(...)
    match_type: str = Field(...)
    field: str = Field(..., description="What differs, e.g. 'score', 'date'")
    mt_value: str = Field(..., description="MT's value")
    feed_value: str = Field(..., description="The feed's value")
    flags: list[str] = Field(
        default_factory=list,
        description="locked, person, forfeit, placeholder, names differ",
    )
    reason: str = Field("", description="Why a change is report-only")
    mt_scored: bool = Field(False, description="MT held a score before this")
    event: FeedEvent | None = Field(None, exclude=True, description="Set for 'send'")

    class Config:
        json_schema_extra = {
            "example": {
                "game_key": "26044",
                "mt_id": 5120,
                "klass": "score",
                "action": "send",
                "league": "Homegrown",
                "match_type": "League",
                "field": "score",
                "mt_value": "1-1",
                "feed_value": "1-2",
                "flags": ["person"],
                "reason": "",
                "mt_scored": True,
            }
        }

    @property
    def overrides_person(self) -> bool:
        """A sent change that replaces a score a person entered."""
        return self.action == "send" and "person" in self.flags and self.mt_scored

    def line(self) -> str:
        """``game_key | class | field: MT -> feed | flags``, for the log."""
        flags = ", ".join(self.flags) or "-"
        line = (
            f"{self.game_key} | {self.klass} | {self.field}: "
            f"{self.mt_value} -> {self.feed_value} | {flags}"
        )
        if self.action == "report":
            line += f" | report only: {self.reason}"
        return line

    def payload(self) -> dict[str, Any]:
        """The queue message for a sent change: the feed's fixture as it stands."""
        from src.orchestrator.tools import build_match_dict

        if self.event is None or self.action != "send":
            raise ValueError(f"{self.game_key}: a report-only change has no payload")
        payload = build_match_dict(self.event.match, self.event.target())
        if self.klass == "redate":
            payload["match_status"] = "scheduled"
        return payload


def _score_text(
    home: int | None, away: int | None, home_pens: int | None, away_pens: int | None
) -> str:
    if home is None or away is None:
        return "no score"
    text = f"{home}-{away}"
    if home_pens is not None:
        text += f" (p {home_pens}-{away_pens})"
    return text


def _team_key(name: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").casefold())


def _orientation(
    feed_home: str, feed_away: str, mt_home: str | None, mt_away: str | None
) -> Literal["same", "swap", "unknown"]:
    """Whether the feed has MT's home side at home.

    MT holds its own team names and the feed holds the clubs' official ones,
    which differ wherever MT has an alias. One side agreeing is enough; when
    neither does the orientation is unknown and the scores are compared as
    they stand — the worker resolves both names to team ids either way.
    """
    fh, fa, mh, ma = map(_team_key, (feed_home, feed_away, mt_home, mt_away))
    if fh == mh or fa == ma:
        return "same"
    if fh == ma or fa == mh:
        return "swap"
    return "unknown"


def _compare(event: FeedEvent, row: SeasonRow, today: date) -> Change | None:
    """How one MT row disagrees with its fixture, or None if it does not.

    * ``swap``: the feed has the sides the other way round, with a result.
    * ``status``: the feed has a result; MT still has the match unplayed
      (scheduled, tbd or postponed — the worker lets a real score lift a
      postponement). A cancelled row is reported: a person cancelled it.
    * ``score``: both have a result, and the scores or shootout differ.
    * ``redate``: unplayed in both, the feed has a real new date.
    * ``voided``: MT counts it as played; the feed does not. Report only —
      the worker refuses completed -> postponed, and nothing here deletes.

    A forfeit counts as completed, so a forfeit with the feed's score is no
    change. Never sends: a locked row, a forfeit whose score differs, a
    result on the placeholder date (it would land dated months ahead), or an
    unscored fixture whose new date is not in the future. A row MT still
    has as scheduled on a past date whose fixture the feed has parked on the
    placeholder is reported: postponed, but with no real date to send.
    """
    from src.orchestrator.tools import _normalize_team_name

    match = event.match
    feed_home = _normalize_team_name(match.home_team, league=event.league)
    feed_away = _normalize_team_name(match.away_team, league=event.league)
    orientation = _orientation(
        feed_home, feed_away, row.home_team_name, row.away_team_name
    )
    status = row.match_status or ""
    flags: list[str] = []
    if row.score_locked:
        flags.append("locked")
    if row.entered_by_person:
        flags.append("person")
    if status == "forfeit":
        flags.append("forfeit")

    if event.completed and not match.has_score():
        # "Played" with no score yet: nothing to compare and nothing to send.
        return None

    reason = ""
    klass: Klass
    if event.has_result:
        home = match.home_score if isinstance(match.home_score, int) else None
        away = match.away_score if isinstance(match.away_score, int) else None
        home_pens, away_pens = match.home_penalty_score, match.away_penalty_score
        feed_score = (home, away, home_pens, away_pens)
        if orientation == "swap":
            feed_score = (away, home, away_pens, home_pens)
        mt_score = (
            row.home_score,
            row.away_score,
            row.home_penalty_score,
            row.away_penalty_score,
        )
        result = _score_text(home, away, home_pens, away_pens)
        if status not in _UNPLAYED | _COUNTED | _HELD:
            return None  # a status this check does not know
        if orientation == "swap":
            klass = "swap"
            field = "home/away"
            mt_value = f"{row.home_team_name} v {row.away_team_name} {row.score()}"
            feed_value = f"{feed_home} v {feed_away} {result}"
        elif status in _UNPLAYED | _HELD:
            klass, field = "status", "status"
            mt_value, feed_value = status, f"completed {result}"
        elif mt_score != feed_score:
            klass, field = "score", "score"
            mt_value, feed_value = row.score(), result
        else:
            return None
        if event.on_placeholder:
            flags.append("placeholder")
        if row.score_locked:
            reason = "locked, differs"
        elif status == "forfeit":
            reason = "forfeit with a different score: needs a person"
        elif status == "cancelled":
            reason = "cancelled in MT, played per feed"
        elif event.on_placeholder:
            reason = "result on the placeholder date: needs a person"
    elif status in _COUNTED:
        klass, field = "voided", "status"
        mt_value = f"{status} {row.score()}"
        feed_value = "not completed"
        if event.on_placeholder:
            flags.append("placeholder")
            feed_value += f" (postponed, {event.match_date})"
        elif event.match_date != row.match_date:
            feed_value += f" ({event.match_date})"
        reason = "MT counts it as played and the feed does not; never voided here"
    elif status in _UNPLAYED and event.on_placeholder:
        # The feed postponed it; MT still has it played-pending on its old
        # date. There is no real date to send, and the scrape's postponed
        # message never moves the date either.
        klass, field = "redate", "date"
        mt_value = f"{status} {row.match_date}"
        feed_value = f"postponed ({event.match_date})"
        flags.append("placeholder")
        reason = "postponed to the placeholder: no real date yet"
    elif status in _UNPLAYED or status == "postponed":
        if event.on_placeholder or event.match_date == row.match_date:
            return None
        klass, field = "redate", "date"
        mt_value, feed_value = str(row.match_date), str(event.match_date)
        if row.score_locked:
            reason = "locked, differs"
        elif event.match_date <= today:
            reason = "new date is not in the future and the feed has no score"
    else:
        return None

    if orientation == "unknown":
        flags.append("names differ")
    return Change(
        game_key=event.game_key,
        mt_id=row.id,
        klass=klass,
        action="report" if reason else "send",
        league=event.league,
        match_type=event.match_type,
        field=field,
        mt_value=mt_value,
        feed_value=feed_value,
        flags=flags,
        reason=reason,
        mt_scored=row.home_score is not None and row.away_score is not None,
        event=None if reason else event,
    )


def _in_scope(
    row: SeasonRow, leagues: Iterable[str], today: date, since: date | None
) -> bool:
    return (
        bool(row.match_id)
        and row.league in set(leagues)
        and row.match_type in RECONCILE_TYPES
        and row.match_date is not None
        and row.match_date < today
        and (since is None or row.match_date >= since)
    )


def classify(
    feed_events: Iterable[FeedEvent],
    mt_rows: Iterable[SeasonRow],
    *,
    today: date,
    leagues: Iterable[str] = tuple(FEEDS),
    since: date | None = None,
) -> list[Change]:
    """Every past MT row of ``leagues`` that disagrees with its official fixture.

    Joined on ``match_id`` = ``game_key``. Only rows dated before ``today``,
    of type League or Flex, are compared. A row whose fixture is filed under
    another competition in the feed is a different finding (SB-1779's
    ``wrong_league_or_type``) and is skipped. Pure: no I/O.
    """
    leagues = tuple(leagues)
    by_key: dict[str, list[FeedEvent]] = {}
    for item in feed_events:
        by_key.setdefault(item.game_key, []).append(item)

    changes: list[Change] = []
    for row in mt_rows:
        if not _in_scope(row, leagues, today, since):
            continue
        event: FeedEvent | None = next(
            (
                e
                for e in by_key.get(row.match_id or "", [])
                if e.league == row.league and e.match_type == row.match_type
            ),
            None,
        )
        if event is None:
            continue
        change = _compare(event, row, today)
        if change is not None:
            changes.append(change)

    order = {klass: i for i, klass in enumerate(CLASSES)}
    changes.sort(key=lambda c: (order[c.klass], c.action, c.game_key))
    return changes


def mt_only(
    mt_rows: Iterable[SeasonRow],
    feed_keys: Iterable[str],
    *,
    today: date,
    leagues: Iterable[str] = tuple(FEEDS),
    since: date | None = None,
) -> list[SeasonRow]:
    """Past MT rows counted as played whose match id the feed does not hold.

    Report only: the feed drops fixtures for reasons of its own, and nothing
    here deletes.
    """
    keys = frozenset(feed_keys)
    leagues = tuple(leagues)
    return [
        row
        for row in mt_rows
        if _in_scope(row, leagues, today, since)
        and row.match_id not in keys
        and row.match_status in _COUNTED
    ]


def totals(changes: Iterable[Change]) -> dict[str, dict[str, int]]:
    """Per class: how many are sent and how many only reported."""
    out = {klass: {"send": 0, "report": 0} for klass in CLASSES}
    for change in changes:
        out[change.klass][change.action] += 1
    return out


def _get_json(http: httpx.Client, url: str, api_key: str, **params: Any) -> Any:
    import httpx

    try:
        resp = http.get(
            url, params=params, headers={"Authorization": f"Bearer {api_key}"}
        )
        resp.raise_for_status()
        return resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise MtReadError(f"{urlsplit(url).path}: {exc}") from exc


def read_season(
    api_url: str,
    api_key: str,
    *,
    season: str,
    leagues: Sequence[str],
    start: date | None = None,
    end: date | None = None,
    page_size: int = SEASON_PAGE_SIZE,
    client: httpx.Client | None = None,
) -> list[SeasonRow]:
    """Every MT match of one season and those leagues, from /api/agent/season-matches.

    The season and league ids are looked up by name: Flex's id is assigned
    by a sequence, so it differs between databases.

    Pages 0, 1, 2… are read until the first **empty** one — a short page is
    not proof of the last — and all of them before the caller sends
    anything: a correction that re-dates a match moves it between pages.

    Raises :class:`MtReadError` on any failure: an HTTP error, an unknown
    season or league, a malformed page, or more than
    :data:`SEASON_MAX_PAGES` pages. Never returns a partial read.
    """
    import httpx

    http = client or httpx.Client(timeout=60.0)
    try:
        seasons = _get_json(http, f"{api_url}/api/seasons", api_key)
        if not isinstance(seasons, list):
            raise MtReadError("/api/seasons: not a list")
        season_ids = [
            s.get("id")
            for s in seasons
            if isinstance(s, dict) and s.get("name") == season
        ]
        if len(season_ids) != 1 or not isinstance(season_ids[0], int):
            raise MtReadError(f"season {season!r} not found in /api/seasons")
        found = _get_json(http, f"{api_url}/api/leagues", api_key)
        if not isinstance(found, list):
            raise MtReadError("/api/leagues: not a list")
        # An entry without a string name and an int id cannot be one we asked
        # for; skipped, never a KeyError.
        league_ids: dict[str, int] = {
            item["name"]: item["id"]
            for item in found
            if isinstance(item, dict)
            and isinstance(item.get("name"), str)
            and isinstance(item.get("id"), int)
        }
        missing = [name for name in leagues if name not in league_ids]
        if missing:
            raise MtReadError(f"league(s) {', '.join(missing)} not in /api/leagues")
        names = {league_ids[name]: name for name in leagues}

        params: dict[str, Any] = {
            "season_id": season_ids[0],
            "league_ids": ",".join(str(i) for i in sorted(names)),
            "page_size": page_size,
        }
        if start:
            params["start_date"] = start.isoformat()
        if end:
            params["end_date"] = end.isoformat()

        rows: dict[int, SeasonRow] = {}
        for page in range(SEASON_MAX_PAGES):
            body = _get_json(
                http,
                f"{api_url}/api/agent/season-matches",
                api_key,
                **params,
                page=page,
            )
            matches = body.get("matches") if isinstance(body, dict) else None
            if not isinstance(matches, list):
                raise MtReadError(
                    f"/api/agent/season-matches page {page}: no 'matches' list"
                )
            if not matches:
                break
            for raw in matches:
                try:
                    row = SeasonRow.model_validate(
                        {k: raw.get(k) for k in SeasonRow.model_fields}
                        | {
                            "match_id": _text(raw.get("match_id")),
                            "league": names.get(raw.get("league_id")),
                            "entered_by_person": bool(raw.get("entered_by_person")),
                            "score_locked": bool(raw.get("score_locked")),
                        }
                    )
                except (AttributeError, ValueError) as exc:
                    raise MtReadError(
                        f"/api/agent/season-matches page {page}: bad row: {exc}"
                    ) from exc
                rows[row.id] = row
        else:
            raise MtReadError(
                f"/api/agent/season-matches: more than {SEASON_MAX_PAGES} pages; "
                "stopping rather than reading forever"
            )
    finally:
        if client is None:
            http.close()
    return list(rows.values())
