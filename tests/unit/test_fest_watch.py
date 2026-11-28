"""
Tests for the MLS NEXT Fest page watcher (SB-1774).

The page markup below is trimmed from what the real pages served on
2026-11-25: the landing page's "Fest Schedule & Standings" promo pointing at
the ``/fest/temp`` placeholder, and the placeholder saying "Coming Soon".

What matters most is that an unreadable page is never mistaken for a release.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from src.scraper.fest_watch import (
    FEST_END,
    FEST_PAGES,
    FEST_START,
    M11_EVENT_IDS,
    FestPage,
    FestPageResult,
    FestPageState,
    FestProbe,
    FestWatcher,
    PageKind,
    classify_page,
)

LANDING = FestPage(
    name="matchcenter",
    url="https://matchcenter.mlsnextpro.com/mlsnext/tournaments/fest/",
    kind=PageKind.SCHEDULE_PROMO,
)
TEMP = FestPage(
    name="fest-temp",
    url="https://www.mlssoccer.com/mlsnext/tournaments/fest/temp",
    kind=PageKind.COMING_SOON,
)

PLACEHOLDER = "https://www.mlssoccer.com/mlsnext/tournaments/fest/temp"


def _landing(href: str = PLACEHOLDER, *, promo: bool = True) -> str:
    block = (
        '<div class="oc-c-promo" id="mlsnext-fest-schedule-standings">'
        f'<a href="{href}">Fest Schedule &amp; Standings</a></div>'
        if promo
        else ""
    )
    return (
        "<html><head><title>MLS NEXT Fest Tournament</title></head><body>"
        f"{block}"
        '<div class="oc-c-promo" id="mlsnext-fest-additional-fest-information">'
        '<a href="https://events.mlssoccer.com/index.php/6AD7AF5B811F5.html">'
        "Additional Fest Information</a></div></body></html>"
    )


def _temp(body: str = "<p>Coming Soon</p>") -> str:
    return (
        "<html><head><title>MLS NEXT Fest Tournament</title></head>"
        f"<body><nav>Schedule Standings</nav>{body}</body></html>"
    )


M11_FIXTURES = Path(__file__).parent / "fixtures/modular11_event_75"
M11_NO_DATA = (M11_FIXTURES / "no_data.html").read_text()
M11_MATCHES = (M11_FIXTURES / "u15_ga_cup.html").read_text()


async def _no_sleep(_: float) -> None:
    return None


class TestSchedulePromo:
    def test_placeholder_link_is_waiting(self):
        r = classify_page(LANDING, 200, LANDING.url, _landing())
        assert r.state is FestPageState.WAITING

    def test_placeholder_with_trailing_slash_is_still_waiting(self):
        r = classify_page(LANDING, 200, LANDING.url, _landing(PLACEHOLDER + "/"))
        assert r.state is FestPageState.WAITING

    def test_relative_placeholder_link_is_waiting(self):
        r = classify_page(
            LANDING, 200, LANDING.url, _landing("/mlsnext/tournaments/fest/temp")
        )
        assert r.state is FestPageState.WAITING

    def test_a_new_link_is_a_release_and_reports_the_link(self):
        new = "https://www.modular11.com/events/event/iframe/schedule/80"
        r = classify_page(LANDING, 200, LANDING.url, _landing(new))
        assert r.state is FestPageState.RELEASED
        assert r.detail == new

    def test_a_relative_new_link_is_reported_absolute(self):
        r = classify_page(
            LANDING, 200, LANDING.url, _landing("/mlsnext/tournaments/fest/schedule")
        )
        assert r.state is FestPageState.RELEASED
        assert r.detail == (
            "https://matchcenter.mlsnextpro.com/mlsnext/tournaments/fest/schedule"
        )

    def test_a_missing_promo_is_an_error_not_a_release(self):
        r = classify_page(LANDING, 200, LANDING.url, _landing(promo=False))
        assert r.state is FestPageState.ERROR

    def test_a_promo_without_a_link_is_an_error(self):
        html = _landing().replace(f'<a href="{PLACEHOLDER}">', "<a>")
        r = classify_page(LANDING, 200, LANDING.url, html)
        assert r.state is FestPageState.ERROR


class TestComingSoon:
    def test_coming_soon_is_waiting(self):
        r = classify_page(TEMP, 200, TEMP.url, _temp())
        assert r.state is FestPageState.WAITING

    def test_coming_soon_is_case_and_whitespace_insensitive(self):
        r = classify_page(TEMP, 200, TEMP.url, _temp("<h2>COMING\n   soon</h2>"))
        assert r.state is FestPageState.WAITING

    def test_real_content_is_a_release(self):
        r = classify_page(TEMP, 200, TEMP.url, _temp("<table>U15 Group A</table>"))
        assert r.state is FestPageState.RELEASED
        assert r.detail == TEMP.url

    def test_text_hidden_in_a_script_does_not_count(self):
        html = _temp("<script>var s='Coming Soon';</script><table>U15</table>")
        r = classify_page(TEMP, 200, TEMP.url, html)
        assert r.state is FestPageState.RELEASED


class TestUnreadablePagesAreErrors:
    """A block page, an outage or a redirect must never announce a release."""

    @pytest.mark.parametrize("status", [403, 404, 500, 503])
    def test_non_200(self, status):
        r = classify_page(TEMP, status, TEMP.url, "")
        assert r.state is FestPageState.ERROR
        assert str(status) in r.detail

    def test_a_block_page_without_the_fest_title(self):
        html = "<html><head><title>Just a moment...</title></head><body></body></html>"
        r = classify_page(TEMP, 200, TEMP.url, html)
        assert r.state is FestPageState.ERROR

    def test_a_redirect_away_from_the_page(self):
        r = classify_page(TEMP, 200, "https://www.mlssoccer.com/mlsnext/", _temp(""))
        assert r.state is FestPageState.ERROR
        assert "redirected" in r.detail


class TestFestProbe:
    def _probe(self, *states):
        return FestProbe(
            checked_at="2026-11-25T12:00:00Z",
            results=[
                FestPageResult(name=f"p{i}", url="u", state=s)
                for i, s in enumerate(states)
            ],
        )

    def test_all_failed_only_when_every_page_failed(self):
        assert self._probe(FestPageState.ERROR, FestPageState.ERROR).all_failed
        assert not self._probe(FestPageState.ERROR, FestPageState.WAITING).all_failed

    def test_an_empty_probe_is_not_all_failed(self):
        assert not self._probe().all_failed

    def test_released_lists_released_pages(self):
        probe = self._probe(FestPageState.WAITING, FestPageState.RELEASED)
        assert [r.name for r in probe.released] == ["p1"]


class TestFestWatcher:
    def test_watches_the_three_known_pages(self):
        assert {p.name for p in FEST_PAGES} == {
            "matchcenter",
            "mlssoccer",
            "fest-temp",
        }

    def test_probe_over_mock_transport(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/temp"):
                return httpx.Response(200, text=_temp())
            if request.url.host == "www.mlssoccer.com":
                return httpx.Response(503)
            return httpx.Response(200, text=_landing())

        watcher = FestWatcher(transport=httpx.MockTransport(handler), m11_events=())
        probe = asyncio.run(watcher.probe())

        states = {r.name: r.state for r in probe.results}
        assert states == {
            "matchcenter": FestPageState.WAITING,
            "mlssoccer": FestPageState.ERROR,
            "fest-temp": FestPageState.WAITING,
        }
        assert not probe.all_failed

    def test_a_network_error_is_an_error_result(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom", request=request)

        watcher = FestWatcher(
            transport=httpx.MockTransport(handler), m11_events=(76,), sleep=_no_sleep
        )
        probe = asyncio.run(watcher.probe())
        assert probe.all_failed
        assert all("ConnectError" in r.detail for r in probe.results)


class TestModular11Events:
    """The 2026 schedule may land on modular11 first (SB-1830)."""

    def _probe(self, answers: dict[str, httpx.Response], events=(76, 77, 78)):
        asked: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host != "www.modular11.com":
                return httpx.Response(200, text=_landing())
            asked.append(request)
            event = request.url.params["tournament"]
            return answers.get(event, httpx.Response(200, text=M11_NO_DATA))

        watcher = FestWatcher(
            pages=(),
            transport=httpx.MockTransport(handler),
            m11_events=events,
            sleep=_no_sleep,
        )
        return asyncio.run(watcher.probe()), asked

    def test_candidates_start_after_the_2025_event(self):
        assert min(M11_EVENT_IDS) == 76
        assert 75 not in M11_EVENT_IDS

    def test_no_data_everywhere_is_waiting(self):
        probe, _ = self._probe({})
        assert {r.state for r in probe.results} == {FestPageState.WAITING}
        assert not probe.released

    def test_an_event_with_matches_is_a_release_with_its_schedule_page(self):
        probe, _ = self._probe({"77": httpx.Response(200, text=M11_MATCHES)})
        assert [(r.name, r.detail) for r in probe.released] == [
            (
                "modular11-77",
                "https://www.modular11.com/events/event/iframe/schedule/77",
            )
        ]

    def test_asks_for_u15_inside_the_fest_dates(self):
        _, asked = self._probe({}, events=(80,))
        params = asked[0].url.params
        assert params["tournament"] == "80"
        assert params["start_date"] == f"{FEST_START.isoformat()} 00:00:00"
        assert params["end_date"] == f"{FEST_END.isoformat()} 23:59:59"

    @pytest.mark.parametrize(
        "response",
        [
            httpx.Response(404),
            httpx.Response(503),
            httpx.Response(302, headers={"Location": "https://example.com/login"}),
            httpx.Response(200, text="<html><title>Login</title></html>"),
        ],
    )
    def test_an_unreadable_answer_is_an_error_not_a_release(self, response):
        probe, _ = self._probe({"76": response}, events=(76,))
        assert probe.results[0].state is FestPageState.ERROR
        assert probe.all_failed

    def test_one_failed_event_does_not_hide_the_others(self):
        probe, _ = self._probe(
            {"76": httpx.Response(500), "78": httpx.Response(200, text=M11_MATCHES)}
        )
        states = {r.name: r.state for r in probe.results}
        assert states == {
            "modular11-76": FestPageState.ERROR,
            "modular11-77": FestPageState.WAITING,
            "modular11-78": FestPageState.RELEASED,
        }
