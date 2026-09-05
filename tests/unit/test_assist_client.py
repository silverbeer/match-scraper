"""Unit tests for the Kitman assist feed client (SB-818)."""

from datetime import date, datetime, timezone

import httpx
import pytest
from freezegun import freeze_time

from src.scraper.assist_client import (
    AssistClient,
    AssistEvent,
    AssistFeedError,
    AssistIndex,
    feed_key,
    fetch_matches,
    league_feeds,
    season_suffix,
)

# Field-for-field copies of live payloads captured on 2026-08-24, trimmed to the
# teams and fixtures each test needs.

STANDINGS_PAYLOAD = {
    "competition_season": {
        "name": "League 26/27",
        "key": "mls-next-league-26-27",
        "competition_brackets": [
            {
                "id": 69,
                "name": "Florida",
                "age_group": {"id": 37, "name": "U14"},
                "standings": [
                    {
                        "position": 1,
                        "team": {
                            "organisation_id": 1367,
                            "squad_id": 5946,
                            "name": "Athletum FC Academy",
                        },
                    },
                    {
                        "position": 2,
                        "team": {
                            "organisation_id": 1345,
                            "squad_id": 5748,
                            "name": "South Florida Football Academy",
                        },
                    },
                ],
            },
            {
                "id": 68,
                "name": "Florida",
                "age_group": {"id": 36, "name": "U13"},
                "standings": [
                    {"team": {"squad_id": 5945, "name": "Athletum FC Academy"}},
                    {"team": {"squad_id": 5747, "name": "South Florida FA"}},
                ],
            },
            {
                "id": 41,
                "name": "Northeast",
                "age_group": {"id": 37, "name": "U14"},
                "standings": [
                    {"team": {"squad_id": 6001, "name": "Oakwood SC"}},
                    {"team": {"squad_id": 6002, "name": "IFA"}},
                ],
            },
        ],
    }
}

# Two Florida U14 fixtures a month apart, one Florida U13, one Northeast U14.
SCHEDULE_PAYLOAD = {
    "synced_at": "2026-08-24T11:50:08Z",
    "linked_competition_seasons": [
        {"name": "League 26/27", "key": "mls-next-league-26-27"}
    ],
    "events": [
        {
            "id": 5737160,
            "game_key": "26030",
            "start_time": "2026-09-05T13:00:00Z",
            "local_timezone": "America/New_York",
            "home_squad_id": 5748,
            "away_squad_id": 5946,
            "home_squad_name": "U14",
            "away_squad_name": "U14",
            "competition": {"id": 1605, "name": "League"},
            "competition_bracket_id": None,
            "completed": False,
            "home_organisation": {
                "id": 1345,
                "name": "South Florida Football Academy",
                "logo_full_path": "https://kitman.imgix.net/southfloridafa/crest.png",
            },
            "away_organisation": {
                "id": 1367,
                "name": "Athletum FC Academy",
                "logo_full_path": "https://kitman.imgix.net/athletumfc/logo.png",
            },
            "home_score": None,
            "away_score": None,
            "home_penalty_shootout_score": None,
            "away_penalty_shootout_score": None,
            "event_location": {"id": 279, "name": "Loggers Run Park - Field # 1"},
            "division": {"id": 2, "name": "MLS Next"},
            "round_number": None,
        },
        {
            "id": 5737999,
            "game_key": "26099",
            "start_time": "2026-10-10T16:00:00Z",
            "local_timezone": "America/New_York",
            "home_squad_id": 5946,
            "away_squad_id": 5748,
            "home_squad_name": "U14",
            "away_squad_name": "U14",
            "competition": {"id": 1605, "name": "League"},
            "completed": True,
            "home_organisation": {"id": 1367, "name": "Athletum FC Academy"},
            "away_organisation": {
                "id": 1345,
                "name": "South Florida Football Academy",
            },
            "home_score": 3,
            "away_score": 1,
            "event_location": {"id": 280, "name": "Loggers Run Park - Field # 2"},
            "division": {"id": 2, "name": "MLS Next"},
        },
        {
            "id": 5737161,
            "game_key": "26029",
            "start_time": "2026-09-05T13:00:00Z",
            "local_timezone": "America/New_York",
            "home_squad_id": 5747,
            "away_squad_id": 5945,
            "home_squad_name": "U13",
            "away_squad_name": "U13",
            "competition": {"id": 1605, "name": "League"},
            "completed": False,
            "home_organisation": {"id": 1345, "name": "South Florida FA"},
            "away_organisation": {"id": 1367, "name": "Athletum FC Academy"},
            "home_score": None,
            "away_score": None,
            "event_location": {"id": 279, "name": "Loggers Run Park - Field # 1"},
            "division": {"id": 2, "name": "MLS Next"},
        },
        {
            "id": 5740000,
            "game_key": "27001",
            "start_time": "2026-09-12T15:00:00Z",
            "local_timezone": "America/New_York",
            "home_squad_id": 6001,
            "away_squad_id": 6002,
            "home_squad_name": "U14",
            "away_squad_name": "U14",
            "competition": {"id": 1605, "name": "League"},
            "completed": False,
            "home_organisation": {"id": 900, "name": "Oakwood SC"},
            "away_organisation": {"id": 901, "name": "IFA"},
            "home_score": None,
            "away_score": None,
            "event_location": {"id": 500, "name": "Oakwood Field 1"},
            "division": {"id": 2, "name": "MLS Next"},
        },
    ],
}

