"""Past MT matches that disagree with the official feed (SB-1787)."""

from __future__ import annotations

from datetime import date, datetime

import httpx
import pytest
from freezegun import freeze_time

from src.orchestrator.completeness import (
    FeedEvent,
    MtReadError,
    SeasonRow,
    classify,
    mt_only,
    read_season,
    totals,
)
from src.scraper.models import Match

TODAY = date(2026, 11, 26)
PLAYED = date(2026, 10, 4)
PLACEHOLDER = date(2027, 6, 8)
HOME = "Miami Futbol Academy Rush"
AWAY = "Sol SC Florida"


@pytest.fixture(autouse=True)
def _frozen():
    # Match.match_status reads the clock: pin it to the classifier's today.
    with freeze_time("2026-11-26 12:00:00"):
        yield


def _event(
    game_key="28249",
    *,
    score=(2, 1),
    pens=(None, None),
    day=PLAYED,
    completed=True,
    on_placeholder=False,
    home=HOME,
    away=AWAY,
    league="Homegrown",
):
    match = Match(
        match_id=game_key,
        match_datetime=datetime(day.year, day.month, day.day, 10, 0),
        home_team=home,
        away_team=away,
        home_score=score[0] if score else None,
        away_score=score[1] if score else None,
        home_penalty_score=pens[0],
        away_penalty_score=pens[1],
        postponed=on_placeholder and not score,
    )
    return FeedEvent(
        game_key=game_key,
        league=league,
        match_type="Flex" if league == "Flex" else "League",
        division="Florida",
        age_group="U15",
        match_date=day,
        completed=completed,
        on_placeholder=on_placeholder,
        match=match,
    )


def _row(match_id="28249", **overrides):
    fields = {
        "id": 7482,
        "match_id": match_id,
        "match_date": PLAYED,
        "match_status": "completed",
        "home_team_name": HOME,
        "away_team_name": AWAY,
        "home_score": 2,
        "away_score": 1,
        "league_id": 1,
        "league": "Homegrown",
        "match_type": "League",
        "source": "match-scraper-agent",
    }
    fields.update(overrides)
    return SeasonRow(**fields)


def _one(event, row):
    changes = classify([event], [row], today=TODAY)
    assert len(changes) == 1, changes
    return changes[0]


class TestClasses:
    def test_score(self):
        change = _one(_event(score=(3, 1)), _row())
        assert (change.klass, change.action) == ("score", "send")
        assert (change.mt_value, change.feed_value) == ("2-1", "3-1")
        assert "28249 | score | score: 2-1 -> 3-1 | -" == change.line()

    def test_a_shootout_that_differs_is_a_score_change(self):
        change = _one(
            _event(score=(1, 1), pens=(4, 2)), _row(home_score=1, away_score=1)
        )
        assert change.klass == "score"
        assert change.feed_value == "1-1 (p 4-2)"

    def test_swap(self):
        change = _one(_event(home=AWAY, away=HOME, score=(1, 2)), _row())
        assert (change.klass, change.action) == ("swap", "send")
        assert change.field == "home/away"

    def test_a_swap_sends_the_feeds_sides(self):
        change = _one(_event(home=AWAY, away=HOME, score=(1, 2)), _row())
        payload = change.payload()
        assert (payload["home_team"], payload["away_team"]) == (AWAY, HOME)
        assert (payload["home_score"], payload["away_score"]) == (1, 2)

    def test_status(self):
        change = _one(
            _event(score=(0, 1)),
            _row(match_status="scheduled", home_score=None, away_score=None),
        )
        assert (change.klass, change.action) == ("status", "send")
        assert change.payload()["match_status"] == "completed"

    def test_tbd_is_unplayed_too(self):
        change = _one(
            _event(), _row(match_status="tbd", home_score=None, away_score=None)
        )
        assert change.klass == "status"

    def test_redate(self):
        new = date(2027, 2, 21)
        change = _one(
            _event(score=None, completed=False, day=new),
            _row(match_status="scheduled", home_score=None, away_score=None),
        )
        assert (change.klass, change.action) == ("redate", "send")
        assert (change.mt_value, change.feed_value) == (str(PLAYED), str(new))
        payload = change.payload()
        assert payload["match_status"] == "scheduled"
        assert payload["match_date"] == new.isoformat()

    def test_a_postponed_row_with_a_real_new_date_is_redated(self):
        # SB-1783: MT keeps a postponed match on its old date.
        change = _one(
            _event(score=None, completed=False, day=date(2027, 3, 7)),
            _row(match_status="postponed", home_score=None, away_score=None),
        )
        assert change.klass == "redate"

    def test_voided_is_report_only(self):
        change = _one(
            _event(score=None, completed=False, day=PLACEHOLDER, on_placeholder=True),
            _row(home_score=1, away_score=0),
        )
        assert (change.klass, change.action) == ("voided", "report")
        assert "placeholder" in change.flags
        assert change.event is None
        with pytest.raises(ValueError):
            change.payload()

    def test_the_same_result_is_no_change(self):
        assert classify([_event()], [_row()], today=TODAY) == []


