"""The modular11 event source: parsing and pagination (SB-1746).

Parsing runs on rows saved from event 75 (MLS NEXT Fest 2025) by
``scripts/capture_event_fixtures.py``; nothing here touches the network.
"""

from datetime import date, datetime
from pathlib import Path

import httpx
import pytest

from src.scraper.tournament import modular11_event
from src.scraper.tournament.modular11_event import (
    ENDPOINT_URL,
    Modular11EventSource,
    parse_kickoff,
    parse_page,
    parse_score,
    unreadable_score,
)

pytestmark = pytest.mark.usefixtures("no_network")

FIXTURES = Path(__file__).parent / "fixtures/modular11_event_75"
START, END = date(2025, 8, 1), date(2026, 7, 15)


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def _by_id(name: str, age_group: str = "U15"):
    return {m.source_match_id: m for m in parse_page(_fixture(name), age_group).matches}


def test_this_module_cannot_reach_the_network():
    import socket

    with pytest.raises(AssertionError, match="network connection"):
        socket.create_connection(("127.0.0.1", 9), timeout=0.1)


class TestParseScore:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("4\xa0:&nbsp1", (4, 1, None, None)),  # as the parser hands it over
            ("4&nbsp:&nbsp1", (4, 1, None, None)),
            ("4&nbsp;:&nbsp;1", (4, 1, None, None)),
            ("  2 : 2  ", (2, 2, None, None)),
            ("10:0", (10, 0, None, None)),
            ("0\xa0:&nbsp0 (1\xa0:&nbsp3)", (0, 0, 1, 3)),
            ("1 : 1 (4 : 3)", (1, 1, 4, 3)),
            # Penalties need a level score, and 0:0 is "no shootout".
            ("2 : 1 (4 : 3)", (2, 1, None, None)),
            ("1 : 1 (0 : 0)", (1, 1, None, None)),
        ],
    )
    def test_results(self, text, expected):
        assert parse_score(text) == expected

    @pytest.mark.parametrize("text", ["TBD", "", None, "-", "vs", "2 :", "PPD", "1-0"])
    def test_anything_else_is_no_score(self, text):
        assert parse_score(text) == (None, None, None, None)


class TestParseKickoff:
    def test_venue_wall_clock(self):
        assert parse_kickoff("12/12/25 08:00am") == datetime(2025, 12, 12, 8, 0)
        assert parse_kickoff("12/13/25 08:20pm 9 - Field") == datetime(
            2025, 12, 13, 20, 20
        )
        assert parse_kickoff("12/04/25 12:00am") == datetime(2025, 12, 4)
        assert parse_kickoff("12/04/25 12:30PM") == datetime(2025, 12, 4, 12, 30)

    def test_a_four_digit_year(self):
        assert parse_kickoff("12/12/2026 08:00am") == datetime(2026, 12, 12, 8, 0)
        assert parse_kickoff("12/12/2026") == datetime(2026, 12, 12)
        assert parse_kickoff("1/5/26 9:05am") == datetime(2026, 1, 5, 9, 5)

    @pytest.mark.parametrize(
        "text", ["12/12/20261 08:00am", "12/12/202 08:00am", "112/12/26 08:00am"]
    )
    def test_extra_digits_are_not_a_date(self, text):
        assert parse_kickoff(text) is None

    def test_a_bare_date_is_midnight(self):
        assert parse_kickoff("12/04/25") == datetime(2025, 12, 4)

    @pytest.mark.parametrize("text", ["", None, "TBD", "13/45/25 08:00am"])
    def test_unreadable(self, text):
        assert parse_kickoff(text) is None