# The SPA shell an unknown competition-season key answers with — a 200, not a 404.
SPA_SHELL = (
    '<!doctype html><html lang="en"><head><meta charset="utf-8"/>'
    "<title>League Viewer</title></head><body><div id=root></div></body></html>"
)


def make_client(handler, **kwargs) -> AssistClient:
    """An AssistClient wired to an in-process transport."""
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport)
    return AssistClient(season_year=2026, client=http, **kwargs)


def feed_handler(calls: list[str] | None = None):
    """Serve both live feeds, recording every path requested."""

    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request.url.path)
        if "/data/standings/" in request.url.path:
            return httpx.Response(200, json=STANDINGS_PAYLOAD)
        if "/data/schedule/" in request.url.path:
            return httpx.Response(200, json=SCHEDULE_PAYLOAD)
        return httpx.Response(404)

    return handler


class TestSeasonKeys:
    """Feed keys are derived from the season, never pinned."""

    @pytest.mark.parametrize(
        ("year", "expected"),
        [(2026, "26-27"), (2027, "27-28"), (2029, "29-30"), (2099, "99-00")],
    )
    def test_season_suffix(self, year: int, expected: str) -> None:
        assert season_suffix(year) == expected

    def test_feed_keys_match_live_platform(self) -> None:
        assert feed_key("league", 2026) == "mls-next-league-26-27"
        assert feed_key("flex", 2026) == "mls-next-flex-26-27"
        assert feed_key("academy", 2026) == "mls-next-2-academy-division-26-27"

    def test_unknown_feed_rejected(self) -> None:
        with pytest.raises(AssistFeedError, match="Unknown feed"):
            feed_key("reserves", 2026)

    def test_league_feeds(self) -> None:
        assert league_feeds("Homegrown") == ("league",)
        assert league_feeds("Academy") == ("academy",)

    def test_unknown_league_rejected(self) -> None:
        with pytest.raises(AssistFeedError, match="Unknown league"):
            league_feeds("Sunday Beer League")