class TestNeverSent:
    def test_a_locked_row_is_reported_not_sent(self):
        change = _one(_event(score=(3, 1)), _row(score_locked=True))
        assert change.action == "report"
        assert change.reason == "locked, differs"
        assert "locked" in change.flags
        assert "locked" in change.line()

    def test_a_locked_redate_is_reported_too(self):
        change = _one(
            _event(score=None, completed=False, day=date(2027, 2, 21)),
            _row(
                match_status="scheduled",
                home_score=None,
                away_score=None,
                score_locked=True,
            ),
        )
        assert change.action == "report"

    def test_a_persons_score_is_sent_and_flagged(self):
        change = _one(_event(score=(3, 1)), _row(entered_by_person=True))
        assert change.action == "send"
        assert "person" in change.flags
        assert change.overrides_person

    def test_a_persons_unscored_row_does_not_override_a_score(self):
        change = _one(
            _event(),
            _row(
                match_status="scheduled",
                home_score=None,
                away_score=None,
                entered_by_person=True,
            ),
        )
        assert change.action == "send"
        assert not change.overrides_person

    def test_a_forfeit_with_the_feeds_score_is_no_change(self):
        assert classify([_event()], [_row(match_status="forfeit")], today=TODAY) == []

    def test_a_forfeit_with_another_score_is_for_a_person(self):
        change = _one(_event(score=(3, 0)), _row(match_status="forfeit"))
        assert change.action == "report"
        assert "forfeit" in change.flags

    def test_a_postponement_on_the_placeholder_is_voided_not_redated(self):
        change = _one(
            _event(score=None, completed=False, day=PLACEHOLDER, on_placeholder=True),
            _row(),
        )
        assert change.klass == "voided"

    def test_a_past_scheduled_row_postponed_to_the_placeholder_is_reported(self):
        # The feed parked it; MT still has it scheduled on its old, past date.
        change = _one(
            _event(score=None, completed=False, day=PLACEHOLDER, on_placeholder=True),
            _row(match_status="scheduled", home_score=None, away_score=None),
        )
        assert (change.klass, change.action) == ("redate", "report")
        assert change.reason == "postponed to the placeholder: no real date yet"
        assert "placeholder" in change.flags

    def test_a_postponed_row_on_the_placeholder_is_no_change(self):
        # 42362: MT already says postponed and the feed has no real date.
        assert (
            classify(
                [
                    _event(
                        score=None,
                        completed=False,
                        day=PLACEHOLDER,
                        on_placeholder=True,
                    )
                ],
                [_row(match_status="postponed", home_score=None, away_score=None)],
                today=TODAY,
            )
            == []
        )

    def test_a_result_on_the_placeholder_is_for_a_person(self):
        change = _one(
            _event(day=PLACEHOLDER, on_placeholder=True),
            _row(match_status="scheduled", home_score=None, away_score=None),
        )
        assert change.action == "report"
        assert "placeholder" in change.flags

    def test_an_unscored_fixture_on_a_past_date_is_never_sent(self):
        change = _one(
            _event(score=None, completed=False, day=date(2026, 11, 22)),
            _row(match_status="scheduled", home_score=None, away_score=None),
        )
        assert change.klass == "redate"
        assert change.action == "report"

    def test_an_unscored_fixture_dated_today_is_never_sent(self):
        change = _one(
            _event(score=None, completed=False, day=TODAY),
            _row(match_status="scheduled", home_score=None, away_score=None),
        )
        assert change.action == "report"


