"""The assist tournament source (SB-1746).

No tournament has been published on the assist platform, so there is no real
payload to save. ``FEST`` below has the shape of the live v2 league document
(``V2_STANDINGS`` in test_assist_client.py) with invented stage and bracket
names — which is exactly the part that cannot be known yet, and what the
"unknown stage" tests pin down.
"""

from datetime import date, datetime, timezone

import httpx
import pytest

from src.models.tournament import TournamentContext, TournamentMatch
from src.scraper.assist_client import AssistClient
from src.scraper.tournament import assist_event
from src.scraper.tournament.assist_event import (
    AssistEventSource,
    brackets_by_event,
    stage_round_label,
)

pytestmark = pytest.mark.usefixtures("no_network")

KEY = "mls-next-fest-26-27"
START, END = date(2026, 8, 1), date(2027, 7, 15)
ALL_AGES = ["U13", "U14", "U15", "U16", "U17", "U19"]
CTX = TournamentContext(tournament_id=12)
NOW = datetime(2026, 12, 20, tzinfo=timezone.utc)


def _event(event_id, game_key, bracket_id, **overrides) -> dict:
    event = {
        "id": event_id,
        "game_key": game_key,
        "start_time": "2026-12-05T16:30:00Z",
        "local_timezone": "America/Phoenix",
        "home_squad_id": 100,
        "away_squad_id": 101,
        "home_squad_name": "U15",
        "away_squad_name": "U15",
        "competition_id": 1,
        "competition_bracket_id": bracket_id,
        "completed": True,
        "home_organisation_id": 10,
        "away_organisation_id": 11,
        "home_score": 2,
        "away_score": 1,
        "home_penalty_shootout_score": 0,
        "away_penalty_shootout_score": 0,
        "event_location_id": 95,
    }
    event.update(overrides)
    return event


FEST = {
    "version": 2,
    "synced_at": "2026-12-06T01:20:09Z",
    "competition_season": {
        "name": "Fest 26/27",
        "key": KEY,
        "competitions": [
            {"id": 1, "name": "HD Group Play"},
            {"id": 2, "name": "GA Cup Qualifier"},
        ],
        "age_groups": [{"id": 43, "name": "U13"}, {"id": 44, "name": "U15"}],
        "organisations": [
            {"id": 10, "name": "Miami Futbol Academy Rush", "logo_url": None},
            {"id": 11, "name": "The Football Academy", "logo_url": None},
        ],
        "event_locations": [{"id": 95, "name": "9 - Arizona Athletic Grounds"}],
        "competition_season_stages": [
            {
                "id": 1,
                "name": "Group Play",
                "competition_brackets": [
                    {
                        "id": 501,
                        "name": "A",
                        "age_group_id": 43,
                        "standings": [{"squad_id": 100}, {"squad_id": 101}],
                    }
                ],
            },
            {
                "id": 2,
                "name": "Round of 16",
                "competition_brackets": [
                    {"id": 502, "name": "Playoff", "age_group_id": 44, "standings": []}
                ],
            },
            {
                # A name nobody has seen: the seam under test.
                "id": 3,
                "name": "Knockout Stage",
                "competition_brackets": [
                    {"id": 503, "name": "Playoff", "age_group_id": 44, "standings": []}
                ],
            },
        ],
        "events": [
            _event(1, "40001", 501, home_squad_name="U13", away_squad_name="U13"),
            _event(
                2,
                "40002",
                502,
                competition_id=2,
                start_time="2026-12-12T01:00:00Z",
                home_score=1,
                away_score=1,
                home_penalty_shootout_score=4,
                away_penalty_shootout_score=3,
            ),
            _event(3, "40003", 503, competition_id=2),
            _event(
                4,
                "40004",
                501,
                home_squad_name="U13",
                away_squad_name="U13",
                start_time="2026-12-13T17:00:00Z",
                completed=False,
                home_score=None,
                away_score=None,
            ),
        ],
    },
}