class TestAssistIndex:
    """The standings feed is the only source of conference membership."""

    def test_brackets_keyed_by_division_and_age(self) -> None:
        index = AssistIndex.from_standings("k", STANDINGS_PAYLOAD)
        assert index.squads("Florida", "U14") == frozenset({5748, 5946})
        assert index.squads("Florida", "U13") == frozenset({5747, 5945})
        assert index.squads("Northeast", "U14") == frozenset({6001, 6002})

    def test_unknown_bracket_is_empty_not_an_error(self) -> None:
        index = AssistIndex.from_standings("k", STANDINGS_PAYLOAD)
        assert index.squads("Florida", "U19") == frozenset()
        assert index.squads("Atlantis", "U14") == frozenset()

    def test_divisions_and_age_groups(self) -> None:
        index = AssistIndex.from_standings("k", STANDINGS_PAYLOAD)
        assert index.divisions() == ["Florida", "Northeast"]
        assert index.age_groups() == ["U13", "U14"]
        assert index.age_groups("Northeast") == ["U14"]

    def test_a_squad_may_sit_in_two_brackets(self) -> None:
        """FC Dallas U17 is in both Frontier and Southeast (Pro Player Pathway)."""
        payload = {
            "competition_season": {
                "competition_brackets": [
                    {
                        "name": "Frontier",
                        "age_group": {"name": "U17"},
                        "standings": [{"team": {"squad_id": 5804}}],
                    },
                    {
                        "name": "Southeast (Pro Player Pathway)",
                        "age_group": {"name": "U17"},
                        "standings": [{"team": {"squad_id": 5804}}],
                    },
                ]
            }
        }
        index = AssistIndex.from_standings("k", payload)
        assert 5804 in index.squads("Frontier", "U17")
        assert 5804 in index.squads("Southeast (Pro Player Pathway)", "U17")

    def test_bracketless_standings_rejected(self) -> None:
        with pytest.raises(AssistFeedError, match="declared no brackets"):
            AssistIndex.from_standings("k", {"competition_season": {}})

    def test_incomplete_brackets_skipped(self) -> None:
        payload = {
            "competition_season": {
                "competition_brackets": [
                    {"name": "Florida", "standings": [{"team": {"squad_id": 1}}]},
                    {"age_group": {"name": "U14"}, "standings": []},
                    {
                        "name": "Northeast",
                        "age_group": {"name": "U14"},
                        "standings": [{"team": {"squad_id": 2}}, {"team": {}}],
                    },
                ]
            }
        }
        index = AssistIndex.from_standings("k", payload)
        assert index.divisions() == ["Northeast"]
        assert index.squads("Northeast", "U14") == frozenset({2})


# The payloads below were captured on 2026-08-24 and carry that week's fixture
# dates. Match.match_status is computed against the wall clock, so without a
# frozen one these assertions decay from "scheduled" to "tbd" the moment those
# dates pass — which is exactly what happened on 2026-09-05 (SB-1017). Freeze
# to the capture date so the tests keep asking the question they were written
# to ask.
@freeze_time("2026-08-24T12:00:00Z")
class TestAssistEvent:
    """Field mapping onto the scraper's Match model."""

    def test_local_datetime_uses_venue_timezone(self) -> None:
        event = AssistEvent.model_validate(SCHEDULE_PAYLOAD["events"][0])
        # 13:00 UTC in New York in September is 9am EDT.
        assert event.local_datetime == datetime(2026, 9, 5, 9, 0)
        assert event.local_datetime.tzinfo is None

    def test_unknown_timezone_falls_back_to_utc(self) -> None:
        raw = dict(SCHEDULE_PAYLOAD["events"][0], local_timezone="Mars/Olympus")
        assert AssistEvent.model_validate(raw).local_datetime == datetime(
            2026, 9, 5, 13, 0
        )

    def test_missing_timezone_falls_back_to_utc(self) -> None:
        raw = dict(SCHEDULE_PAYLOAD["events"][0], local_timezone=None)
        assert AssistEvent.model_validate(raw).local_datetime == datetime(
            2026, 9, 5, 13, 0
        )

    def test_to_match_uses_game_key_as_match_id(self) -> None:
        match = AssistEvent.model_validate(SCHEDULE_PAYLOAD["events"][0]).to_match()
        assert match.match_id == "26030"
        assert match.home_team == "South Florida Football Academy"
        assert match.away_team == "Athletum FC Academy"
        assert match.location == "Loggers Run Park - Field # 1"
        assert match.competition == "League"
        assert match.home_score is None
        assert match.match_status == "scheduled"

    def test_to_match_carries_scores(self) -> None:
        raw = dict(SCHEDULE_PAYLOAD["events"][1], start_time="2020-10-10T16:00:00Z")
        match = AssistEvent.model_validate(raw).to_match()
        assert (match.home_score, match.away_score) == (3, 1)
        assert match.has_score()
        assert match.match_status == "completed"

    def test_a_played_fixture_still_dated_ahead_reads_as_scheduled(self) -> None:
        """Match.match_status is driven by the clock, not the feed's ``completed``."""
        match = AssistEvent.model_validate(SCHEDULE_PAYLOAD["events"][1]).to_match()
        assert match.has_score()
        assert match.match_status == "scheduled"

    def test_to_match_rejects_a_fixture_with_no_club(self) -> None:
        raw = dict(SCHEDULE_PAYLOAD["events"][0], away_organisation=None)
        with pytest.raises(AssistFeedError, match="missing a club name"):
            AssistEvent.model_validate(raw).to_match()

    def test_unknown_upstream_fields_are_ignored(self) -> None:
        raw = dict(SCHEDULE_PAYLOAD["events"][0], broadcast_partner="Apple TV")
        assert AssistEvent.model_validate(raw).game_key == "26030"


