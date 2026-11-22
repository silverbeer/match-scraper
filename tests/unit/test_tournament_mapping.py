"""Feed values -> missing-table round key and group (SB-1746).

The census test is the one that matters next December: it holds every
combination MLS NEXT Fest 2025 used, so a rule that stops covering one of them
fails here rather than in production.
"""

import json
from pathlib import Path

import pytest

from src.models.match_data import VALID_LEAGUES
from src.scraper.assist_client import LEAGUE_FEEDS
from src.scraper.tournament.mapping import (
    KNOWN_LABELS,
    LEAGUE_BY_PREFIX,
    MT_ROUND_KEYS,
    clean_round_label,
    league_for,
    map_round,
    slugify,
)

pytestmark = pytest.mark.usefixtures("no_network")

CENSUS = json.loads(
    (Path(__file__).parent / "fixtures/modular11_event_75/census.json").read_text()
)

# Census combinations that are meant to send no round. Empty for 2025: every
# row of the event maps. Adding to this is a decision, not a fix.
NO_ROUND: set[tuple[str, str, str]] = set()


class TestCleanRoundLabel:
    @pytest.mark.parametrize("label", KNOWN_LABELS)
    def test_a_known_label_is_itself(self, label):
        assert clean_round_label(label) == label

    @pytest.mark.parametrize("label", KNOWN_LABELS)
    def test_an_address_prefix_is_stripped(self, label):
        assert (
            clean_round_label(f"1234 E  Main St,\n Mesa, AZ 85212   {label}") == label
        )

    def test_semi_final_is_not_read_as_final(self):
        assert clean_round_label("Semi-Final") == "Semi-Final"
        assert clean_round_label("Field 3 Semi-Final") == "Semi-Final"

    def test_the_label_must_end_the_text(self):
        # "Final" in the middle of something else is not a label.
        assert clean_round_label("Final whistle pending") == "Final whistle pending"

    def test_whitespace_is_collapsed_on_an_unknown_label(self):
        assert clean_round_label("  Third\xa0 Place\n") == "Third Place"

    @pytest.mark.parametrize("blank", [None, "", "   ", "\xa0"])
    def test_blank_is_blank(self, blank):
        assert clean_round_label(blank) == ""