class TestUnreadableScore:
    @pytest.mark.parametrize(
        "text", ["TBD", "tbd", "", None, "4&nbsp:&nbsp1", "1 : 1 (4 : 3)"]
    )
    def test_a_score_tbd_or_blank_is_understood(self, text):
        assert unreadable_score(text) is None

    @pytest.mark.parametrize("text", ["1 : 1 (4 : 3) FF", "PPD", "-", "1-0", "2 :"])
    def test_anything_else_is_reported(self, text):
        assert unreadable_score(text) == text

    def test_the_page_counts_them(self):
        html = _fixture("u13_last_page.html").replace(
            "1&nbsp:&nbsp3", "1&nbsp:&nbsp3 FF", 1
        )
        parsed = parse_page(html, "U13")
        assert parsed.unread_scores == {"1 : 3 FF": 1}
        assert len(parsed.matches) == 6

    def test_the_real_event_has_none(self):
        for name in ("u13_group_play", "u15_ga_cup", "u19_showcase", "u13_last_page"):
            assert parse_page(_fixture(f"{name}.html"), "U13").unread_scores == {}


class TestParseRows:
    def test_the_match_id_is_the_first_cell_not_the_game_attribute(self):
        parsed = parse_page(_fixture("u15_ga_cup.html"), "U15")
        assert [m.source_match_id for m in parsed.matches] == [
            "16423",
            "16416",
            "16412",
            "16439",
            "16401",
            "16402",
            "16407",
            "16409",
            "16362",
            "16460",
            "16446",
            "18526",
        ]
        assert parsed.skipped == 0
        assert (parsed.page, parsed.total_pages) == (1, 15)

    def test_a_row_in_full(self):
        match = _by_id("u15_ga_cup.html")["16416"]
        assert match.model_dump() == {
            "source_match_id": "16416",
            "age_group": "U15",
            "home_team": "Miami Futbol Academy Rush",
            "away_team": "The Football Academy",
            "kickoff_local": datetime(2025, 12, 12, 18, 0),
            "kickoff_utc": None,
            "location": "12 - Arizona Athletic Grounds",
            "home_score": 1,
            "away_score": 1,
            "home_penalty_score": 4,
            "away_penalty_score": 3,
            "competition": "GA Cup Qualifier",
            "source_division": "Playoff",
            "source_round_label": "Round of 16",
            "bracket_position": None,
        }

    def test_team_names_are_raw(self):
        match = _by_id("u15_ga_cup.html")["16439"]
        assert match.home_team == "Intercontinental Football Academy of New England"

    def test_competition_division_and_label_are_raw(self):
        rows = _by_id("u15_ga_cup.html")
        triples = {
            match_id: (m.competition, m.source_division, m.source_round_label)
            for match_id, m in rows.items()
        }
        assert triples == {
            "16423": ("GA Cup Qualifier", "Playoff", "Round of 32"),
            "16416": ("GA Cup Qualifier", "Playoff", "Round of 16"),
            "16412": ("GA Cup Qualifier", "Playoff", "QuarterFinal"),
            "16439": ("GA Cup Qualifier", "Playoff", "Semi-Final"),
            "16401": ("GA Cup Qualifier", "Playoff", "Final"),
            "16402": ("GA Cup Qualifier", "NEXT Pro", "Group Play"),
            "16407": ("GA Cup Qualifier", "NEXT Pro", "Group Play"),
            "16409": ("GA Cup Qualifier", "Finals", "Final (Child Group of NEXT Pro)"),
            "16362": ("GA Cup Qualifier", "Consolation", "Consolation"),
            "16460": ("AD Showcase", "FEST", "Showcase"),
            "16446": ("HD Showcase", "FEST", "Showcase"),
            "18526": ("AD Showcase", "FEST", None),  # blank label
        }

    def test_scores_and_penalties(self):
        rows = _by_id("u15_ga_cup.html")
        scores = {
            match_id: (
                m.home_score,
                m.away_score,
                m.home_penalty_score,
                m.away_penalty_score,
            )
            for match_id, m in rows.items()
        }
        assert scores["16423"] == (4, 1, None, None)
        assert scores["16412"] == (2, 2, 5, 6)
        assert scores["16439"] == (0, 0, 1, 0)
        assert scores["16401"] == (0, 0, 3, 4)
        assert scores["16407"] == (0, 0, 1, 3)

    def test_a_draw_with_no_shootout_has_no_penalties(self):
        match = _by_id("u19_showcase.html", "U19")["17042"]
        assert (match.home_score, match.away_score) == (0, 0)
        assert match.home_penalty_score is None

    def test_group_rows_and_their_playoffs(self):
        rows = _by_id("u13_group_play.html", "U13")
        assert {
            match_id: (m.competition, m.source_division, m.source_round_label)
            for match_id, m in rows.items()
        } == {
            "16044": ("HD Group Play", "E", "Group Play"),
            "16147": ("HD Group Play", "B", "Group Play"),
            "16263": ("AD Group Play", "G", "Group Play"),
            "16071": ("HD Group Play", "Playoffs", "Final"),
            "16080": ("AD Group Play", "Playoffs", "Final"),
            "16129": ("AD Group Play", "Playoffs", "Consolation"),
            "17228": ("AD Group Play", "Playoffs", "Consolation"),
        }
        assert rows["16147"].home_penalty_score == 2
        assert rows["16147"].away_penalty_score == 0

    def test_a_tbd_score_cell_is_no_score(self):
        match = _by_id("u13_group_play.html", "U13")["17228"]
        assert match.home_score is None
        assert match.away_score is None

    def test_the_age_group_is_the_rows_own(self):
        # Asked for U13, but the rows say U19.
        parsed = parse_page(_fixture("u19_showcase.html"), "U13")
        assert {m.age_group for m in parsed.matches} == {"U19"}

    def test_a_fixture_with_no_teams_or_time_yet(self):
        match = _by_id("u19_showcase.html", "U19")["18531"]
        assert (match.home_team, match.away_team) == ("TBD", "TBD")
        assert match.kickoff_local == datetime(2025, 12, 4)
        assert not match.teams_known()

    def test_other_competitions(self):
        rows = _by_id("u19_showcase.html", "U19")
        assert rows["16992"].competition == "Pro Player Pathway"
        assert rows["16992"].source_round_label == "League (Pro Player Pathway)"
        assert rows["18237"].competition == "Best Of"
        assert {m.source_division for m in rows.values()} == {"FEST"}

    def test_no_data_is_no_matches(self):
        for name in ("no_data.html", "u13_past_end.html"):
            parsed = parse_page(_fixture(name), "U13")
            assert parsed.matches == []
            assert parsed.total_pages is None
            assert parsed.skipped == 0
            assert parsed.no_data
        assert not parse_page(_fixture("u13_last_page.html"), "U13").no_data
        assert not parse_page(
            "<html><body>Checking your browser</body></html>", "U13"
        ).no_data

    def test_the_last_page_says_it_is_the_last(self):
        parsed = parse_page(_fixture("u13_last_page.html"), "U13")
        assert len(parsed.matches) == 6
        assert (parsed.page, parsed.total_pages) == (15, 15)

    def test_synthetic_unplayed_row(self):
        match = _by_id("synthetic_rows.html", "U13")["90001"]
        assert match.kickoff_local == datetime(2026, 12, 5, 9, 30)
        assert match.home_score is None
        assert match.source_round_label == "Group Play"

    def test_synthetic_address_prefixed_label_maps_to_its_round(self):
        match = _by_id("synthetic_rows.html", "U13")["90002"]
        assert match.source_round_label.endswith("Round of 16")
        assert match.source_round_label != "Round of 16"
        assert match.mapped().label == "Round of 16"
        assert match.mapped().round_key == "round_of_16"
        assert (match.home_penalty_score, match.away_penalty_score) == (5, 4)

    def test_a_row_missing_its_teams_is_skipped_not_fatal(self):
        html = _fixture("u13_last_page.html").replace(
            '<p data-title="Achilles FC">Achilles FC</p>', "<p></p>"
        )
        parsed = parse_page(html, "U13")
        assert len(parsed.matches) == 5
        assert parsed.skipped == 1


