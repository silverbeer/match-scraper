#!/usr/bin/env python3
"""
Capture trimmed parser fixtures from a modular11 event. Manual; uses the network.

Never imported by tests: the default suite reads only what this wrote under
``tests/unit/fixtures/modular11_event_75/``.

    uv run python scripts/capture_event_fixtures.py --raw /tmp/event75-raw

``--raw`` is a directory of whole pages named ``<AGE>_p<NN>.html`` — exactly
what ``match-scraper-agent scrape-event --save-raw`` leaves behind, so a dry
run's pages can be reused. Whatever is missing from it is fetched, one request
at a time and at least a second apart: every page of every age group (about a
hundred requests) from an empty directory, two requests (the page past the end
and an empty window) from a complete one.

It writes:

* three fixtures of chosen rows, one per age group — :data:`CHOSEN_ROWS`;
* the last page of one age group, and the page after it — which the endpoint
  answers with ``No data available.``;
* the ``No data available.`` body for a window with no matches;
* ``census.json`` — every (age, competition, division, label) combination in
  the event with its count, which the mapping test checks against.

Each kept row is the page's own ``.container-row`` with ``style`` attributes
and comments removed, whitespace collapsed, and the mobile block reduced to
the one element the parser reads from it (``.place-info``, the round label).
``synthetic_rows.html`` in the same directory is hand-written and is not
touched by this script.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import httpx
from bs4 import BeautifulSoup, Comment, Tag

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.models.tournament import TournamentMatch  # noqa: E402
from src.scraper.modular11 import AGE_GROUP_IDS  # noqa: E402
from src.scraper.tournament.modular11_event import (  # noqa: E402
    MATCH_ROW_SELECTOR,
    PAGINATOR_SELECTOR,
    ROUND_LABEL_SELECTOR,
    ROW_CONTAINER_CLASS,
    Modular11EventSource,
    parse_page,
)

FIXTURE_DIR = REPO_ROOT / "tests/unit/fixtures/modular11_event_75"

# MLS NEXT Fest 2025.
EVENT_ID = "75"
WINDOW = (date(2025, 8, 1), date(2026, 7, 15))
# Inside the season the endpoint serves, before the event: no matches.
EMPTY_WINDOW = (date(2025, 9, 1), date(2025, 9, 2))

# Fixture file -> (age group, match ids to keep). Chosen to cover every shape
# of row the event has; see tests/unit/test_modular11_event.py for what each
# is there to prove.
CHOSEN_ROWS: dict[str, tuple[str, tuple[str, ...]]] = {
    "u13_group_play.html": (
        "U13",
        (
            "16044",  # HD Group Play, group E
            "16147",  # HD Group Play, group B, level and decided on penalties
            "16263",  # AD Group Play, group G, penalties
            "16071",  # HD Group Play / Playoffs / Final
            "16080",  # AD Group Play / Playoffs / Final
            "16129",  # AD Group Play / Playoffs / Consolation
            "17228",  # never scored: the cell reads TBD
        ),
    ),
    "u15_ga_cup.html": (
        "U15",
        (
            "16423",  # Round of 32
            "16416",  # Round of 16, penalties
            "16412",  # QuarterFinal, penalties
            "16439",  # Semi-Final, 0:0 then 1:0 on penalties
            "16401",  # Final, penalties
            "16402",  # NEXT Pro group match
            "16407",  # NEXT Pro group match, penalties
            "16409",  # Final (Child Group of NEXT Pro)
            "16362",  # division Consolation
            "16460",  # AD Showcase, division FEST
            "16446",  # HD Showcase, division FEST
            "18526",  # blank round label
        ),
    ),
    "u19_showcase.html": (
        "U19",
        (
            "17042",  # HD Showcase, a 0:0 draw with no shootout
            "18240",  # AD Showcase
            "16992",  # Pro Player Pathway
            "18237",  # Best Of
            "18531",  # TBD v TBD at midnight: teams and time not set
        ),
    ),
}

# The age group whose last page and page-past-the-end are kept whole.
LAST_PAGE_AGE = "U13"

# ASCII whitespace only: \s would also swallow the non-breaking space the
# score cell is written with.
_SPACE = re.compile(r"[ \t\r\n\f]+")


def _pages(raw: Path, age_group: str) -> list[Path]:
    return sorted(raw.glob(f"{age_group}_p[0-9][0-9].html"))


async def fetch_missing(raw: Path) -> int:
    """Fetch whatever ``raw`` lacks. Returns the number of requests made."""
    source = Modular11EventSource(EVENT_ID, delay=1.0, save_raw=raw)
    missing = [age for age in AGE_GROUP_IDS if not _pages(raw, age)]
    if missing:
        print(f"fetching every page for {', '.join(missing)}", file=sys.stderr)
        await source.fetch(missing, *WINDOW)
        for age, reason in source.failures.items():
            raise SystemExit(f"{age} failed: {reason}")

    async with httpx.AsyncClient(timeout=source.REQUEST_TIMEOUT) as client:
        past_end = raw / f"{LAST_PAGE_AGE}_past_end.html"
        if not past_end.exists():
            page = len(_pages(raw, LAST_PAGE_AGE)) + 1
            print(
                f"fetching {LAST_PAGE_AGE} page {page} (past the end)", file=sys.stderr
            )
            past_end.write_text(await source._get(client, LAST_PAGE_AGE, page, *WINDOW))
        no_data = raw / "no_data.html"
        if not no_data.exists():
            print("fetching an empty window", file=sys.stderr)
            no_data.write_text(
                await source._get(client, LAST_PAGE_AGE, 1, *EMPTY_WINDOW)
            )
    return source.requests


def trim_row(container: Tag) -> str:
    """One ``.container-row``, reduced to what the parser reads."""
    soup = BeautifulSoup(str(container), "html.parser")
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()
    for tag in soup.find_all(True):
        tag.attrs.pop("style", None)
    label = soup.select_one(ROUND_LABEL_SELECTOR)
    mobile = soup.select_one(".visible-xs")
    if mobile is not None and label is not None:
        mobile.clear()
        mobile.append(label)
    return _serialise(soup)


def _serialise(node: Tag | BeautifulSoup) -> str:
    text = _SPACE.sub(" ", str(node)).replace("> <", ">\n<").strip()
    # Put the score cell back as the endpoint writes it: "4&nbsp:&nbsp1", no
    # semicolons. A parser decodes the first entity and not the second, and
    # the fixture must make the parser deal with that, as the live page does.
    return text.replace("&amp;nbsp", "&nbsp").replace("\xa0", "&nbsp")


def build_fixture(rows: list[Tag], paginator: Tag | None, about: str) -> str:
    parts = [
        f"<!-- {about} -->",
        '<div class="container-fluid container-table-matches">',
        '<div class="container-table-content table-content-public">',
        *[trim_row(row) for row in rows],
        "</div>",
        "</div>",
    ]
    if paginator is not None:
        parts.append(f"<div js-paginator>\n{_serialise(paginator)}\n</div>")
    return "\n".join(parts) + "\n"


def _containers(html: str) -> tuple[dict[str, Tag], Tag | None]:
    """Match id -> its ``.container-row``, and the page's paginator."""
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, Tag] = {}
    for row in soup.select(MATCH_ROW_SELECTOR):
        container = row.find_parent(class_=ROW_CONTAINER_CLASS)
        match_id = row.select_one(".col-sm-1")
        if container is not None and match_id is not None:
            found[match_id.get_text().split()[0]] = container
    return found, soup.select_one(PAGINATOR_SELECTOR)


