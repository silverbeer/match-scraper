"""Official results missing from missing-table (SB-1786)."""

from __future__ import annotations

from datetime import date, datetime

import httpx
import pytest

from src.orchestrator.completeness import (
    MT_PAGE_CAP,
    MT_SPLIT_AT,
    FeedEvent,
    MtPageFull,
    MtReadError,
    MtRow,
    _bracket_of,
    counts,
    diff,
    fetch_mt_rows,
    in_window,
    mt_pages,
    publish_mismatch,
    triage,
)
from src.scraper.assist_client import AssistEvent, AssistIndex
from src.scraper.models import Match

PLACEHOLDER = date(2027, 6, 8)


def _event(game_key="26363", *, completed=True, score=(8, 0), **overrides):
    day = overrides.pop("match_date", date(2026, 9, 6))
    pens = overrides.pop("pens", (None, None))
    match = Match(
        match_id=game_key,
        match_datetime=datetime(day.year, day.month, day.day, 10, 0),
        home_team="Los Angeles Bulls Soccer Club",
        away_team="Ventura County Fusion",
        home_score=score[0] if score else None,
        away_score=score[1] if score else None,
        home_penalty_score=pens[0],
        away_penalty_score=pens[1],
        postponed=overrides.get("on_placeholder", False),
    )
    fields = {
        "game_key": game_key,
        "league": "Flex",
        "match_type": "Flex",
        "division": "Southwest (North)",
        "age_group": "U15",
        "match_date": day,
        "completed": completed,
        "match": match,
    }
    fields.update(overrides)
    return FeedEvent(**fields)


def _row(match_id="26363", **overrides):
    fields = {
        "id": 1,
        "match_id": match_id,
        "match_date": date(2026, 9, 6),
        "match_status": "completed",
        "match_type_name": "Flex",
        "league_name": "Flex",
        "division_name": "Southwest (North)",
        "age_group_name": "U15",
        "home_score": 8,
        "away_score": 0,
    }
    fields.update(overrides)
    return MtRow(**fields)


class TestDiff:
    def test_a_completed_result_mt_lacks_is_a_create(self):
        gaps = diff([_event()], [])

        assert [(g.action, g.game_key) for g in gaps] == [("create", "26363")]
        assert gaps[0].division == "Southwest (North)"
        assert gaps[0].score == "8-0"

    def test_a_result_already_in_mt_is_not_a_gap(self):
        assert diff([_event()], [_row()]) == []

    def test_a_row_filed_under_another_competition_still_exists(self):
        # Wrong league or type is a different finding; resending is not its fix.
        row = _row(match_type_name="League", league_name="Homegrown")
        assert [g for g in diff([_event()], [row]) if g.action == "create"] == []

    def test_an_unplayed_fixture_is_never_a_gap(self):
        assert diff([_event(completed=False, score=None)], []) == []

    def test_completed_with_no_score_is_not_sent(self):
        assert diff([_event(score=None)], []) == []

    def test_the_shootout_travels_with_the_score(self):
        (gap,) = diff([_event(score=(3, 3), pens=(3, 4))], [])

        assert gap.score == "3-3 (p 3-4)"
        assert gap.event.match.home_penalty_score == 3

    def test_an_mt_only_result_is_reported_never_created(self):
        gaps = diff([_event()], [_row(), _row("99999", id=2)])

        assert [(g.action, g.game_key, g.mt_id) for g in gaps] == [
            ("report", "99999", 2)
        ]

    def test_an_mt_row_the_feed_holds_unplayed_is_not_mt_only(self):
        # Miami v Sol SC, 28249-28252: MT counts them, the feed has them
        # unplayed on the placeholder. That disagreement is not "MT-only".
        event = _event("28249", completed=False, score=None)
        assert diff([event], [_row("28249")]) == []

    def test_an_unplayed_mt_row_is_not_reported(self):
        scheduled = _row("99999", id=2, match_status="scheduled")
        assert diff([_event()], [_row(), scheduled]) == []

    def test_mt_rows_outside_the_covered_competitions_are_ignored(self):
        academy = _row("55555", id=3, league_name="Academy", match_type_name="League")
        tournament = _row("m11-75-1", id=4, match_type_name="Tournament")
        assert diff([_event()], [_row(), academy, tournament]) == []

    def test_a_cross_bracket_event_keeps_its_own_bracket(self):
        event = _event("28630", division="Empire")
        (gap,) = diff([event], [])
        assert gap.division == "Empire"

    def test_a_bracketless_event_is_still_listed(self):
        (gap,) = diff([_event(division=None, age_group=None)], [])
        assert gap.division is None
        assert "(no bracket)" in gap.line()