def _source(payload=FEST, calls=None, **kwargs) -> AssistEventSource:
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request.url.path)
        if isinstance(payload, httpx.Response):
            return payload
        if callable(payload):
            return payload(request)
        return httpx.Response(200, json=payload)

    client = AssistClient(
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    return AssistEventSource(KEY, client=client, **kwargs)


async def _by_key(source=None, ages=ALL_AGES, start=START, end=END):
    source = source or _source()
    matches = await source.fetch(ages, start, end)
    return source, {m.source_match_id: m for m in matches}


class TestStageSeam:
    @pytest.mark.parametrize(
        ("stage", "label"),
        [
            ("Group Play", "Group Play"),
            ("round of 16", "Round of 16"),
            ("  Semi-Final ", "Semi-Final"),
            ("QUARTERFINAL", "QuarterFinal"),
        ],
    )
    def test_a_stage_named_like_a_known_label_is_that_label(self, stage, label):
        assert stage_round_label(stage) == label

    @pytest.mark.parametrize(
        "stage", ["Knockout Stage", "League", "Flex", "Playoffs", "", None]
    )
    def test_any_other_stage_is_not_guessed(self, stage):
        assert stage_round_label(stage) is None

    def test_a_stage_can_be_taught(self, monkeypatch):
        monkeypatch.setitem(
            assist_event.ASSIST_STAGE_LABELS, "knockout - last 16", "Round of 16"
        )
        assert stage_round_label("Knockout -  Last 16") == "Round of 16"

    def test_nothing_is_taught_yet(self):
        # Filled in from the first real tournament feed, not before.
        assert assist_event.ASSIST_STAGE_LABELS == {}


class TestFetch:
    async def test_it_reads_the_standings_document_for_the_key(self):
        calls: list[str] = []
        await _source(calls=calls).fetch(ALL_AGES, START, END)
        assert calls == [f"/data/standings/{KEY}.json"]

    async def test_a_match_in_full(self):
        _, matches = await _by_key()
        assert matches["40002"].model_dump() == {
            "source_match_id": "40002",
            "age_group": "U15",
            "home_team": "Miami Futbol Academy Rush",
            "away_team": "The Football Academy",
            # 01:00Z on the 12th is 18:00 on the 11th in Mesa.
            "kickoff_local": datetime(2026, 12, 11, 18, 0),
            "kickoff_utc": datetime(2026, 12, 12, 1, 0, tzinfo=timezone.utc),
            "location": "9 - Arizona Athletic Grounds",
            "home_score": 1,
            "away_score": 1,
            "home_penalty_score": 4,
            "away_penalty_score": 3,
            "competition": "GA Cup Qualifier",
            "source_division": "Playoff",
            "source_round_label": "Round of 16",
            "bracket_position": None,
        }

    async def test_group_and_round_come_from_bracket_and_stage(self):
        _, matches = await _by_key()
        message = matches["40001"].to_message(CTX, now=NOW)
        assert message.competition == "HD Group Play"
        assert message.tournament_group == "A"
        assert message.tournament_round == "group_stage"
        assert message.league == "Homegrown"
        assert message.external_match_id == "40001"

    async def test_zeros_are_no_shootout(self):
        _, matches = await _by_key()
        assert matches["40001"].home_penalty_score is None

    async def test_an_unplayed_fixture(self):
        _, matches = await _by_key()
        message = matches["40004"].to_message(
            CTX, now=datetime(2026, 12, 13, 16, 0, tzinfo=timezone.utc)
        )
        assert message.match_status == "scheduled"
        assert message.home_score is None
        assert message.scheduled_kickoff == datetime(
            2026, 12, 13, 17, 0, tzinfo=timezone.utc
        )

    async def test_an_unknown_stage_sends_no_round_and_is_reported(self):
        source, matches = await _by_key()
        match = matches["40003"]
        assert match.source_round_label is None
        assert match.source_division == "Playoff"
        assert match.to_message(CTX, now=NOW).tournament_round is None
        assert source.unmapped == {"stage 'Knockout Stage'": 1}
        # ...and the mapping says so too, in the command's summary.
        assert match.mapped().unmapped[0].startswith("no round")

    async def test_age_groups_are_filtered(self):
        _, matches = await _by_key(ages=["U13"])
        assert sorted(matches) == ["40001", "40004"]

    async def test_the_window_is_the_venues_local_date(self):
        # 40002 kicks off 01:00Z on the 12th: the 11th in Mesa.
        _, on_the_11th = await _by_key(start=date(2026, 12, 11), end=date(2026, 12, 11))
        _, on_the_12th = await _by_key(start=date(2026, 12, 12), end=date(2026, 12, 12))
        assert sorted(on_the_11th) == ["40002"]
        assert on_the_12th == {}

    async def test_an_event_with_no_zone_uses_the_tournaments(self):
        payload = {
            "competition_season": {
                **FEST["competition_season"],
                "events": [
                    _event(
                        2,
                        "40002",
                        502,
                        start_time="2026-12-12T01:00:00Z",
                        local_timezone=None,
                    )
                ],
            }
        }
        _, matches = await _by_key(_source(payload))
        assert matches["40002"].kickoff_local == datetime(2026, 12, 11, 18, 0)

    async def test_the_age_group_falls_back_to_the_squad_name(self):
        season = FEST["competition_season"]
        payload = {
            "competition_season": {
                **season,
                "events": [
                    *season["events"],
                    # In a competition the stages know, but in no bracket.
                    _event(
                        9,
                        "40009",
                        None,
                        home_squad_name="U16 AD",
                        away_squad_name="U16 AD",
                    ),
                ],
            }
        }
        source, matches = await _by_key(_source(payload))
        assert matches["40009"].age_group == "U16"
        assert matches["40009"].source_division is None
        assert matches["40009"].to_message(CTX, now=NOW).tournament_round is None

    @pytest.mark.parametrize("name", ["Under 15", "U-13"])
    async def test_an_age_group_named_differently_is_reported_not_dropped(self, name):
        season = FEST["competition_season"]
        payload = {
            "competition_season": {
                **season,
                "age_groups": [{"id": 43, "name": name}, {"id": 44, "name": name}],
            }
        }
        source, matches = await _by_key(_source(payload))
        assert matches == {}
        assert source.unmapped[f"age group {name!r}"] == 4

    async def test_a_known_age_group_that_was_not_asked_for_is_not_a_finding(self):
        source, matches = await _by_key(ages=["U19"])
        assert matches == {}
        assert source.unmapped == {}

    async def test_a_feed_that_is_not_published_fails_every_age_group(self):
        shell = httpx.Response(200, text="<!doctype html><html></html>")
        source = _source(shell)
        assert await source.fetch(["U13", "U15"], START, END) == []
        assert set(source.failures) == {"U13", "U15"}
        assert "not published" in source.failures["U13"]

    async def test_a_document_without_stages_still_gives_fixtures(self):
        season = FEST["competition_season"]
        organisations = {o["id"]: o for o in season["organisations"]}

        def handler(request: httpx.Request) -> httpx.Response:
            if "/data/standings/" in request.url.path:
                return httpx.Response(
                    200, json={"competition_season": {"competition_brackets": []}}
                )
            raw = season["events"][0]
            return httpx.Response(
                200,
                json={
                    "events": [
                        {
                            **raw,
                            "competition": {"id": 1, "name": "HD Group Play"},
                            "home_organisation": organisations[10],
                            "away_organisation": organisations[11],
                        }
                    ]
                },
            )

        source, matches = await _by_key(_source(handler))
        assert sorted(matches) == ["40001"]
        assert matches["40001"].source_division is None
        assert source.unmapped == {
            "standings document has no stages: no group or round": 1
        }

    async def test_the_document_can_be_kept(self, tmp_path):
        await _source(save_raw=tmp_path).fetch(ALL_AGES, START, END)
        assert (tmp_path / f"assist_{KEY}.json").exists()

    def test_brackets_by_event(self):
        brackets = brackets_by_event(FEST)
        assert brackets[2].model_dump() == {
            "stage": "Round of 16",
            "name": "Playoff",
            "age_group": "U15",
        }

    def test_the_bare_game_key_is_the_id(self):
        assert AssistEventSource(KEY).id_prefix == ""
        assert AssistEventSource(KEY).name == "assist"


class TestSameOutputAsModular11:
    """Swap the source and the message does not change, bar the id."""

    async def test_the_same_fixture_from_either_source(self):
        _, matches = await _by_key()
        from_assist = matches["40002"].to_message(CTX, now=NOW)

        from_modular11 = TournamentMatch(
            source_match_id="16416",
            age_group="U15",
            home_team="Miami Futbol Academy Rush",
            away_team="The Football Academy",
            kickoff_local=datetime(2026, 12, 11, 18, 0),
            location="9 - Arizona Athletic Grounds",
            home_score=1,
            away_score=1,
            home_penalty_score=4,
            away_penalty_score=3,
            competition="GA Cup Qualifier",
            source_division="Playoff",
            source_round_label="Round of 16",
        ).to_message(TournamentContext(tournament_id=12, id_prefix="m11-75-"), now=NOW)

        left = from_assist.model_dump(mode="json")
        right = from_modular11.model_dump(mode="json")
        assert left.pop("external_match_id") == "40002"
        assert right.pop("external_match_id") == "m11-75-16416"
        assert left == right