# ---------------------------------------------------------------------------
# Pagination, with the network mocked at the transport layer
# ---------------------------------------------------------------------------

ROW = """
<div class="container-row">
 <div class="row table-content-row hidden-xs" js-match-group="A"
      js-match-round="0" js-match-game="1" js-match-bracket="HD Group Play">
  <div class="col-sm-1 pad-0"> {match_id} <br> MALE </div>
  <div class="col-sm-2"> 12/05/25 09:00am
   <div class="container-location"><p>1 - Field</p></div></div>
  <div class="col-sm-1 pad-0"> {age} </div>
  <div class="col-sm-2"> HD Group Play <br> A </div>
  <div class="col-sm-6 pad-0"><div class="row container-teams-info">
   <div class="col-sm-3 container-first-team"><p>Home {match_id}</p></div>
   <div class="col-sm-2 container-score"><span class="score-match-table">
    1&nbsp:&nbsp0 </span></div>
   <div class="col-sm-3 container-second-team"><p>Away {match_id}</p></div>
  </div></div>
 </div>
 <div class="visible-xs"><div class="place-info"> Group Play </div></div>
</div>
"""
PAGINATOR = (
    '<div js-paginator><div class="current-pages"> {page} page out of {total} '
    "</div></div>"
)
NO_DATA = _fixture("no_data.html")