def _same(left: list[TournamentMatch], right: list[TournamentMatch]) -> bool:
    return [m.model_dump() for m in left] == [m.model_dump() for m in right]


def write_chosen(raw: Path, header: str) -> None:
    for name, (age_group, wanted) in CHOSEN_ROWS.items():
        rows: dict[str, Tag] = {}
        originals: dict[str, TournamentMatch] = {}
        paginator: Tag | None = None
        for page in _pages(raw, age_group):
            html = page.read_text()
            containers, page_paginator = _containers(html)
            hits = [match_id for match_id in wanted if match_id in containers]
            if hits and paginator is None:
                paginator = page_paginator
            rows.update({match_id: containers[match_id] for match_id in hits})
            originals.update(
                {
                    m.source_match_id: m
                    for m in parse_page(html, age_group).matches
                    if m.source_match_id in wanted
                }
            )
        absent = [match_id for match_id in wanted if match_id not in rows]
        if absent:
            raise SystemExit(f"{name}: match ids not in the event: {absent}")
        fixture = build_fixture(
            [rows[match_id] for match_id in wanted],
            paginator,
            f"{header} {age_group}, chosen rows. Trimmed; see "
            "scripts/capture_event_fixtures.py.",
        )
        # Trimming must not change what the parser reads.
        if not _same(
            parse_page(fixture, age_group).matches,
            [originals[match_id] for match_id in wanted],
        ):
            raise SystemExit(f"{name}: trimmed rows parse differently")
        (FIXTURE_DIR / name).write_text(fixture)
        print(f"{name}: {len(wanted)} rows, {len(fixture):,} bytes")