class TestScope:
    def test_only_rows_before_today(self):
        assert (
            classify(
                [_event(score=(3, 1), day=TODAY)], [_row(match_date=TODAY)], today=TODAY
            )
            == []
        )

    def test_since(self):
        changes = classify(
            [_event(score=(3, 1))], [_row()], today=TODAY, since=date(2026, 10, 5)
        )
        assert changes == []

    def test_other_competitions_are_not_compared(self):
        row = _row(match_type="Tournament")
        assert classify([_event(score=(3, 1))], [row], today=TODAY) == []

    def test_a_row_filed_under_another_league_is_not_compared(self):
        row = _row(league="Flex", match_type="Flex")
        assert classify([_event(score=(3, 1))], [row], today=TODAY) == []

    def test_league_filter(self):
        assert (
            classify([_event(score=(3, 1))], [_row()], today=TODAY, leagues=["Flex"])
            == []
        )

    def test_a_cancelled_unplayed_fixture_is_left_alone(self):
        row = _row(match_status="cancelled", home_score=None, away_score=None)
        event = _event(score=None, completed=False, day=date(2027, 2, 21))
        assert classify([event], [row], today=TODAY) == []

    def test_a_postponed_row_the_feed_has_played_is_a_status_change(self):
        # match_tasks._incoming_status lets a real score lift a postponement.
        change = _one(
            _event(score=(0, 1)),
            _row(match_status="postponed", home_score=None, away_score=None),
        )
        assert (change.klass, change.action) == ("status", "send")
        assert change.mt_value == "postponed"
        assert change.payload()["match_status"] == "completed"

    def test_a_cancelled_row_the_feed_has_played_is_for_a_person(self):
        change = _one(
            _event(score=(0, 1)),
            _row(match_status="cancelled", home_score=None, away_score=None),
        )
        assert (change.klass, change.action) == ("status", "report")
        assert change.reason == "cancelled in MT, played per feed"

    def test_mt_only_rows_are_reported(self):
        rows = [_row("1"), _row("2", match_status="scheduled", id=2)]
        assert [r.match_id for r in mt_only(rows, {"9"}, today=TODAY)] == ["1"]

    def test_totals(self):
        changes = classify(
            [_event("1", score=(3, 1)), _event("2", score=(3, 1))],
            [_row("1", id=1), _row("2", id=2, score_locked=True)],
            today=TODAY,
        )
        assert totals(changes)["score"] == {"send": 1, "report": 1}