def _page(ids, page=None, total=None, age="U13") -> str:
    html = "".join(ROW.format(match_id=i, age=age) for i in ids)
    if total is not None:
        html += PAGINATOR.format(page=page, total=total)
    return html


class _Server:
    """Answers get_matches from a table of pages, and records what was asked."""

    def __init__(self, pages: dict[tuple[str, int], object], default=NO_DATA):
        self.pages = pages
        self.default = default
        self.requests: list[httpx.Request] = []
        self.calls: list[tuple[str, int]] = []
        self.sleeps: list[float] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        params = request.url.params
        age_id = params["age[]"]
        key = (age_id, int(params["open_page"]))
        self.calls.append(key)
        answer = self.pages.get(key, self.default)
        if isinstance(answer, list):
            answer = answer.pop(0) if len(answer) > 1 else answer[0]
        if isinstance(answer, httpx.Response):
            return answer
        if isinstance(answer, Exception):
            raise answer
        return httpx.Response(200, text=answer)

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)

    def source(self, **kwargs) -> Modular11EventSource:
        return Modular11EventSource(
            "75",
            client=httpx.AsyncClient(transport=httpx.MockTransport(self.handler)),
            sleep=self.sleep,
            **kwargs,
        )


# modular11's age[] values.
U13, U14 = "21", "22"


@pytest.fixture(autouse=True)
def _no_jitter(monkeypatch):
    monkeypatch.setattr(modular11_event.random, "uniform", lambda a, b: 0.0)


