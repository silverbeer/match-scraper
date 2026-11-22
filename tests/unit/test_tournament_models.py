"""The tournament fields on the wire, and the one message builder (SB-1746)."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.models.match_data import TOURNAMENT_FIELDS, MatchData
from src.models.tournament import TournamentContext, TournamentMatch

pytestmark = pytest.mark.usefixtures("no_network")

LEAGUE_MESSAGE = {
    "home_team": "A",
    "away_team": "B",
    "match_date": "2026-10-03",
    "season": "2026-2027",
    "age_group": "U14",
    "match_type": "League",
    "division": "Northeast",
    "division_id": 41,
    "league": "Homegrown",
    "home_score": 2,
    "away_score": 1,
    "match_status": "completed",
    "external_match_id": "100436",
    "match_time": "12:00",
    "scheduled_kickoff": "2026-10-03T16:00:00Z",
    "location": "X",
    "source": "match-scraper-agent",
}

# model_dump(mode="json") of LEAGUE_MESSAGE on main before the tournament
# fields existed, key order included.
LEAGUE_DUMP_BEFORE = {
    "home_team": "A",
    "away_team": "B",
    "match_date": "2026-10-03",
    "season": "2026-2027",
    "age_group": "U14",
    "match_type": "League",
    "match_time": "12:00",
    "scheduled_kickoff": "2026-10-03T16:00:00Z",
    "division": "Northeast",
    "division_id": 41,
    "league": "Homegrown",
    "home_score": 2,
    "away_score": 1,
    "home_penalty_score": None,
    "away_penalty_score": None,
    "match_status": "completed",
    "external_match_id": "100436",
    "location": "X",
    "notes": None,
    "source": "match-scraper-agent",
}

TOURNAMENT_MESSAGE = {
    "home_team": "Team E",
    "away_team": "Team F",
    "match_date": "2026-12-04",
    "season": "2026-2027",
    "age_group": "U15",
    "match_type": "Tournament",
    "external_match_id": "m11-75-101",
    "tournament_id": 12,
    "competition": "HD Group Play",
    "tournament_group": "A",
    "tournament_round": "group_stage",
    "tournament_round_order": 3,
}

CTX = TournamentContext(tournament_id=12, id_prefix="m11-75-")
NOW = datetime(2026, 12, 5, 18, 0, tzinfo=timezone.utc)


def _match(**overrides) -> TournamentMatch:
    fields = {
        "source_match_id": "16416",
        "age_group": "U15",
        "home_team": "Miami Futbol Academy Rush",
        "away_team": "The Football Academy",
        "kickoff_local": datetime(2026, 12, 5, 18, 0),
        "location": "9 - Arizona Athletic Grounds",
        "competition": "GA Cup Qualifier",
        "source_division": "Playoff",
        "source_round_label": "Round of 16",
    }
    fields.update(overrides)
    return TournamentMatch(**fields)


class TestMatchDataOnTheWire:
    def test_a_league_message_serialises_exactly_as_before(self):
        dumped = MatchData(**LEAGUE_MESSAGE).model_dump(mode="json")
        assert dumped == LEAGUE_DUMP_BEFORE
        assert list(dumped) == list(LEAGUE_DUMP_BEFORE)

    def test_tournament_fields_survive_the_dump_the_queue_client_publishes(self):
        dumped = MatchData(**TOURNAMENT_MESSAGE).model_dump(mode="json")
        for name in TOURNAMENT_FIELDS:
            assert dumped[name] == TOURNAMENT_MESSAGE[name]
        assert dumped["division"] is None

    def test_an_unset_tournament_field_is_sent_as_null_not_dropped(self):
        # missing-table reads null as "leave the stored value alone".
        message = {**TOURNAMENT_MESSAGE, "tournament_round_order": None}
        dumped = MatchData(**message).model_dump(mode="json")
        assert dumped["tournament_round_order"] is None

    def test_a_dumped_tournament_message_validates_again(self):
        # MatchQueueClient.submit_match re-validates the dict it is handed.
        dumped = MatchData(**TOURNAMENT_MESSAGE).model_dump(mode="json")
        assert MatchData(**dumped).model_dump(mode="json") == dumped

    def test_a_division_is_rejected(self):
        with pytest.raises(ValidationError, match="must not carry a division"):
            MatchData(**{**TOURNAMENT_MESSAGE, "division": "Northeast"})

    def test_a_missing_source_id_is_rejected(self):
        message = {**TOURNAMENT_MESSAGE, "external_match_id": None}
        with pytest.raises(ValidationError, match="requires external_match_id"):
            MatchData(**message)

    def test_any_other_match_type_is_rejected(self):
        with pytest.raises(ValidationError, match="match_type 'Tournament'"):
            MatchData(**{**TOURNAMENT_MESSAGE, "match_type": "League"})

    @pytest.mark.parametrize(
        "name", [f for f in TOURNAMENT_FIELDS if f != "tournament_id"]
    )
    def test_a_tournament_field_needs_a_tournament(self, name):
        message = {**LEAGUE_MESSAGE, name: TOURNAMENT_MESSAGE[name]}
        with pytest.raises(ValidationError, match="requires tournament_id"):
            MatchData(**message)

    @pytest.mark.parametrize(
        "round_key", ["Round of 16", "round-of-16", "_final", "16", "x" * 41]
    )
    def test_a_malformed_round_key_is_rejected(self, round_key):
        with pytest.raises(ValidationError):
            MatchData(**{**TOURNAMENT_MESSAGE, "tournament_round": round_key})

    @pytest.mark.parametrize(
        ("name", "value"), [("tournament_id", 0), ("tournament_round_order", -1)]
    )
    def test_out_of_range_numbers_are_rejected(self, name, value):
        with pytest.raises(ValidationError):
            MatchData(**{**TOURNAMENT_MESSAGE, name: value})


class TestToMessage:
    def test_the_message_missing_table_expects(self):
        message = _match(
            home_score=1, away_score=1, home_penalty_score=4, away_penalty_score=3
        ).to_message(CTX, now=NOW)

        assert message.model_dump(mode="json") == {
            "home_team": "Miami Futbol Academy Rush",
            "away_team": "The Football Academy",
            "match_date": "2026-12-05",
            "season": "2026-2027",
            "age_group": "U15",
            "match_type": "Tournament",
            "match_time": "18:00",
            # 18:00 in Arizona, which keeps no daylight time: UTC-7.
            "scheduled_kickoff": "2026-12-06T01:00:00Z",
            "division": None,
            "division_id": None,
            "league": None,
            "home_score": 1,
            "away_score": 1,
            "home_penalty_score": 4,
            "away_penalty_score": 3,
            "match_status": "completed",
            "external_match_id": "m11-75-16416",
            "location": "9 - Arizona Athletic Grounds",
            "notes": None,
            "source": "match-scraper-agent",
            "tournament_id": 12,
            "competition": "GA Cup Qualifier",
            "tournament_group": None,
            "tournament_round": "round_of_16",
            "tournament_round_order": None,
        }

    def test_team_names_are_sent_as_the_feed_has_them(self):
        name = "Intercontinental Football Academy of New England"
        assert _match(home_team=name).to_message(CTX, now=NOW).home_team == name

    def test_the_wall_clock_is_read_in_the_context_zone(self):
        ctx = TournamentContext(tournament_id=12, timezone="America/New_York")
        message = _match().to_message(ctx, now=NOW)
        assert message.match_time == "18:00"
        assert message.scheduled_kickoff == datetime(
            2026, 12, 5, 23, 0, tzinfo=timezone.utc
        )

    def test_an_exact_instant_from_the_source_wins(self):
        instant = datetime(2026, 12, 6, 0, 30, tzinfo=timezone.utc)
        message = _match(kickoff_utc=instant).to_message(CTX, now=NOW)
        assert message.scheduled_kickoff == instant
        assert message.match_time == "18:00"

    def test_midnight_means_the_time_is_not_set(self):
        message = _match(kickoff_local=datetime(2026, 12, 5)).to_message(CTX, now=NOW)
        assert message.match_date.isoformat() == "2026-12-05"
        assert message.match_time is None
        assert message.scheduled_kickoff is None

    @pytest.mark.parametrize(
        ("now", "expected"),
        [
            # Kick-off is 2026-12-06T01:00Z.
            (datetime(2026, 12, 6, 0, 59, tzinfo=timezone.utc), "scheduled"),
            (datetime(2026, 12, 6, 1, 1, tzinfo=timezone.utc), "tbd"),
        ],
    )
    def test_unscored_status_follows_the_real_instant(self, now, expected):
        assert _match().to_message(CTX, now=now).match_status == expected

    def test_an_untimed_match_is_not_overdue_until_its_day_is(self):
        match = _match(kickoff_local=datetime(2026, 12, 5))
        # The day runs 07:00Z to 07:00Z in Arizona.
        during = datetime(2026, 12, 6, 6, 0, tzinfo=timezone.utc)
        after = datetime(2026, 12, 6, 8, 0, tzinfo=timezone.utc)
        assert match.to_message(CTX, now=during).match_status == "scheduled"
        assert match.to_message(CTX, now=after).match_status == "tbd"

    def test_a_scored_match_is_completed_never_live(self):
        before_kickoff = datetime(2026, 12, 1, tzinfo=timezone.utc)
        message = _match(home_score=2, away_score=0).to_message(CTX, now=before_kickoff)
        assert message.match_status == "completed"

    @pytest.mark.parametrize(
        ("home", "away", "home_pens", "away_pens"),
        [
            (2, 1, 4, 3),  # decided in regulation
            (1, 1, 0, 0),  # the feed's "no shootout"
            (1, 1, 4, None),  # half a pair
            (None, None, 4, 3),  # no regulation score
        ],
    )
    def test_penalties_that_missing_table_would_reject_are_not_sent(
        self, home, away, home_pens, away_pens
    ):
        message = _match(
            home_score=home,
            away_score=away,
            home_penalty_score=home_pens,
            away_penalty_score=away_pens,
        ).to_message(CTX, now=NOW)
        assert message.home_penalty_score is None
        assert message.away_penalty_score is None

    def test_the_id_is_the_source_id_behind_the_context_prefix(self):
        assert _match().to_message(CTX, now=NOW).external_match_id == "m11-75-16416"
        bare = TournamentContext(tournament_id=12)
        assert _match().to_message(bare, now=NOW).external_match_id == "16416"

    def test_a_bracket_position_is_sent_only_on_a_knockout_round(self):
        knockout = _match(bracket_position=3).to_message(CTX, now=NOW)
        group = _match(
            competition="HD Group Play",
            source_division="A",
            source_round_label="Group Play",
            bracket_position=3,
        ).to_message(CTX, now=NOW)
        assert knockout.tournament_round_order == 3
        assert group.tournament_round_order is None
        assert group.tournament_group == "A"
        assert group.league == "Homegrown"

    def test_the_season_is_the_one_the_match_is_played_in(self):
        message = _match(kickoff_local=datetime(2025, 12, 12, 8, 0)).to_message(
            CTX, now=NOW
        )
        assert message.season == "2025-2026"

    def test_a_tbd_team_is_a_placeholder(self):
        assert _match().teams_known()
        assert not _match(home_team="TBD", away_team="TBD").teams_known()
        assert not _match(away_team="tbd").teams_known()

    def test_an_aware_wall_clock_is_refused(self):
        with pytest.raises(ValidationError, match="wall clock"):
            _match(kickoff_local=datetime(2026, 12, 5, 18, 0, tzinfo=timezone.utc))

    def test_an_unknown_zone_is_refused(self):
        with pytest.raises(ValidationError, match="Unknown timezone"):
            TournamentContext(tournament_id=12, timezone="America/Mesa")