class TestReadSeason:
    def _client(self, pages, *, status=200, seasons=None, leagues=None):
        asked: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path == "/api/seasons":
                return httpx.Response(
                    200, json=seasons or [{"id": 184, "name": "2026-2027"}]
                )
            if path == "/api/leagues":
                return httpx.Response(
                    200,
                    json=leagues
                    or [
                        {"id": 1, "name": "Homegrown"},
                        {"id": 2, "name": "Academy"},
                        {"id": 290, "name": "Flex"},
                    ],
                )
            params = dict(request.url.params)
            asked.append(params)
            page = int(params["page"])
            if status != 200:
                return httpx.Response(status)
            rows = pages[page] if page < len(pages) else 0
            return httpx.Response(
                200,
                json={
                    "matches": [
                        {
                            "id": page * 1000 + i,
                            "match_id": page * 1000 + i,
                            "match_date": "2026-10-04",
                            "match_status": "completed",
                            "league_id": 290,
                            "match_type": "Flex",
                            "entered_by_person": False,
                            "score_locked": False,
                        }
                        for i in range(rows)
                    ]
                },
            )

        return httpx.Client(transport=httpx.MockTransport(handler)), asked

    def test_reads_until_the_first_empty_page(self):
        # A short page is not the last one.
        client, asked = self._client([2, 1, 3])

        rows = read_season(
            "http://mt",
            "k",
            season="2026-2027",
            leagues=["Homegrown", "Flex"],
            start=date(2026, 8, 1),
            end=date(2026, 11, 25),
            client=client,
        )

        assert len(rows) == 6
        assert [a["page"] for a in asked] == ["0", "1", "2", "3"]
        assert asked[0]["season_id"] == "184"
        assert asked[0]["league_ids"] == "1,290"
        assert asked[0]["start_date"] == "2026-08-01"
        assert asked[0]["end_date"] == "2026-11-25"
        assert {r.league for r in rows} == {"Flex"}
        assert rows[0].match_id == "0"

    def test_a_failed_page_is_an_error_not_a_short_read(self):
        client, _ = self._client([2], status=500)
        with pytest.raises(MtReadError):
            read_season(
                "http://mt", "k", season="2026-2027", leagues=["Flex"], client=client
            )

    def test_an_unknown_season_is_an_error(self):
        client, asked = self._client([2], seasons=[{"id": 1, "name": "2025-2026"}])
        with pytest.raises(MtReadError):
            read_season(
                "http://mt", "k", season="2026-2027", leagues=["Flex"], client=client
            )
        assert asked == []

    def test_an_unknown_league_is_an_error(self):
        client, _ = self._client([2], leagues=[{"id": 1, "name": "Homegrown"}])
        with pytest.raises(MtReadError):
            read_season(
                "http://mt", "k", season="2026-2027", leagues=["Flex"], client=client
            )

    def test_league_entries_without_a_name_are_skipped(self):
        client, _ = self._client(
            [1],
            leagues=[
                {"id": 7},
                {"name": None, "id": 8},
                "x",
                {"name": "Flex", "id": 290},
            ],
        )
        rows = read_season(
            "http://mt", "k", season="2026-2027", leagues=["Flex"], client=client
        )
        assert len(rows) == 1

    def test_a_league_list_that_is_not_a_list_is_an_error(self):
        client, _ = self._client([1], leagues={"detail": "?"})
        with pytest.raises(MtReadError):
            read_season(
                "http://mt", "k", season="2026-2027", leagues=["Flex"], client=client
            )

    def test_a_page_without_matches_is_an_error(self):
        client = httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json=[{"id": 184, "name": "2026-2027"}]
                    if request.url.path == "/api/seasons"
                    else [{"id": 290, "name": "Flex"}]
                    if request.url.path == "/api/leagues"
                    else {"detail": "?"},
                )
            )
        )
        with pytest.raises(MtReadError):
            read_season(
                "http://mt", "k", season="2026-2027", leagues=["Flex"], client=client
            )


# MarkdownV2 reserves these; every one must be backslash-escaped outside the
# * and _ markers the report uses, or Telegram rejects the whole message.
_RESERVED = set("[]()~`>#+-=|{}.!")


def _unescaped(message: str) -> list[str]:
    bad = []
    i = 0
    while i < len(message):
        ch = message[i]
        if ch == "\\":
            i += 2
            continue
        if ch in _RESERVED:
            bad.append(message[max(0, i - 20) : i + 1])
        i += 1
    return bad


class TestReconcileReportIsValidMarkdownV2:
    from src.orchestrator.report import build_reconcile_report as build

    BASE = {
        "env": "prod",
        "totals": {
            "score": {"send": 2, "report": 1},
            "swap": {"send": 0, "report": 0},
            "status": {"send": 1, "report": 0},
            "redate": {"send": 1, "report": 0},
            "voided": {"send": 0, "report": 4},
        },
        "sent": ["26044", "26079", "26839", "30664"],
        "send_failed": [],
        "report_only": {
            "locked, differs": ["27093"],
            "MT counts it as played and the feed does not; never voided here": [
                "28249",
                "28250",
            ],
        },
        "overrides_person": ["26079"],
        "mt_only": ["TSC-DRYRUN-1"],
        "log_path": "/data/agent-state/reconcile/20261130T100000Z-abcd1234.json",
    }

    @pytest.mark.parametrize(
        "overrides",
        [
            {},
            {"send_failed": ["26044"]},
            {"refused": "140 corrections to send, more than --max-changes 100."},
            {"log_path": ""},
        ],
    )
    def test_every_variant(self, overrides):
        message = type(self).build(**{**self.BASE, **overrides})
        assert _unescaped(message) == []

    def test_the_header_counts_report_only(self):
        message = type(self).build(**self.BASE)
        assert "4 to send, 5 report only" in message
        assert "for a person" not in message.split("\n")[0]

    def test_a_refused_run_would_override_not_overrides(self):
        message = type(self).build(**{**self.BASE, "sent": [], "refused": "too many"})
        assert "Would override a person" in message
        assert "*Overrides a person" not in message
        sent = type(self).build(**self.BASE)
        assert "*Overrides a person" in sent