@pytest.mark.asyncio
class TestAssistClient:
    """Fetching, filtering and caching against a mocked transport."""

    async def test_filters_to_the_requested_bracket(self) -> None:
        async with make_client(feed_handler()) as client:
            matches = await client.get_matches(division="Florida", age_group="U14")
        assert [m.match_id for m in matches] == ["26030", "26099"]

    async def test_other_divisions_and_age_groups_excluded(self) -> None:
        async with make_client(feed_handler()) as client:
            northeast = await client.get_matches(division="Northeast", age_group="U14")
            u13 = await client.get_matches(division="Florida", age_group="U13")
        assert [m.match_id for m in northeast] == ["27001"]
        assert [m.match_id for m in u13] == ["26029"]

    async def test_date_window_is_inclusive_and_local(self) -> None:
        async with make_client(feed_handler()) as client:
            window = await client.get_matches(
                division="Florida",
                age_group="U14",
                start_date=date(2026, 9, 5),
                end_date=date(2026, 9, 5),
            )
        assert [m.match_id for m in window] == ["26030"]

    async def test_window_excludes_fixtures_outside_it(self) -> None:
        async with make_client(feed_handler()) as client:
            empty = await client.get_matches(
                division="Florida",
                age_group="U14",
                start_date=date(2026, 9, 6),
                end_date=date(2026, 10, 9),
            )
        assert empty == []

    async def test_open_ended_window(self) -> None:
        async with make_client(feed_handler()) as client:
            from_october = await client.get_matches(
                division="Florida", age_group="U14", start_date=date(2026, 10, 1)
            )
            until_september = await client.get_matches(
                division="Florida", age_group="U14", end_date=date(2026, 9, 30)
            )
        assert [m.match_id for m in from_october] == ["26099"]
        assert [m.match_id for m in until_september] == ["26030"]

    async def test_results_sorted_by_kickoff(self) -> None:
        async with make_client(feed_handler()) as client:
            matches = await client.get_matches(division="Florida", age_group="U14")
        assert [m.match_datetime for m in matches] == sorted(
            m.match_datetime for m in matches
        )

    async def test_feeds_downloaded_once_per_client(self) -> None:
        calls: list[str] = []
        async with make_client(feed_handler(calls)) as client:
            await client.get_matches(division="Florida", age_group="U14")
            await client.get_matches(division="Florida", age_group="U13")
            await client.get_matches(division="Northeast", age_group="U14")
        assert len(calls) == 2, calls

    async def test_unknown_bracket_returns_nothing(self) -> None:
        async with make_client(feed_handler()) as client:
            assert await client.get_matches(division="Atlantis", age_group="U14") == []

    async def test_academy_league_uses_the_academy_feed(self) -> None:
        calls: list[str] = []
        async with make_client(feed_handler(calls)) as client:
            await client.get_matches(
                division="Florida", age_group="U14", league="Academy"
            )
        assert all("academy-division-26-27" in path for path in calls), calls

    async def test_explicit_feeds_override_the_league(self) -> None:
        calls: list[str] = []
        async with make_client(feed_handler(calls)) as client:
            await client.get_matches(
                division="Florida", age_group="U14", feeds=["league", "flex"]
            )
        assert any("mls-next-flex-26-27" in path for path in calls), calls

    async def test_synced_at_exposed_for_release_detection(self) -> None:
        async with make_client(feed_handler()) as client:
            assert await client.synced_at("league") == datetime(
                2026, 8, 24, 11, 50, 8, tzinfo=timezone.utc
            )

    async def test_html_shell_is_a_loud_failure(self) -> None:
        """An unknown season key answers 200 with the SPA, not a 404."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=SPA_SHELL)

        async with make_client(handler) as client:
            with pytest.raises(AssistFeedError, match="did not return JSON"):
                await client.index("league")

    async def test_html_shell_is_not_retried(self) -> None:
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.url.path)
            return httpx.Response(200, text=SPA_SHELL)

        async with make_client(handler) as client:
            with pytest.raises(AssistFeedError):
                await client.index("league")
        assert len(calls) == 1

    async def test_transport_errors_retried_then_raised(self) -> None:
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.url.path)
            return httpx.Response(503)

        client = make_client(handler)
        client.RETRY_DELAY_BASE = 0.0
        async with client:
            with pytest.raises(AssistFeedError, match="failed after 3 attempts"):
                await client.index("league")
        assert len(calls) == 3

    async def test_a_transient_failure_recovers(self) -> None:
        attempts: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            attempts.append(1)
            if "/data/standings/" in request.url.path and len(attempts) == 1:
                return httpx.Response(500)
            if "/data/standings/" in request.url.path:
                return httpx.Response(200, json=STANDINGS_PAYLOAD)
            return httpx.Response(200, json=SCHEDULE_PAYLOAD)

        client = make_client(handler)
        client.RETRY_DELAY_BASE = 0.0
        async with client:
            matches = await client.get_matches(division="Florida", age_group="U14")
        assert [m.match_id for m in matches] == ["26030", "26099"]

    async def test_one_bad_fixture_does_not_sink_the_target(self) -> None:
        broken = dict(SCHEDULE_PAYLOAD)
        broken["events"] = [
            dict(SCHEDULE_PAYLOAD["events"][0], home_organisation=None),
            SCHEDULE_PAYLOAD["events"][1],
        ]

        def handler(request: httpx.Request) -> httpx.Response:
            if "/data/standings/" in request.url.path:
                return httpx.Response(200, json=STANDINGS_PAYLOAD)
            return httpx.Response(200, json=broken)

        async with make_client(handler) as client:
            matches = await client.get_matches(division="Florida", age_group="U14")
        assert [m.match_id for m in matches] == ["26099"]

    async def test_concurrent_targets_share_one_download(self) -> None:
        import asyncio

        calls: list[str] = []
        async with make_client(feed_handler(calls)) as client:
            await asyncio.gather(
                client.get_matches(division="Florida", age_group="U14"),
                client.get_matches(division="Florida", age_group="U13"),
                client.get_matches(division="Northeast", age_group="U14"),
            )
        assert len(calls) == 2, calls

    async def test_fetch_matches_wrapper(self, monkeypatch) -> None:
        transport = httpx.MockTransport(feed_handler())
        real_init = httpx.AsyncClient.__init__

        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = transport
            real_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)
        matches = await fetch_matches("Florida", "U14", season_year=2026)
        assert [m.match_id for m in matches] == ["26030", "26099"]