class TestWindow:
    def test_inside_and_outside(self):
        start, end = date(2026, 8, 1), date(2026, 11, 24)
        assert in_window(_event(), start, end)
        assert not in_window(_event(match_date=date(2026, 11, 25)), start, end)

    def test_a_result_on_the_placeholder_counts_whatever_the_window(self):
        # One of SB-1779's 121 was a scored fixture parked on 2027-06-08.
        event = _event(match_date=PLACEHOLDER, on_placeholder=True)
        assert in_window(event, date(2026, 8, 1), date(2026, 11, 24))
        assert [g.action for g in diff([event], [])] == ["create"]

    def test_an_unplayed_placeholder_fixture_does_not(self):
        event = _event(
            match_date=PLACEHOLDER, on_placeholder=True, completed=False, score=None
        )
        assert not in_window(event, date(2026, 8, 1), date(2026, 11, 24))


def test_counts_per_league_division_age():
    gaps = diff(
        [
            _event("1"),
            _event("2"),
            _event("3", division="Southeast", age_group="U16"),
        ],
        [],
    )
    assert counts(gaps) == {
        ("Flex", "Southeast", "U16"): 1,
        ("Flex", "Southwest (North)", "U15"): 2,
    }


class TestBracketOf:
    INDEX = AssistIndex(
        key="k",
        brackets={
            ("Empire", "U15"): frozenset({1}),
            ("Turnpike", "U15"): frozenset({2}),
        },
        bracket_ids={10: ("Empire", "U15"), 20: ("Turnpike", "U15")},
    )

    def _raw(self, **fields):
        base = {
            "id": 1,
            "game_key": "28630",
            "start_time": "2026-10-14T23:00:00Z",
            "home_squad_id": 2,
            "away_squad_id": 1,
        }
        return AssistEvent.model_validate({**base, **fields})

    def test_the_events_own_bracket_wins(self):
        # Home squad is in Turnpike; the feed files the fixture in Empire.
        assert _bracket_of(self._raw(competition_bracket_id=10), self.INDEX) == (
            "Empire",
            "U15",
        )

    def test_a_bracketless_event_falls_back_to_the_home_squad(self):
        assert _bracket_of(self._raw(), self.INDEX) == ("Turnpike", "U15")

    def test_then_the_away_squad(self):
        raw = self._raw(home_squad_id=99)
        assert _bracket_of(raw, self.INDEX) == ("Empire", "U15")

    def test_nothing_found(self):
        raw = self._raw(home_squad_id=98, away_squad_id=99)
        assert _bracket_of(raw, self.INDEX) == (None, None)


def test_the_standings_index_records_bracket_ids():
    payload = {
        "competition_season": {
            "age_groups": [{"id": 5, "name": "U15"}],
            "competition_season_stages": [
                {
                    "name": "Flex",
                    "competition_brackets": [
                        {
                            "id": 10,
                            "name": "Empire",
                            "age_group_id": 5,
                            "standings": [{"squad_id": 1}],
                        }
                    ],
                }
            ],
        }
    }
    index = AssistIndex.from_standings("k", payload, "Flex")
    assert index.bracket_ids == {10: ("Empire", "U15")}


