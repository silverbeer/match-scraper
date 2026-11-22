"""
Read a tournament from a modular11 event page — no browser.

MLS NEXT Fest 2025 was modular11 event ``75``: 2,458 matches across six age
groups. Its schedule widget calls ``events/league/get_matches``, which returns
an HTML fragment of 25 matches plus a paginator, the same shape as the league
endpoint ``release_detector`` reads.

Things that are true of the endpoint and easy to get wrong:

* ``open_page`` is 1-based, and ``0`` answers with page 1 again (checked live
  against event 75 on 2026-11-22). Starting at 0 would fetch the first page
  twice.
* A page past the end answers ``No data available.``, the same body as a
  window with no matches. The paginator's "N page out of M" is what ends the
  loop; an empty page, and a page repeating the previous one's ids, both end
  it too, so a wrong M cannot loop or double-count.
* ``js-match-game`` is not the match id (that is the first cell's text) and
  is not a usable bracket position either: the 2025 round of 32 has sixteen
  matches numbered 0-7 twice, once per half of the draw, with nothing on the
  row saying which half. So no round order is sent from this source.
* The score cell reads ``4&nbsp:&nbsp1`` — no semicolons — and ``TBD`` when
  unplayed. Any other text is sent as no score and reported. A fixture whose teams are not known yet has both teams ``TBD``.
* An empty read is never taken on trust: only a 2xx is a page, a body with
  neither match rows nor ``No data available.`` fails the age group, and so
  does a full page with no paginator. Rows that cannot be read are counted.
* Times are the venue's wall clock with no zone.
"""

from __future__ import annotations

import asyncio
import random
import re
from collections.abc import Awaitable, Callable, Sequence
from datetime import date, datetime
from pathlib import Path

import httpx
from bs4 import BeautifulSoup, Tag
from pydantic import BaseModel, Field

from ...models.tournament import TournamentMatch
from ...utils.logger import get_logger
from ..modular11 import AGE_GROUP_IDS
from .mapping import collapse

logger = get_logger()