class TestPagination:
    async def test_reads_page_one_through_the_last_and_stops(self):
        server = _Server(
            {
                (U13, 1): _page(["1", "2"], 1, 3),
                (U13, 2): _page(["3", "4"], 2, 3),
                (U13, 3): _page(["5"], 3, 3),
            }
        )
        source = server.source()

        matches = await source.fetch(["U13"], START, END)

        assert [m.source_match_id for m in matches] == ["1", "2", "3", "4", "5"]
        # 1-based: page 0 would have been page 1 again. Nothing past the last.
        assert server.calls == [(U13, 1), (U13, 2), (U13, 3)]
        assert source.failures == {}
        assert source.requests == 3

    async def test_the_request_is_the_event_endpoint(self):
        server = _Server({(U13, 1): _page(["1"], 1, 1)})
        await server.source().fetch(["U13"], START, END)

        request = server.requests[0]
        params = request.url.params
        assert str(request.url).startswith(ENDPOINT_URL)
        assert params["tournament"] == "75"
        assert params["match_type"] == "1"
        assert params["groups"] == ""
        assert params["status"] == "all"
        assert params["start_date"] == "2025-08-01 00:00:00"
        assert params["end_date"] == "2026-07-15 23:59:59"
        assert request.headers["X-Requested-With"] == "XMLHttpRequest"
        assert "mls-match-scraper" in request.headers["User-Agent"]

    async def test_the_real_last_page_then_stops(self):
        server = _Server(
            {
                (U13, 1): _fixture("u13_last_page.html").replace(
                    "15 page out of 15", "1 page out of 1"
                )
            }
        )
        matches = await server.source().fetch(["U13"], START, END)
        assert len(matches) == 6
        assert server.calls == [(U13, 1)]

    async def test_an_empty_page_ends_it_when_the_paginator_overstates(self):
        # The live endpoint answers a page past the end with "No data
        # available." (u13_past_end.html).
        server = _Server(
            {
                (U13, 1): _page(["1", "2"], 1, 9),
                (U13, 2): _fixture("u13_past_end.html"),
            }
        )
        matches = await server.source().fetch(["U13"], START, END)
        assert [m.source_match_id for m in matches] == ["1", "2"]
        assert server.calls == [(U13, 1), (U13, 2)]

    async def test_a_repeated_page_ends_it(self):
        server = _Server(
            {
                (U13, 1): _page(["1", "2"], 1, 9),
                (U13, 2): _page(["3", "4"], 2, 9),
            },
            default=_page(["3", "4"], 2, 9),
        )
        source = server.source()

        matches = await source.fetch(["U13"], START, END)

        assert [m.source_match_id for m in matches] == ["1", "2", "3", "4"]
        assert server.calls == [(U13, 1), (U13, 2), (U13, 3)]
        assert source.failures == {}

    async def test_a_match_on_two_pages_is_kept_once(self):
        # A match scored between two requests can slide onto the next page.
        server = _Server(
            {
                (U13, 1): _page(["1", "2"], 1, 2),
                (U13, 2): _page(["2", "3"], 2, 2),
            }
        )
        matches = await server.source().fetch(["U13"], START, END)
        assert [m.source_match_id for m in matches] == ["1", "2", "3"]

    async def test_no_data_at_all_is_no_matches_and_no_failure(self):
        server = _Server({})
        source = server.source()
        assert await source.fetch(["U13"], START, END) == []
        assert source.failures == {}
        assert server.calls == [(U13, 1)]

    async def test_the_page_cap(self, monkeypatch):
        monkeypatch.setattr(Modular11EventSource, "MAX_PAGES", 3)
        pages = {(U13, n): _page([str(n)], n, 99) for n in range(1, 10)}
        server = _Server(pages)
        source = server.source()

        matches = await source.fetch(["U13"], START, END)

        assert server.calls == [(U13, 1), (U13, 2), (U13, 3)]
        assert [m.source_match_id for m in matches] == ["1", "2", "3"]
        assert "3-page cap" in source.failures["U13"]

    async def test_the_default_cap_is_sixty_pages(self):
        assert Modular11EventSource.MAX_PAGES == 60

    async def test_requests_are_spaced_by_the_delay(self):
        server = _Server(
            {
                (U13, 1): _page(["1"], 1, 2),
                (U13, 2): _page(["2"], 2, 2),
                (U14, 1): _page(["3"], 1, 1, age="U14"),
            }
        )
        await server.source(delay=1.5).fetch(["U13", "U14"], START, END)
        # Before every request but the first, across age groups too.
        assert server.sleeps == [1.5, 1.5]

    async def test_one_age_group_after_another(self):
        server = _Server(
            {
                (U13, 1): _page(["1"], 1, 1),
                (U14, 1): _page(["2"], 1, 1, age="U14"),
            }
        )
        matches = await server.source().fetch(["U13", "U14"], START, END)
        assert [(m.age_group, m.source_match_id) for m in matches] == [
            ("U13", "1"),
            ("U14", "2"),
        ]