def write_whole_page(source: Path, name: str, about: str) -> None:
    html = source.read_text()
    containers, paginator = _containers(html)
    fixture = build_fixture(list(containers.values()), paginator, about)
    if not _same(
        parse_page(fixture, LAST_PAGE_AGE).matches,
        parse_page(html, LAST_PAGE_AGE).matches,
    ):
        raise SystemExit(f"{name}: trimmed page parses differently")
    (FIXTURE_DIR / name).write_text(fixture)
    print(f"{name}: {len(containers)} rows, {len(fixture):,} bytes")


def write_body(source: Path, name: str, about: str) -> None:
    """A page with no matches on it, kept whole."""
    html = source.read_text()
    if parse_page(html, LAST_PAGE_AGE).matches:
        raise SystemExit(f"{name}: expected a page with no matches")
    (FIXTURE_DIR / name).write_text(
        f"<!-- {about} -->\n" + _SPACE.sub(" ", html).strip() + "\n"
    )
    print(f"{name}: {len(html):,} bytes as fetched")


def write_census(raw: Path, header: str) -> None:
    """Every (age, competition, division, label) in the event, with counts."""
    counts: Counter[tuple[str, str, str, str]] = Counter()
    totals: Counter[str] = Counter()
    for age_group in AGE_GROUP_IDS:
        seen: set[str] = set()
        for page in _pages(raw, age_group):
            for match in parse_page(page.read_text(), age_group).matches:
                if match.source_match_id in seen:
                    continue
                seen.add(match.source_match_id)
                totals[match.age_group] += 1
                counts[
                    (
                        match.age_group,
                        match.competition or "",
                        match.source_division or "",
                        match.mapped().label,
                    )
                ] += 1
    census = {
        "about": f"{header} every combination of age group, competition, "
        "division and cleaned round label, with the number of matches "
        "carrying it. Written by scripts/capture_event_fixtures.py.",
        "event": EVENT_ID,
        "matches": sum(totals.values()),
        "matches_by_age_group": dict(sorted(totals.items())),
        "combinations": [
            {
                "age_group": age,
                "competition": competition,
                "division": division,
                "label": label,
                "matches": count,
            }
            for (age, competition, division, label), count in sorted(counts.items())
        ],
    }
    (FIXTURE_DIR / "census.json").write_text(json.dumps(census, indent=1) + "\n")
    print(f"census.json: {len(counts)} combinations, {census['matches']} matches")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--raw",
        type=Path,
        required=True,
        help="Directory of whole pages (<AGE>_p<NN>.html); missing ones are fetched",
    )
    parser.add_argument(
        "--captured",
        default=date.today().isoformat(),
        help="Capture date written into the fixtures (default: today)",
    )
    args = parser.parse_args()

    args.raw.mkdir(parents=True, exist_ok=True)
    requests = asyncio.run(fetch_missing(args.raw))
    print(f"requests made: {requests}", file=sys.stderr)

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    header = (
        f"modular11 event {EVENT_ID} (MLS NEXT Fest 2025), captured {args.captured}:"
    )
    write_chosen(args.raw, header)
    last = _pages(args.raw, LAST_PAGE_AGE)[-1]
    write_whole_page(
        last,
        "u13_last_page.html",
        f"{header} {LAST_PAGE_AGE} page {len(_pages(args.raw, LAST_PAGE_AGE))}, the "
        "last one, every row. Trimmed.",
    )
    write_body(
        args.raw / f"{LAST_PAGE_AGE}_past_end.html",
        "u13_past_end.html",
        f"{header} {LAST_PAGE_AGE} page {len(_pages(args.raw, LAST_PAGE_AGE)) + 1}, "
        "one past the end. Whole body.",
    )
    write_body(
        args.raw / "no_data.html",
        "no_data.html",
        f"{header} a window with no matches. Whole body.",
    )
    write_census(args.raw, header)


if __name__ == "__main__":
    main()