class TestPaging:
    def test_weekly_pages_plus_extra_days(self):
        pages = mt_pages(date(2026, 8, 1), date(2026, 8, 16), [PLACEHOLDER])
        assert pages == [
            (date(2026, 8, 1), date(2026, 8, 7)),
            (date(2026, 8, 8), date(2026, 8, 14)),
            (date(2026, 8, 15), date(2026, 8, 16)),
            (PLACEHOLDER, PLACEHOLDER),
        ]

    def test_an_extra_day_inside_the_range_is_not_read_twice(self):
        pages = mt_pages(date(2026, 8, 1), date(2026, 8, 7), [date(2026, 8, 3)])
        assert pages == [(date(2026, 8, 1), date(2026, 8, 7))]

    @staticmethod
    def _client(sizes):
        asked = []

        def handler(request):
            asked.append(dict(request.url.params))
            n = sizes[len(asked) - 1]
            return httpx.Response(
                200,
                json=[
                    {"id": len(asked) * 10_000 + i, "match_id": str(i)}
                    for i in range(n)
                ],
            )

        return httpx.Client(transport=httpx.MockTransport(handler)), asked

    def test_reads_every_page(self):
        client, asked = self._client([2, 3])
        pages = mt_pages(date(2026, 8, 1), date(2026, 8, 14))

        rows = fetch_mt_rows("http://mt", "k", pages, client=client)

        assert len(rows) == 5
        assert asked == [
            {"start_date": "2026-08-01", "end_date": "2026-08-07"},
            {"start_date": "2026-08-08", "end_date": "2026-08-14"},
        ]

    def test_a_page_at_the_postgrest_cap_is_an_error(self):
        client, _ = self._client([2, MT_PAGE_CAP])
        pages = mt_pages(date(2026, 8, 1), date(2026, 8, 14))

        with pytest.raises(MtPageFull, match="1000"):
            fetch_mt_rows("http://mt", "k", pages, client=client)

    def test_an_http_failure_is_an_error_not_an_empty_page(self):
        client = httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(503))
        )
        with pytest.raises(MtReadError):
            fetch_mt_rows(
                "http://mt", "k", [(date(2026, 8, 1), date(2026, 8, 7))], client=client
            )


class TestPublishMismatch:
    def test_prod_with_prod(self):
        assert (
            publish_mismatch("https://api.missingtable.com", "matches.prod", "") is None
        )

    def test_local_with_a_non_prod_queue(self):
        assert publish_mismatch("http://localhost:8000", "matches.local", "") is None

    def test_prod_queue_with_a_local_api_is_refused(self):
        reason = publish_mismatch("http://localhost:8000", "matches.prod", "")
        assert reason and "localhost" in reason

    def test_prod_api_with_a_local_queue_is_refused(self):
        reason = publish_mismatch("https://api.missingtable.com", "matches.local", "")
        assert reason and "matches.local" in reason

    def test_a_fanout_exchange_is_refused(self):
        assert publish_mismatch("https://api.missingtable.com", "", "matches-fanout")