class TestNeverCleanOnAnEmptyOrTruncatedRead:
    """A read that found nothing must say why, or fail."""

    @pytest.mark.parametrize("status", [301, 302, 307])
    async def test_a_redirect_is_a_failure(self, status):
        server = _Server(
            {(U13, 1): httpx.Response(status, headers={"Location": "/login"})}
        )
        source = server.source(delay=0)

        assert await source.fetch(["U13"], START, END) == []
        assert f"HTTP {status}" in source.failures["U13"]
        assert server.calls == [(U13, 1)]  # not retried

    @pytest.mark.parametrize(
        "body",
        [
            "<html><body><h1>Checking your browser before accessing</h1></body></html>",
            "",
            "<html><body><form action='/login'></form></body></html>",
        ],
    )
    async def test_a_page_that_is_neither_matches_nor_no_data_is_a_failure(self, body):
        server = _Server({(U13, 1): body})
        source = server.source(delay=0)

        assert await source.fetch(["U13"], START, END) == []
        assert "neither matches nor 'No data available.'" in source.failures["U13"]

    async def test_the_same_page_part_way_through_fails_the_age_group(self):
        server = _Server(
            {(U13, 1): _page(["1"], 1, 2), (U13, 2): "<html>blocked</html>"}
        )
        source = server.source(delay=0)
        assert await source.fetch(["U13"], START, END) == []
        assert "page 2" in source.failures["U13"]

    async def test_a_full_page_with_no_paginator_is_a_failure(self):
        ids = [str(n) for n in range(1, 26)]
        server = _Server({(U13, 1): _page(ids)})
        source = server.source(delay=0)

        assert await source.fetch(["U13"], START, END) == []
        assert "no readable paginator" in source.failures["U13"]
        assert server.calls == [(U13, 1)]

    async def test_a_short_page_with_no_paginator_is_the_whole_answer(self):
        server = _Server({(U13, 1): _page(["1", "2"])})
        source = server.source(delay=0)
        assert len(await source.fetch(["U13"], START, END)) == 2
        assert source.failures == {}

    async def test_rows_that_cannot_be_read_are_a_finding_with_a_count(self):
        broken = (
            _page(["1", "2", "3"], 1, 1)
            .replace("<p>Home 2</p>", "<p></p>")
            .replace("<p>Away 3</p>", "<p></p>")
        )
        server = _Server({(U13, 1): broken})
        source = server.source(delay=0)

        matches = await source.fetch(["U13"], START, END)

        assert [m.source_match_id for m in matches] == ["1"]
        assert source.unmapped == {"rows that could not be read (U13)": 2}
        assert source.failures == {}

    async def test_a_page_of_only_unreadable_rows_is_counted_not_called_empty(self):
        broken = _page(["1"], 1, 1).replace("<p>Home 1</p>", "<p></p>")
        server = _Server({(U13, 1): broken})
        source = server.source(delay=0)
        assert await source.fetch(["U13"], START, END) == []
        assert source.unmapped == {"rows that could not be read (U13)": 1}

    async def test_an_unreadable_score_is_a_finding(self):
        page = _page(["1"], 1, 1).replace("1&nbsp:&nbsp0", "1&nbsp:&nbsp0 FF")
        server = _Server({(U13, 1): page})
        source = server.source(delay=0)
        (match,) = await source.fetch(["U13"], START, END)
        assert match.home_score is None
        assert source.unmapped == {"score '1 : 0 FF'": 1}

    async def test_findings_do_not_carry_over_to_the_next_fetch(self):
        broken = _page(["1"], 1, 1).replace("<p>Home 1</p>", "<p></p>")
        server = _Server({(U13, 1): [broken, _page(["1"], 1, 1)]})
        source = server.source(delay=0)
        await source.fetch(["U13"], START, END)
        await source.fetch(["U13"], START, END)
        assert source.unmapped == {}


