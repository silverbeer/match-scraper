"""
Watch the MLS NEXT Fest pages for the schedule being published (SB-1774).

Fest 2026 runs 2-13 December. Until the schedule is out, ``scrape-event`` has
no event id to read and the ``k3s/fest`` CronJobs stay suspended, so the only
useful thing to do is notice the moment it lands.

Both sites are server-rendered: a plain GET returns the content a browser
shows, so this needs no Playwright. What each page looks like while waiting,
checked by hand on 2026-11-25:

* ``matchcenter.mlsnextpro.com/mlsnext/tournaments/fest/`` and
  ``www.mlssoccer.com/mlsnext/tournaments/fest/`` — the same Fest landing page
  on two hosts. Its "Fest Schedule & Standings" promo
  (``#mlsnext-fest-schedule-standings``) links to ``/fest/temp``: a
  placeholder. Released means that link points somewhere else, and where it
  points is the most useful thing to report, because it probably carries the
  event id ``scrape-event`` needs.
* ``www.mlssoccer.com/mlsnext/tournaments/fest/temp`` — the placeholder
  itself, whose whole body is the words "Coming Soon". Released means that
  text is gone.

A page that cannot be read is an error, never a release. That covers a
non-200, a redirect away from the page, a block page without the Fest title,
and a page that has lost the element we read. Without that rule, the first
time a CDN served a challenge page the watcher would announce a release.

``temp`` is in the URL for a reason and may disappear, and either landing page
may be rebuilt; that is why three pages are probed. One page failing is fine, and the caller
only treats the probe as failed when every page failed.

The schedule may also land on modular11 before those pages link to it
(SB-1830). Fest 2025 was modular11 event ``75``; the 2026 id is unknown, so
the next ids are each asked for U15 matches inside the Fest dates. An event
with matches is a release, reported with its schedule page; the endpoint's
own "No data available." is waiting; anything else is an error.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from enum import Enum
from urllib.parse import urljoin, urlparse

import httpx
import structlog
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from .tournament.modular11_event import Modular11EventSource

logger = structlog.get_logger()


class PageKind(str, Enum):
    """How a page shows that the schedule is not out yet."""

    COMING_SOON = "coming_soon"
    SCHEDULE_PROMO = "schedule_promo"


class FestPageState(str, Enum):
    WAITING = "waiting"
    RELEASED = "released"
    ERROR = "error"


class FestPage(BaseModel):
    """One page to watch."""

    name: str = Field(..., description="Short label used in logs and messages")
    url: str = Field(..., description="Page URL")
    kind: PageKind = Field(..., description="Which waiting signal the page carries")


FEST_PAGES: tuple[FestPage, ...] = (
    FestPage(
        name="matchcenter",
        url="https://matchcenter.mlsnextpro.com/mlsnext/tournaments/fest/",
        kind=PageKind.SCHEDULE_PROMO,
    ),
    FestPage(
        name="mlssoccer",
        url="https://www.mlssoccer.com/mlsnext/tournaments/fest/",
        kind=PageKind.SCHEDULE_PROMO,
    ),
    FestPage(
        name="fest-temp",
        url="https://www.mlssoccer.com/mlsnext/tournaments/fest/temp",
        kind=PageKind.COMING_SOON,
    ),
)

# modular11 event ids that might be Fest 2026 (SB-1830). 2025 was 75, and on
# 2026-11-28 76-82 held no Fest-dated matches.
M11_EVENT_IDS: tuple[int, ...] = tuple(range(76, 91))
# One age group is enough to see a schedule go up: they publish together, and
# U15 is the one we care about most.
M11_AGE_GROUP = "U15"
FEST_START = date(2026, 12, 2)
FEST_END = date(2026, 12, 13)
M11_SCHEDULE_URL = "https://www.modular11.com/events/event/iframe/schedule/{}"

# Every real Fest page has this in its <title>; a block or error page does not.
FEST_TITLE = "mls next fest"
COMING_SOON_TEXT = "coming soon"
SCHEDULE_PROMO_ID = "mlsnext-fest-schedule-standings"
# Where the schedule promo points while there is no schedule.
PLACEHOLDER_PATH = "/mlsnext/tournaments/fest/temp"

HEADERS = {
    # The sites serve the same HTML to any browser-like agent.
    "User-Agent": "Mozilla/5.0 (compatible; mls-match-scraper/fest-watch)",
    "Accept": "text/html,*/*",
}


class FestPageResult(BaseModel):
    """What one page said on one probe."""

    name: str
    url: str
    state: FestPageState
    detail: str = Field(
        default="",
        description="The schedule link when released, the reason when an error",
    )


class FestProbe(BaseModel):
    """One pass over every Fest page."""

    checked_at: datetime
    results: list[FestPageResult] = Field(default_factory=list)

    @property
    def released(self) -> list[FestPageResult]:
        return [r for r in self.results if r.state is FestPageState.RELEASED]

    @property
    def errors(self) -> list[FestPageResult]:
        return [r for r in self.results if r.state is FestPageState.ERROR]

    @property
    def all_failed(self) -> bool:
        return bool(self.results) and len(self.errors) == len(self.results)

    def summary(self) -> str:
        parts = [f"{r.name}={r.state.value}" for r in self.results]
        return "fest: " + ", ".join(parts)


def classify_page(
    page: FestPage, status: int, final_url: str, html: str
) -> FestPageResult:
    """Decide what a fetched page says. Pure, so it is tested without a network."""

    def result(state: FestPageState, detail: str = "") -> FestPageResult:
        return FestPageResult(name=page.name, url=page.url, state=state, detail=detail)

    if status != 200:
        return result(FestPageState.ERROR, f"HTTP {status}")
    if _path(final_url) != _path(page.url):
        return result(FestPageState.ERROR, f"redirected to {final_url}")

    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True).lower() if soup.title else ""
    if FEST_TITLE not in title:
        return result(FestPageState.ERROR, f"not a Fest page (title {title!r})")

    if page.kind is PageKind.COMING_SOON:
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = " ".join(soup.get_text(" ").split()).lower()
        if COMING_SOON_TEXT in text:
            return result(FestPageState.WAITING)
        return result(FestPageState.RELEASED, page.url)

    promo = soup.find(id=SCHEDULE_PROMO_ID)
    if promo is None:
        return result(FestPageState.ERROR, f"no #{SCHEDULE_PROMO_ID} on the page")
    link = promo.find("a", href=True)
    if link is None:
        return result(FestPageState.ERROR, "schedule promo has no link")
    href = urljoin(final_url, str(link["href"]))
    if _path(href) == _path(PLACEHOLDER_PATH):
        return result(FestPageState.WAITING)
    return result(FestPageState.RELEASED, href)


def _path(url: str) -> str:
    """Host-independent, slash-insensitive path, for comparing URLs."""
    return urlparse(url).path.rstrip("/").lower()


class FestWatcher:
    """Fetches every Fest page and classifies it."""

    REQUEST_TIMEOUT = 20.0

    def __init__(
        self,
        pages: tuple[FestPage, ...] = FEST_PAGES,
        transport: httpx.AsyncBaseTransport | None = None,
        m11_events: tuple[int, ...] = M11_EVENT_IDS,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.pages = pages
        self.m11_events = m11_events
        self._transport = transport  # tests inject httpx.MockTransport
        self._sleep = sleep  # and a no-op sleep, so retries are instant

    async def probe(self) -> FestProbe:
        async with httpx.AsyncClient(
            timeout=self.REQUEST_TIMEOUT,
            headers=HEADERS,
            follow_redirects=True,
            transport=self._transport,
        ) as client:
            results = list(
                await asyncio.gather(
                    *(self._probe_page(client, page) for page in self.pages)
                )
            )
        results += await self._probe_m11_events()
        probe = FestProbe(checked_at=datetime.now(tz=UTC), results=results)
        logger.info(
            "fest_watch.probe",
            released=[r.name for r in probe.released],
            errors={r.name: r.detail for r in probe.errors},
        )
        return probe

    async def _probe_page(
        self, client: httpx.AsyncClient, page: FestPage
    ) -> FestPageResult:
        try:
            response = await client.get(page.url)
        except httpx.HTTPError as exc:
            return FestPageResult(
                name=page.name,
                url=page.url,
                state=FestPageState.ERROR,
                detail=f"{type(exc).__name__}: {exc}",
            )
        return classify_page(
            page, response.status_code, str(response.url), response.text
        )

    async def _probe_m11_events(self) -> list[FestPageResult]:
        """Ask each candidate modular11 event for Fest-dated U15 matches.

        One at a time over one client, so fifteen ids are fifteen polite
        requests, not a burst. The reader does not follow redirects, so a
        redirect is an error rather than an empty event.
        """
        if not self.m11_events:
            return []
        results: list[FestPageResult] = []
        async with httpx.AsyncClient(
            timeout=Modular11EventSource.REQUEST_TIMEOUT, transport=self._transport
        ) as client:
            for event_id in self.m11_events:
                results.append(await self._probe_m11_event(client, event_id))
        return results

    async def _probe_m11_event(
        self, client: httpx.AsyncClient, event_id: int
    ) -> FestPageResult:
        url = M11_SCHEDULE_URL.format(event_id)
        reader = Modular11EventSource(
            str(event_id), delay=0.0, client=client, sleep=self._sleep
        )

        def result(state: FestPageState, detail: str = "") -> FestPageResult:
            return FestPageResult(
                name=f"modular11-{event_id}", url=url, state=state, detail=detail
            )

        try:
            matches = await reader.fetch([M11_AGE_GROUP], FEST_START, FEST_END)
        except Exception as exc:  # a parser surprise is an error, never a release
            return result(FestPageState.ERROR, f"{type(exc).__name__}: {exc}")
        if reader.failures:
            return result(FestPageState.ERROR, reader.failures[M11_AGE_GROUP])
        if matches:
            return result(FestPageState.RELEASED, url)
        return result(FestPageState.WAITING)
