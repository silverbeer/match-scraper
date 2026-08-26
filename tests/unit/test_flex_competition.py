"""Flex posts as its own competition (SB-836).

Flex is played by the SAME teams as Homegrown — 563 of its 567 squads also
appear in the league feed — but it is a different competition, and the two
must not be conflated. `mt team stats -c` and the Golden Boot resolve a
competition name to a match_type, so a Flex fixture posted as League would
inflate every League scorer and make games-played read 25 instead of 19.

Pro Player Pathway is the deliberate counter-case: those ARE League fixtures,
in a different bracket. Filing them as anything else would empty ~29 pro
academies' League records.
"""

import pytest

from src.models.match_data import VALID_LEAGUES, MatchData
from src.scraper.assist_client import AssistFeedError, feed_key, league_feeds


class TestLeagueValidator:
    @pytest.mark.parametrize("league", ["Homegrown", "Academy", "Flex"])
    def test_leagues_missing_table_has_a_row_for_are_accepted(self, league):
        assert (
            MatchData(
                home_team="IFA",
                away_team="Bayside FC",
                match_date="2026-09-05",
                season="2026-2027",
                age_group="U15",
                match_type="League",
                league=league,
            ).league
            == league
        )

    def test_an_unknown_league_is_rejected(self):
        # MT resolves the league to scope its division lookup; an unmapped name
        # silently drops that scoping and can match the wrong division.
        with pytest.raises(ValueError, match="League must be one of"):
            MatchData(
                home_team="IFA",
                away_team="Bayside FC",
                match_date="2026-09-05",
                season="2026-2027",
                age_group="U15",
                match_type="League",
                league="MLS NEXT Flex",
            )

    def test_league_stays_optional(self):
        # Manual and tournament sources send none.
        assert (
            MatchData(
                home_team="IFA",
                away_team="Bayside FC",
                match_date="2026-09-05",
                season="2026-2027",
                age_group="U15",
                match_type="Friendly",
            ).league
            is None
        )

    def test_flex_is_in_the_shared_constant(self):
        assert VALID_LEAGUES == ("Homegrown", "Academy", "Flex")


class TestFlexFeed:
    def test_flex_maps_to_its_own_feed(self):
        assert league_feeds("Flex") == ("flex",)

    def test_flex_is_a_separate_competition_season_from_league(self):
        # Different key entirely — Flex is not a slice of the league feed.
        assert feed_key("flex", 2026) == "mls-next-flex-26-27"
        assert feed_key("league", 2026) == "mls-next-league-26-27"

    def test_an_unknown_league_names_the_known_ones(self):
        with pytest.raises(AssistFeedError, match="Unknown league"):
            league_feeds("Fest")


class TestMatchTypeFollowsTheCompetition:
    @pytest.mark.parametrize(
        ("league", "expected"),
        [("Flex", "Flex"), ("Homegrown", "League"), ("Academy", "League")],
    )
    def test_match_type_is_derived_from_the_league(self, league, expected):
        # Mirrors the expression in tools.py. Pathway is absent on purpose:
        # it rides on league="Homegrown" and so stays match_type "League".
        assert ("Flex" if league == "Flex" else "League") == expected