class TestRetries:
    async def test_a_server_error_is_retried_with_backoff(self):
        server = _Server(
            {
                (U13, 1): [
                    httpx.Response(500),
                    httpx.Response(502),
                    _page(["1"], 1, 1),
                ]
            }
        )
        source = server.source(delay=0)

        matches = await source.fetch(["U13"], START, END)

        assert [m.source_match_id for m in matches] == ["1"]
        assert source.requests == 3
        # backoff 1s, pace, backoff 2s, pace
        assert server.sleeps == [1.0, 0.0, 2.0, 0.0]

    async def test_a_transport_error_is_retried(self):
        server = _Server(
            {(U13, 1): [httpx.ConnectError("connection refused"), _page(["1"], 1, 1)]}
        )
        matches = await server.source(delay=0).fetch(["U13"], START, END)
        assert len(matches) == 1

    @pytest.mark.parametrize("status", [429, 503])
    async def test_retry_after_is_honoured(self, status):
        server = _Server(
            {
                (U13, 1): [
                    httpx.Response(status, headers={"Retry-After": "7"}),
                    _page(["1"], 1, 1),
                ]
            }
        )
        matches = await server.source(delay=0).fetch(["U13"], START, END)
        assert len(matches) == 1
        assert server.sleeps[0] == 7.0

    async def test_a_429_without_retry_after_backs_off(self):
        server = _Server({(U13, 1): [httpx.Response(429), _page(["1"], 1, 1)]})
        await server.source(delay=0).fetch(["U13"], START, END)
        assert server.sleeps[0] == 1.0

    async def test_a_long_retry_after_is_taken_as_stop(self):
        server = _Server(
            {(U13, 1): httpx.Response(429, headers={"Retry-After": "3600"})}
        )
        source = server.source(delay=0)
        assert await source.fetch(["U13"], START, END) == []
        assert source.requests == 1
        assert "Retry-After 3600s" in source.failures["U13"]

    async def test_three_retries_then_the_age_group_fails_and_the_rest_proceed(self):
        server = _Server(
            {
                (U13, 1): httpx.Response(500),
                (U14, 1): _page(["9"], 1, 1, age="U14"),
            }
        )
        source = server.source(delay=0)

        matches = await source.fetch(["U13", "U14"], START, END)

        assert server.calls.count((U13, 1)) == 4  # one try and three retries
        assert [s for s in server.sleeps if s] == [1.0, 2.0, 4.0]
        assert "HTTP 500" in source.failures["U13"]
        assert [m.source_match_id for m in matches] == ["9"]

    async def test_a_client_error_is_not_retried(self):
        server = _Server({(U13, 1): httpx.Response(404)})
        source = server.source(delay=0)
        await source.fetch(["U13"], START, END)
        assert server.calls == [(U13, 1)]
        assert "HTTP 404" in source.failures["U13"]

    async def test_a_failure_part_way_keeps_nothing_from_that_age_group(self):
        # Half an age group would look like the other half's matches vanished.
        server = _Server({(U13, 1): _page(["1"], 1, 2), (U13, 2): httpx.Response(500)})
        source = server.source(delay=0)
        assert await source.fetch(["U13"], START, END) == []
        assert "page 2" in source.failures["U13"]

    async def test_an_unknown_age_group_is_reported_without_a_request(self):
        server = _Server({})
        source = server.source()
        assert await source.fetch(["U12"], START, END) == []
        assert "unknown age group" in source.failures["U12"]
        assert server.calls == []


class TestSaveRaw:
    async def test_every_page_is_kept(self, tmp_path):
        server = _Server({(U13, 1): _page(["1"], 1, 2), (U13, 2): _page(["2"], 2, 2)})
        await server.source(save_raw=tmp_path / "raw").fetch(["U13"], START, END)
        assert sorted(p.name for p in (tmp_path / "raw").iterdir()) == [
            "U13_p01.html",
            "U13_p02.html",
        ]

    def test_the_id_prefix_names_the_event(self):
        assert Modular11EventSource("75").id_prefix == "m11-75-"
        assert Modular11EventSource("75").name == "modular11"