class TestRoundRules:
    @pytest.mark.parametrize(
        ("competition", "division", "label", "expected"),
        [
            # NEXT Pro is a round robin, whatever its label says.
            ("GA Cup Qualifier", "NEXT Pro", "Group Play", "group_stage"),
            ("GA Cup Qualifier", "NEXT Pro", "Final", "group_stage"),
            # Its own final decides a placing after a round robin; the
            # knockout final is the competition's only "final".
            (
                "GA Cup Qualifier",
                "Finals",
                "Final (Child Group of NEXT Pro)",
                "placement_final",
            ),
            ("GA Cup Qualifier", "Playoff", "Round of 32", "round_of_32"),
            ("GA Cup Qualifier", "Playoff", "Round of 16", "round_of_16"),
            ("GA Cup Qualifier", "Playoff", "QuarterFinal", "quarterfinal"),
            ("GA Cup Qualifier", "Playoff", "Semi-Final", "semifinal"),
            ("GA Cup Qualifier", "Playoff", "Final", "final"),
            ("GA Cup Qualifier", "Consolation", "Consolation", "consolation"),
            ("HD Group Play", "Playoffs", "Consolation", "consolation"),
            # A "Final" after group play decides a placing, not the event.
            ("HD Group Play", "Playoffs", "Final", "placement_final"),
            ("AD Group Play", "Playoffs", "Final", "placement_final"),
            ("HD Group Play", "A", "Group Play", "group_stage"),
            ("AD Showcase", "FEST", "Showcase", "showcase"),
            ("Pro Player Pathway", "FEST", "League (Pro Player Pathway)", "showcase"),
            ("Best Of", "FEST", "Best Of", "showcase"),
        ],
    )
    def test_labelled_rows(self, competition, division, label, expected):
        mapped = map_round(competition, division, label)
        assert mapped.round_key == expected
        assert mapped.unmapped == ()

    @pytest.mark.parametrize(
        ("competition", "division", "expected"),
        [
            ("GA Cup Qualifier", "NEXT Pro", "group_stage"),
            ("GA Cup Qualifier", "Consolation", "consolation"),
            ("HD Group Play", "C", "group_stage"),
            ("AD Showcase", "FEST", "showcase"),
            ("Pro Player Pathway", "FEST", "showcase"),
            ("Best Of", "FEST", "showcase"),
            ("HD Group Play", "Playoffs", "placement_final"),
            ("AD Group Play", "Playoff", "placement_final"),
            ("HD Group Play", "Finals", "placement_final"),
        ],
    )
    def test_a_blank_label_falls_back_to_competition_and_division(
        self, competition, division, expected
    ):
        mapped = map_round(competition, division, "")
        assert mapped.round_key == expected
        assert mapped.unmapped == ()

    @pytest.mark.parametrize(
        ("competition", "division"),
        [
            ("GA Cup Qualifier", "Playoff"),  # which knockout round? unknowable
            ("GA Cup Qualifier", "Finals"),
            ("Some New Cup", "FEST"),
        ],
    )
    def test_a_blank_label_never_guesses_a_knockout_round(self, competition, division):
        mapped = map_round(competition, division, None)
        assert mapped.round_key is None
        assert len(mapped.unmapped) == 1
        assert mapped.unmapped[0].startswith("no round")

    def test_an_unrecognised_label_is_slugified_and_reported(self):
        mapped = map_round("GA Cup Qualifier", "Playoff", "Third Place Match")
        assert mapped.round_key == "third_place_match"
        assert mapped.round_key not in MT_ROUND_KEYS
        assert mapped.unmapped == ("label 'Third Place Match'",)

    def test_a_label_with_nothing_to_slugify_sends_no_round(self):
        mapped = map_round("GA Cup Qualifier", "Playoff", "1/8")
        assert mapped.round_key is None
        assert mapped.unmapped == ("label '1/8'",)

    def test_slugs_fit_the_round_key_field(self):
        slug = slugify("A Very Long Round Name That Runs On And On And On And On")
        assert len(slug) <= 40
        assert not slug.endswith("_")

    def test_round_order_is_only_for_knockout_rounds(self):
        assert map_round("GA Cup Qualifier", "Playoff", "Semi-Final").send_round_order
        assert map_round("GA Cup Qualifier", "Playoff", "Final").send_round_order
        assert not map_round("HD Group Play", "A", "Group Play").send_round_order
        assert not map_round("HD Group Play", "Playoffs", "Final").send_round_order


class TestGroup:
    @pytest.mark.parametrize("division", ["A", "T", "Z", "AA", "NEXT Pro"])
    def test_a_real_group_is_sent(self, division):
        assert map_round("HD Group Play", division, "Group Play").group == division

    @pytest.mark.parametrize(
        "division", ["FEST", "Playoff", "Playoffs", "Finals", "Consolation", "", None]
    )
    def test_a_stage_name_in_the_division_column_is_not_a_group(self, division):
        mapped = map_round("HD Group Play", division, "Group Play")
        assert mapped.group is None
        assert mapped.unmapped == ()

    def test_an_unknown_division_on_a_group_match_is_sent_raw_and_reported(self):
        mapped = map_round("HD Group Play", "Pool 3", "Group Play")
        assert mapped.round_key == "group_stage"
        assert mapped.group == "Pool 3"
        assert mapped.unmapped == ("division 'Pool 3'",)

    def test_an_unknown_division_elsewhere_is_reported_but_not_sent(self):
        mapped = map_round("AD Showcase", "Desert", "Showcase")
        assert mapped.group is None
        assert mapped.unmapped == ("division 'Desert'",)


