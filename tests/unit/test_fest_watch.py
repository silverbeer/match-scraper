"""
Tests for the MLS NEXT Fest page watcher (SB-1774).

The page markup below is trimmed from what the real pages served on
2026-11-25: the landing page's "Fest Schedule & Standings" promo pointing at
the ``/fest/temp`` placeholder, and the placeholder saying "Coming Soon".

What matters most is that an unreadable page is never mistaken for a release.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from src.scraper.fest_watch import (
    FEST_PAGES,
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

        watcher = FestWatcher(transport=httpx.MockTransport(handler))
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

        probe = asyncio.run(FestWatcher(transport=httpx.MockTransport(handler)).probe())
        assert probe.all_failed
        assert all("ConnectError" in r.detail for r in probe.results)