class TestShortReads:
    """/api/matches answers 200 [] when its database query fails (SB-1786)."""

    @staticmethod
    def _client(pages: dict[str, int]):
        asked = []

        def handler(request):
            params = dict(request.url.params)
            asked.append((params["start_date"], params["end_date"]))
            n = pages.get(f"{params['start_date']}..{params['end_date']}", 0)
            base = len(asked) * 10_000
            return httpx.Response(
                200,
                json=[{"id": base + i, "match_id": str(base + i)} for i in range(n)],
            )

        return httpx.Client(transport=httpx.MockTransport(handler)), asked

    def test_an_empty_page_over_played_results_is_a_failed_read(self):
        client, _ = self._client({})
        with pytest.raises(MtReadError, match="no rows"):
            fetch_mt_rows(
                "http://mt",
                "k",
                [(date(2026, 9, 6), date(2026, 9, 12))],
                expect_days={date(2026, 9, 6)},
                client=client,
            )

    def test_an_empty_page_with_nothing_played_is_fine(self):
        client, _ = self._client({})
        rows = fetch_mt_rows(
            "http://mt",
            "k",
            [(date(2026, 8, 1), date(2026, 8, 7))],
            expect_days={date(2026, 9, 6)},
            client=client,
        )
        assert rows == []

    def test_a_full_looking_page_is_split_and_reread(self):
        client, asked = self._client(
            {
                "2026-09-06..2026-09-12": MT_SPLIT_AT,
                "2026-09-06..2026-09-09": 300,
                "2026-09-10..2026-09-12": 200,
            }
        )
        rows = fetch_mt_rows(
            "http://mt", "k", [(date(2026, 9, 6), date(2026, 9, 12))], client=client
        )
        assert asked == [
            ("2026-09-06", "2026-09-12"),
            ("2026-09-06", "2026-09-09"),
            ("2026-09-10", "2026-09-12"),
        ]
        assert len(rows) == 500

    def test_a_single_full_looking_day_is_kept(self):
        client, _ = self._client({"2026-09-06..2026-09-06": MT_SPLIT_AT})
        rows = fetch_mt_rows(
            "http://mt", "k", [(date(2026, 9, 6), date(2026, 9, 6))], client=client
        )
        assert len(rows) == MT_SPLIT_AT

    def test_a_single_day_at_the_cap_is_still_an_error(self):
        client, _ = self._client({"2026-09-06..2026-09-06": MT_PAGE_CAP})
        with pytest.raises(MtPageFull):
            fetch_mt_rows(
                "http://mt", "k", [(date(2026, 9, 6), date(2026, 9, 6))], client=client
            )


def test_a_feed_key_that_could_not_be_read_is_not_mt_only():
    # The fixture is in the feed, just unusable (no club name).
    assert diff([], [_row("31000")], feed_keys={"31000"}) == []
    assert [g.action for g in diff([_event()], [_row("31000", id=9)])] == [
        "create",
        "report",
    ]


class TestTriage:
    def test_splits_sendable_from_needs_a_person(self):
        gaps = diff(
            [
                _event("1"),
                _event("2", division=None),
                _event("3", match_date=PLACEHOLDER, on_placeholder=True),
            ],
            [],
        )
        plan = triage(g for g in gaps if g.action == "create")
        assert [g.game_key for g in plan.send] == ["1"]
        assert [g.game_key for g in plan.no_bracket] == ["2"]
        assert [g.game_key for g in plan.placeholder] == ["3"]


# MarkdownV2 reserves these; every one must be backslash-escaped outside the
# * and _ markers this report uses for bold and italics, or Telegram rejects
# the whole message with a 400.
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


class TestCompletenessReportIsValidMarkdownV2:
    from src.orchestrator.report import build_completeness_report as build

    BASE = {
        "env": "prod",
        "found": {("Flex", "Southwest (North)", "U15"): 2},
        "game_keys": ["26363", "26364"],
        "still_missing": [],
        "submitted": 2,
        "send_failed": [],
        "no_bracket": [],
        "placeholder": [],
    }

    @pytest.mark.parametrize(
        "overrides",
        [
            {"repeats": []},
            {"repeats": ["26363"]},
            {"repeats": [], "refused": "250 results to send, more than 200."},
            {
                "repeats": [],
                "send_failed": ["26364"],
                "no_bracket": ["1-2"],
                "placeholder": ["28249"],
                "still_missing": ["26363"],
            },
            {"repeats": [], "confirmed": False},
        ],
    )
    def test_every_variant(self, overrides):
        message = type(self).build(**{**self.BASE, **overrides})
        assert _unescaped(message) == []

    def test_the_check_catches_an_unescaped_header(self):
        assert _unescaped("⚠️ *2 official result(s) were not in MT*")