class TestNoCompetition:
    """A group is namespaced by its competition on the receiving side."""

    @pytest.mark.parametrize("competition", [None, "", "  "])
    def test_no_group_is_sent_and_the_row_is_reported(self, competition):
        mapped = map_round(competition, "A", "Group Play")
        # HD group A and AD group A would otherwise be stored as one group.
        assert mapped.group is None
        assert "no competition: division 'A', label 'Group Play'" in mapped.unmapped

    def test_a_knockout_row_without_one_is_reported_too(self):
        mapped = map_round(None, "Playoff", "Round of 16")
        assert mapped.round_key == "round_of_16"
        assert mapped.group is None
        assert mapped.unmapped == (
            "no competition: division 'Playoff', label 'Round of 16'",
        )

    def test_nothing_at_all(self):
        mapped = map_round(None, None, None)
        assert mapped.round_key is None
        assert mapped.group is None
        assert len(mapped.unmapped) == 2


class TestOneFinalPerCompetition:
    def test_no_competition_and_age_group_has_two_finals(self):
        finals: dict[tuple[str, str], int] = {}
        for combo in CENSUS["combinations"]:
            mapped = map_round(combo["competition"], combo["division"], combo["label"])
            if mapped.round_key == "final":
                key = (combo["age_group"], combo["competition"])
                finals[key] = finals.get(key, 0) + combo["matches"]
        assert finals == {
            ("U15", "GA Cup Qualifier"): 1,
            ("U16", "GA Cup Qualifier"): 1,
        }


class TestLeague:
    @pytest.mark.parametrize(
        ("competition", "expected"),
        [
            ("HD Group Play", "Homegrown"),
            ("HD Showcase", "Homegrown"),
            ("AD Group Play", "Academy"),
            ("AD  Showcase", "Academy"),
            ("GA Cup Qualifier", None),
            ("Pro Player Pathway", None),
            ("Best Of", None),
            ("HD", None),
            ("ADVANCED Cup", None),
            (None, None),
        ],
    )
    def test_the_league_is_read_off_the_first_word(self, competition, expected):
        assert league_for(competition) == expected

    def test_only_homegrown_and_academy_are_ever_sent(self):
        # missing-table rejects the whole message for a league it does not
        # know, so these two strings are pinned, and anything else is omitted.
        assert LEAGUE_BY_PREFIX == {"HD": "Homegrown", "AD": "Academy"}
        sent = {league_for(c["competition"]) for c in CENSUS["combinations"]}
        assert sent == {"Homegrown", "Academy", None}

    def test_they_are_the_names_league_matches_are_sent_with(self):
        for league in LEAGUE_BY_PREFIX.values():
            assert league in VALID_LEAGUES
            assert league in LEAGUE_FEEDS


class TestCensus:
    """Every combination in MLS NEXT Fest 2025 still maps."""

    def test_the_census_is_the_whole_event(self):
        assert CENSUS["matches"] == 2458
        assert CENSUS["matches_by_age_group"] == {
            "U13": 356,
            "U14": 376,
            "U15": 371,
            "U16": 417,
            "U17": 464,
            "U19": 474,
        }
        assert sum(c["matches"] for c in CENSUS["combinations"]) == 2458

    @pytest.mark.parametrize(
        "combo",
        CENSUS["combinations"],
        ids=lambda c: f"{c['age_group']}/{c['competition']}/{c['division']}/{c['label']}",
    )
    def test_every_combination_maps(self, combo):
        mapped = map_round(combo["competition"], combo["division"], combo["label"])
        assert mapped.unmapped == ()
        key = (combo["competition"], combo["division"], combo["label"])
        if key in NO_ROUND:
            assert mapped.round_key is None
        else:
            assert mapped.round_key in MT_ROUND_KEYS

    def test_rounds_by_match_count(self):
        counts: dict[str, int] = {}
        for combo in CENSUS["combinations"]:
            key = map_round(
                combo["competition"], combo["division"], combo["label"]
            ).round_key
            counts[key] = counts.get(key, 0) + combo["matches"]
        assert counts == {
            "showcase": 1574,
            "group_stage": 556,
            "consolation": 220,
            "placement_final": 46,
            "round_of_32": 32,
            "round_of_16": 16,
            "quarterfinal": 8,
            "semifinal": 4,
            "final": 2,
        }

    def test_group_is_sent_exactly_for_group_stage(self):
        for combo in CENSUS["combinations"]:
            mapped = map_round(combo["competition"], combo["division"], combo["label"])
            assert (mapped.group is not None) == (mapped.round_key == "group_stage")
