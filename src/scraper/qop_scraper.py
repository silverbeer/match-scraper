"""
MLS Next QoP (Quality of Play) standings scraper.

Fetches standings directly from the modular11 HTTP endpoint that the MLS Next
standings iframe uses internally. No browser automation required — the endpoint
returns an HTML fragment with rankings for every division in the given age
group, and we parse the target division with BeautifulSoup.
"""

from __future__ import annotations

import asyncio
import re
from datetime import date, datetime, timedelta, timezone

import httpx
from bs4 import BeautifulSoup, Tag

from ..models.qop_ranking import QoPRanking, QoPSnapshot
from ..utils.logger import get_logger

logger = get_logger()


class QoPScraperError(Exception):
    """Custom exception for QoP scraper failures."""

    pass


# Age group → modular11 UID_age value
AGE_GROUP_IDS: dict[str, str] = {
    "U13": "21",
    "U14": "22",
    "U15": "33",
    "U16": "14",
    "U17": "15",
    "U19": "26",
}

_QUALIFICATION_PATTERNS = re.compile(
    r"(Championship Qualification|Premier Qualification|Qualification|Qualified)",
    re.IGNORECASE,
)

_AGE_PREFIX = re.compile(r"^\s*U\d+\s+", re.IGNORECASE)

# The standings page sometimes lists a "<Region> (Pro Player Pathway) Division"
# alongside the plain "<Region> Division" heading. The QoP cronjob targets the
# plain geographic Homegrown divisions, so we skip Pro Player Pathway rows by
# default unless explicitly requested.
_PRO_PLAYER_PATHWAY = "(pro player pathway)"


def strip_qualification_text(raw: str) -> str:
    """Remove qualification status text from a raw team name string."""
    cleaned = _QUALIFICATION_PATTERNS.sub("", raw)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()


def _normalize_division_heading(title: str) -> str:
    """
    Reduce a ``data-title`` like "U15 Northeast Division" to "northeast".

    Keeps "(pro player pathway)" as a suffix so callers can distinguish
    geographic divisions from Pathway brackets.
    """
    t = title.strip().lower()
    t = _AGE_PREFIX.sub("", t)
    if t.endswith(" division"):
        t = t[: -len(" division")]
    return t.strip()