ENDPOINT_URL = "https://www.modular11.com/events/league/get_matches"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; mls-match-scraper/tournament-events)",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "text/html,*/*",
}

# The desktop block of each match; the mobile block repeats it.
MATCH_ROW_SELECTOR = ".table-content-row[js-match-game]"
MATCH_COLUMN_SELECTORS = {
    "match_id": ".col-sm-1",  # First column: Match ID + Gender
    "details": ".col-sm-2",  # Second column: Date/Time + Venue
    "location": ".container-location p",
    "home_team": ".container-first-team p",
    "away_team": ".container-second-team p",
    "score": ".container-score .score-match-table",
}
# The round label sits outside the desktop block, in the row's mobile half.
ROW_CONTAINER_CLASS = "container-row"
ROUND_LABEL_SELECTOR = ".place-info"
PAGINATOR_SELECTOR = "[js-paginator] .current-pages"

_MATCH_ID = re.compile(r"\d+")
# A two- or four-digit year, and nothing digit-like after it: "12/12/2026"
# must not be read as the year 20 followed by "26".
_KICKOFF = re.compile(
    r"(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4}|\d{2})(?!\d)"
    r"(?:\s+(\d{1,2}:\d{2})\s*([ap]m))?",
    re.I,
)
_SCORE = re.compile(r"^(\d+)\s*:\s*(\d+)(?:\s*\((\d+)\s*:\s*(\d+)\))?$")
_PAGES = re.compile(r"(\d+)\s+page\s+out\s+of\s+(\d+)", re.I)
_AGE = re.compile(r"^U\d{2}$")

# What the endpoint answers when a window or a page holds no matches.
NO_DATA_SELECTOR = ".block-without-matches"
NO_DATA_TEXT = "no data available"
# Matches per full page. A page this full with no paginator is a truncated
# read, not a short event.
PAGE_SIZE = 25
# What an unplayed score cell reads.
UNPLAYED_SCORE = "tbd"

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
RETRY_AFTER_STATUS = frozenset({429, 503})


class Modular11EventError(Exception):
    """Raised when an event page cannot be fetched."""


class ParsedPage(BaseModel):
    """One ``get_matches`` fragment, parsed."""

    matches: list[TournamentMatch] = Field(default_factory=list)
    page: int | None = Field(
        default=None, description="Page the paginator says this is"
    )
    total_pages: int | None = Field(
        default=None, description="Pages the paginator declares"
    )
    skipped: int = Field(default=0, description="Rows that could not be read")
    no_data: bool = Field(
        default=False, description="The body is the endpoint's 'No data available.'"
    )
    unread_scores: dict[str, int] = Field(
        default_factory=dict,
        description="Score cells that are neither a score nor TBD -> rows",
    )


def parse_score(
    text: str | None,
) -> tuple[int | None, int | None, int | None, int | None]:
    """``(home, away, home_pens, away_pens)`` from a score cell.

    ``2 : 1`` is a result and ``1 : 1 (4 : 3)`` a result decided on penalties.
    Penalties are kept only when regulation is level and they are not 0:0 —
    the rule missing-table stores by. Anything else is no score at all.

    >>> parse_score("1\xa0:\xa01 (4 : 3)")
    (1, 1, 4, 3)
    >>> parse_score("TBD")
    (None, None, None, None)
    """
    # The cell is written "4&nbsp:&nbsp1" with no semicolons, and an HTML
    # parser leaves an unterminated entity that runs into a digit undecoded.
    found = _SCORE.match(_score_text(text))
    if not found:
        return None, None, None, None
    home, away = int(found.group(1)), int(found.group(2))
    if found.group(3) is None:
        return home, away, None, None
    home_pens, away_pens = int(found.group(3)), int(found.group(4))
    if home != away or (home_pens == 0 and away_pens == 0):
        return home, away, None, None
    return home, away, home_pens, away_pens


def _score_text(text: str | None) -> str:
    # The cell is written "4&nbsp:&nbsp1" with no semicolons, and an HTML
    # parser leaves an unterminated entity that runs into a digit undecoded.
    return collapse((text or "").replace("&nbsp;", " ").replace("&nbsp", " "))


def unreadable_score(text: str | None) -> str | None:
    """The cell's text when it is neither a score, ``TBD`` nor blank.

    Such a cell is sent as "no score", which is right for ``TBD`` and a guess
    for anything else (``1 : 1 (4 : 3) FF``), so it is reported.
    """
    cleaned = _score_text(text)
    if not cleaned or cleaned.lower() == UNPLAYED_SCORE or _SCORE.match(cleaned):
        return None
    return cleaned


def parse_kickoff(text: str | None) -> datetime | None:
    """``12/12/25 08:00am`` as a naive datetime; a bare date is midnight.

    The year may have two digits or four.
    """
    found = _KICKOFF.search(collapse(text))
    if not found:
        return None
    month, day, year, clock, meridiem = found.groups()
    stamp = f"{int(month):02d}/{int(day):02d}/{year}"
    year_format = "%Y" if len(year) == 4 else "%y"
    try:
        if clock is None:
            return datetime.strptime(stamp, f"%m/%d/{year_format}")
        return datetime.strptime(
            f"{stamp} {clock}{meridiem.lower()}", f"%m/%d/{year_format} %I:%M%p"
        )
    except ValueError:
        return None


def _text(node: Tag | None) -> str:
    return collapse(node.get_text(" ")) if node is not None else ""


def _attr(row: Tag, name: str) -> str | None:
    value = row.get(name)
    return collapse(value) or None if isinstance(value, str) else None


def _parse_row(row: Tag, age_group: str) -> TournamentMatch | None:
    """One desktop row as a match, or None if it has no id, date or teams."""
    columns = row.find_all("div", recursive=False)
    id_cell = row.select_one(MATCH_COLUMN_SELECTORS["match_id"])
    match_id = _MATCH_ID.search(_text(id_cell))
    details = row.select_one(MATCH_COLUMN_SELECTORS["details"])
    # The date is the details cell's own leading text; the venue follows it.
    kickoff = parse_kickoff(_text(details))
    home = _text(row.select_one(MATCH_COLUMN_SELECTORS["home_team"]))
    away = _text(row.select_one(MATCH_COLUMN_SELECTORS["away_team"]))
    if not match_id or kickoff is None or not home or not away:
        return None

    # Third column: the age group, as the row itself states it.
    row_age = _text(columns[2]) if len(columns) > 2 else ""
    container = row.find_parent(class_=ROW_CONTAINER_CLASS)
    label = container.select_one(ROUND_LABEL_SELECTOR) if container else None
    home_score, away_score, home_pens, away_pens = parse_score(
        _text(row.select_one(MATCH_COLUMN_SELECTORS["score"]))
    )
    return TournamentMatch(
        source_match_id=match_id.group(0),
        age_group=row_age if _AGE.match(row_age) else age_group,
        home_team=home,
        away_team=away,
        kickoff_local=kickoff,
        location=_text(row.select_one(MATCH_COLUMN_SELECTORS["location"])) or None,
        home_score=home_score,
        away_score=away_score,
        home_penalty_score=home_pens,
        away_penalty_score=away_pens,
        competition=_attr(row, "js-match-bracket"),
        source_division=_attr(row, "js-match-group"),
        source_round_label=_text(label) or None,
        # js-match-game repeats within a round (see the module docstring).
        bracket_position=None,
    )


def parse_page(html: str, age_group: str) -> ParsedPage:
    """Parse one fragment. ``No data available.`` parses to no matches."""
    soup = BeautifulSoup(html, "html.parser")
    parsed = ParsedPage()
    parsed.no_data = (
        soup.select_one(NO_DATA_SELECTOR) is not None
        or NO_DATA_TEXT in _text(soup).lower()
    )
    for row in soup.select(MATCH_ROW_SELECTOR):
        cell = unreadable_score(_text(row.select_one(MATCH_COLUMN_SELECTORS["score"])))
        if cell is not None:
            parsed.unread_scores[cell] = parsed.unread_scores.get(cell, 0) + 1
        try:
            match = _parse_row(row, age_group)
        except ValueError:
            match = None
        if match is None:
            parsed.skipped += 1
        else:
            parsed.matches.append(match)

    pages = _PAGES.search(_text(soup.select_one(PAGINATOR_SELECTOR)))
    if pages:
        parsed.page, parsed.total_pages = int(pages.group(1)), int(pages.group(2))
    return parsed


class Modular11EventSource:
    """All matches of one modular11 event, one polite request at a time."""

    name = "modular11"

    FIRST_PAGE = 1
    # 25 matches a page; the largest 2025 age group was 19 pages.
    MAX_PAGES = 60
    REQUEST_TIMEOUT = 30.0
    MAX_RETRIES = 3
    RETRY_DELAY_BASE = 1.0
    RETRY_BACKOFF_MULTIPLIER = 2.0
    # A server asking for longer than this is one to stop bothering.
    MAX_RETRY_AFTER = 120.0
    JITTER = 0.5

    def __init__(
        self,
        event_id: str,
        *,
        delay: float = 1.0,
        save_raw: Path | None = None,
        client: httpx.AsyncClient | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.event_id = str(event_id)
        self.id_prefix = f"m11-{self.event_id}-"
        self.delay = max(delay, 0.0)
        self.save_raw = save_raw
        self._client = client
        self._sleep = sleep
        self._requested = False
        self.requests = 0
        self.failures: dict[str, str] = {}
        self.unmapped: dict[str, int] = {}

    async def fetch(
        self, age_groups: Sequence[str], start: date, end: date
    ) -> list[TournamentMatch]:
        """Every match for ``age_groups``. A failed age group does not stop the rest."""
        self.failures = {}
        self.unmapped = {}
        matches: list[TournamentMatch] = []
        client = self._client or httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT)
        try:
            for age_group in age_groups:
                if age_group not in AGE_GROUP_IDS:
                    self.failures[age_group] = (
                        f"unknown age group; known: {', '.join(AGE_GROUP_IDS)}"
                    )
                    continue
                try:
                    matches.extend(
                        await self._fetch_age_group(client, age_group, start, end)
                    )
                except Modular11EventError as exc:
                    self.failures[age_group] = str(exc)
                    logger.warning(
                        "Tournament age group failed",
                        extra={"age_group": age_group, "error": str(exc)},
                    )
        finally:
            if self._client is None:
                await client.aclose()
        return matches

    async def _fetch_age_group(
        self, client: httpx.AsyncClient, age_group: str, start: date, end: date
    ) -> list[TournamentMatch]:
        """Walk the pages of one age group until the paginator says stop."""
        found: dict[str, TournamentMatch] = {}
        previous_ids: set[str] | None = None
        page = self.FIRST_PAGE
        last_page = self.FIRST_PAGE + self.MAX_PAGES - 1
        while page <= last_page:
            html = await self._get(client, age_group, page, start, end)
            self._save(age_group, page, html)
            parsed = parse_page(html, age_group)
            ids = {match.source_match_id for match in parsed.matches}
            rows = len(parsed.matches) + parsed.skipped
            if parsed.skipped:
                # A finding, not a log line: these matches are not sent.
                self._count(
                    f"rows that could not be read ({age_group})", parsed.skipped
                )
                logger.warning(
                    "Unreadable tournament rows skipped",
                    extra={
                        "age_group": age_group,
                        "page": page,
                        "skipped": parsed.skipped,
                    },
                )
            for cell, count in parsed.unread_scores.items():
                self._count(f"score {cell!r}", count)
            # Neither matches nor the endpoint's own "no data": a block page,
            # a login page, a changed layout. Reading it as "no matches" would
            # report an empty event as a clean run.
            if not rows and not parsed.no_data:
                raise Modular11EventError(
                    f"get_matches page {page} for {age_group} is neither matches "
                    f"nor 'No data available.' ({len(html)} bytes)"
                )
            # Past the end: empty, or (as page 0 does page 1) a repeat.
            if not ids or ids == previous_ids:
                break
            for match in parsed.matches:
                found.setdefault(match.source_match_id, match)
            previous_ids = ids
            if parsed.total_pages is None:
                if rows >= PAGE_SIZE:
                    raise Modular11EventError(
                        f"get_matches page {page} for {age_group} is full "
                        f"({rows} rows) but has no readable paginator: "
                        "more pages may exist"
                    )
                break
            if page >= parsed.total_pages:
                break
            page += 1
        else:
            # Not an error to lose the matches already read over, but not a
            # complete read either.
            self.failures[age_group] = (
                f"stopped at the {self.MAX_PAGES}-page cap; "
                f"{len(found)} matches read, more may exist"
            )
        return list(found.values())

    def _params(
        self, age_group: str, page: int, start: date, end: date
    ) -> dict[str, str]:
        # As release_detector sends for the league, except the event id, the
        # event match type, no group filter and the page.
        return {
            "open_page": str(page),
            "academy": "0",
            "tournament": self.event_id,
            "gender": "0",
            "age[]": AGE_GROUP_IDS[age_group],
            "brackets": "",
            "groups": "",
            "group": "",
            "match_number": "0",
            "status": "all",
            "match_type": "1",
            "schedule": "0",
            "teamPlayer": "0",
            "location": "0",
            "as_referee": "0",
            "report_status": "0",
            "start_date": f"{start.isoformat()} 00:00:00",
            "end_date": f"{end.isoformat()} 23:59:59",
        }

    async def _get(
        self,
        client: httpx.AsyncClient,
        age_group: str,
        page: int,
        start: date,
        end: date,
    ) -> str:
        """GET one page: paced, retried with backoff, honouring Retry-After."""
        params = self._params(age_group, page, start, end)
        last_error = ""
        for attempt in range(self.MAX_RETRIES + 1):
            if self._requested:
                await self._sleep(self.delay + random.uniform(0, self.JITTER))
            self._requested = True
            self.requests += 1
            wait = self.RETRY_DELAY_BASE * (self.RETRY_BACKOFF_MULTIPLIER**attempt)
            try:
                response = await client.get(
                    ENDPOINT_URL, params=params, headers=HEADERS
                )
            except httpx.RequestError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            else:
                # Only a 2xx is a page. Redirects are not followed, so a 3xx
                # is a body-less answer that would parse as "no matches".
                if 200 <= response.status_code < 300:
                    return response.text
                last_error = f"HTTP {response.status_code}"
                if response.status_code not in RETRYABLE_STATUS:
                    break
                if response.status_code in RETRY_AFTER_STATUS:
                    wait = _retry_after(response, wait)
                    if wait > self.MAX_RETRY_AFTER:
                        last_error += f", Retry-After {wait:.0f}s"
                        break
            if attempt < self.MAX_RETRIES:
                await self._sleep(wait)
        raise Modular11EventError(
            f"get_matches page {page} failed for {age_group}: {last_error}"
        )

    def _count(self, what: str, count: int = 1) -> None:
        self.unmapped[what] = self.unmapped.get(what, 0) + count

    def _save(self, age_group: str, page: int, html: str) -> None:
        if self.save_raw is None:
            return
        self.save_raw.mkdir(parents=True, exist_ok=True)
        (self.save_raw / f"{age_group}_p{page:02d}.html").write_text(html)


def _retry_after(response: httpx.Response, default: float) -> float:
    """Seconds the server asked for, or ``default`` when it did not say."""
    value = response.headers.get("Retry-After", "").strip()
    return float(value) if value.isdigit() else default