class MLSQoPScraper:
    """
    Scrapes MLS Next Quality-of-Play standings for a given age group and division.

    Usage::

        scraper = MLSQoPScraper(age_group="U14", division="Northeast")
        snapshot = await scraper.scrape()
    """

    ENDPOINT_URL = "https://www.modular11.com/public_schedule/league/get_teams"

    EVENT_ID = "12"  # MLS NEXT
    LIST_TYPE = "53"  # QoP standings listing

    REQUEST_TIMEOUT = 30.0
    MAX_RETRIES = 3
    RETRY_DELAY_BASE = 1.0
    RETRY_BACKOFF_MULTIPLIER = 2.0

    def __init__(
        self,
        age_group: str,
        division: str,
        headless: bool = True,  # noqa: ARG002 — kept for backwards compat with CLI
    ) -> None:
        self.age_group = age_group
        self.division = division

        if age_group not in AGE_GROUP_IDS:
            raise QoPScraperError(
                f"Unknown age group: {age_group!r}. Known: {sorted(AGE_GROUP_IDS)}"
            )

        self.age_id = AGE_GROUP_IDS[age_group]
        self._division_target = _normalize_division_heading(division)

    async def scrape(self) -> QoPSnapshot:
        """Fetch and parse standings for the configured age group and division."""
        logger.info(
            "Starting QoP standings scrape",
            extra={
                "age_group": self.age_group,
                "division": self.division,
                "age_id": self.age_id,
            },
        )

        html = await self._fetch_html()
        rankings = self._parse_rankings(html)

        if not rankings:
            raise QoPScraperError(
                f"No QoP rankings found for {self.age_group} {self.division}. "
                "The division may not expose QoP metrics (some age groups only "
                "publish standard league standings) or the page structure changed."
            )

        today = date.today()
        week_of = today - timedelta(days=today.weekday())

        logger.info(
            "QoP standings scrape completed",
            extra={
                "age_group": self.age_group,
                "division": self.division,
                "rankings_count": len(rankings),
            },
        )

        return QoPSnapshot(
            week_of=week_of,
            division=self.division,
            age_group=self.age_group,
            scraped_at=datetime.now(tz=timezone.utc),
            rankings=rankings,
        )

    async def _fetch_html(self) -> str:
        """GET the modular11 get_teams endpoint with retries."""
        params = {
            "tournament_type": "league",
            "UID_age": self.age_id,
            "UID_gender": "0",
            "UID_event": self.EVENT_ID,
            "list_type": self.LIST_TYPE,
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; mls-match-scraper/QoP)",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "text/html,*/*",
        }

        last_exc: Exception | None = None
        async with httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT) as client:
            for attempt in range(self.MAX_RETRIES):
                try:
                    resp = await client.get(
                        self.ENDPOINT_URL, params=params, headers=headers
                    )
                    resp.raise_for_status()
                    return resp.text
                except (httpx.HTTPError, httpx.RequestError) as exc:
                    last_exc = exc
                    logger.warning(
                        "QoP endpoint fetch failed",
                        extra={
                            "attempt": attempt + 1,
                            "max_retries": self.MAX_RETRIES,
                            "error": str(exc),
                            "error_type": type(exc).__name__,
                        },
                    )
                    if attempt < self.MAX_RETRIES - 1:
                        await asyncio.sleep(
                            self.RETRY_DELAY_BASE
                            * (self.RETRY_BACKOFF_MULTIPLIER**attempt)
                        )

        raise QoPScraperError(
            f"QoP endpoint fetch failed after {self.MAX_RETRIES} attempts: {last_exc}"
        ) from last_exc

    def _parse_rankings(self, html: str) -> list[QoPRanking]:
        """
        Parse the modular11 HTML fragment and extract rankings for the target division.

        The endpoint returns rows for every division in the age group. Division
        boundaries are marked by ``<p data-title="... Division">`` headings; team
        rows follow each heading until the next one. We walk the document in
        order, track the current heading, and collect rows only while the heading
        matches the target division.
        """
        soup = BeautifulSoup(html, "html.parser")
        target = self._division_target

        rankings: list[QoPRanking] = []
        current_match = False
        found_target = False
        skipped_rows = 0

        # Walk relevant elements in document order
        for el in soup.find_all(
            lambda t: (
                t.name == "p"
                and t.has_attr("data-title")
                and "division" in (t.get("data-title") or "").lower()
            )
            or (
                t.name == "div"
                and "form_row" in (t.get("class") or [])
                and "main_row" in (t.get("class") or [])
            )
        ):
            if el.name == "p":
                heading = _normalize_division_heading(el.get("data-title") or "")
                # Skip Pro Player Pathway brackets unless explicitly requested
                if _PRO_PLAYER_PATHWAY in heading and _PRO_PLAYER_PATHWAY not in target:
                    current_match = False
                    continue
                current_match = heading == target
                if current_match:
                    found_target = True
                continue

            if current_match:
                ranking = self._parse_row(el)
                if ranking is None:
                    skipped_rows += 1
                else:
                    rankings.append(ranking)

        if not found_target:
            raise QoPScraperError(
                f"Division heading for {self.division!r} not found in "
                f"{self.age_group} standings response. The division may not "
                "exist for this age group."
            )

        logger.info(
            "QoP row parsing complete",
            extra={"parsed": len(rankings), "skipped": skipped_rows},
        )

        return sorted(rankings, key=lambda r: r.rank)

    @staticmethod
    def _parse_row(row: Tag) -> QoPRanking | None:
        """
        Extract a single QoPRanking from a ``.form_row.main_row`` element.

        QoP rows have exactly 4 stat cells (``.col-sm-3.hidden-xs``) containing
        matches played, attack score, defense score, and QoP score. Age groups
        that publish traditional standings (W/L/T/GF/GA/etc.) use 9x
        ``.col-sm-1.hidden-xs`` cells instead — those rows are skipped.
        """
        try:
            rank_el = row.select_one(".container-rank")
            team_el = row.select_one(".container-team-info p[data-title]")
            stat_cells = row.select(".subrow.pad-left .col-sm-3.hidden-xs")

            if rank_el is None or team_el is None or len(stat_cells) != 4:
                return None

            rank = int(rank_el.get_text(strip=True))
            team_name = strip_qualification_text(
                team_el.get("data-title") or team_el.get_text(strip=True)
            )
            matches_played = int(stat_cells[0].get_text(strip=True))
            att_score = float(stat_cells[1].get_text(strip=True))
            def_score = float(stat_cells[2].get_text(strip=True))
            qop_score = float(stat_cells[3].get_text(strip=True))

            return QoPRanking(
                rank=rank,
                team_name=team_name,
                matches_played=matches_played,
                att_score=att_score,
                def_score=def_score,
                qop_score=qop_score,
            )
        except (ValueError, AttributeError) as exc:
            logger.debug(
                "Skipping unparseable QoP row",
                extra={"error": str(exc)},
            )
            return None
