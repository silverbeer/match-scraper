"""The two submit paths must produce the same payload (SB-846).

match-scraper can send a fixture to missing-table two ways: the CLI
(`build_match_dict`, used for manual and backfill loads) and the orchestrator
(`scrape_matches`, used by the agent CronJob). Both normalise the same feed
into the same contract, and they have now drifted apart three times in two
days:

  SB-844  the CLI appended "HG" to IFA's team name; the agent did not, so the
          CLI path silently dropped every IFA Homegrown fixture
  SB-846  the CLI hardcoded match_type "League"; the agent derived it, so 68
          Flex fixtures landed in production filed as League

Each time both paths were defensible in isolation and wrong relative to each
other, and nothing compared them. That is what this file is for.
"""

from types import SimpleNamespace

import pytest

from src.cli.main import mt_match_type, normalize_team_name_for_display
from src.orchestrator.tools import _normalize_team_name

FEED_NAME = "Intercontinental Football Academy of New England"


def _cli_match_type(league: str, competition: str | None = None) -> str:
    """The CLI's real mapping, not a copy of it."""
    return mt_match_type(SimpleNamespace(competition=competition), league)


def _agent_match_type(league: str) -> str:
    """Mirror of the expression in orchestrator/tools.py."""
    return "Flex" if league == "Flex" else "League"


@pytest.mark.parametrize("league", ["Homegrown", "Academy", "Flex"])
def test_both_paths_agree_on_match_type(league):
    assert _cli_match_type(league) == _agent_match_type(league)


@pytest.mark.parametrize(
    ("competition", "expected"),
    [
        ("League", "League"),
        ("League (Pro Player Pathway)", "League"),
        ("MLS NEXT Flex", "Flex"),
    ],
)
def test_the_fixtures_own_competition_decides(competition, expected):
    """The feed states the competition per EVENT, not per target.

    MLS Next's schedule page shows it as a column, and IFA's U15 schedule
    interleaves League and Flex fixtures. Inferring from which bracket was
    scraped works only while the feeds stay disjoint; reading what the fixture
    says it is does not depend on that.
    """
    assert _cli_match_type("Homegrown", competition) == expected


def test_an_unknown_competition_falls_back_to_the_target_league():
    # A competition MLS invents next season must not become a match_type
    # missing-table has no row for. Degrading to the old behaviour is wrong
    # in a way someone will notice; inventing a type is wrong silently.
    assert _cli_match_type("Flex", "Some New Competition") == "Flex"
    assert _cli_match_type("Homegrown", "Some New Competition") == "League"


@pytest.mark.parametrize(
    ("league", "expected"),
    [("Flex", "Flex"), ("Homegrown", "League"), ("Academy", "League")],
)
def test_match_type_follows_the_competition(league, expected):
    assert _cli_match_type(league) == expected


def test_pathway_is_not_its_own_competition():
    """Pathway rides on league="Homegrown" and must stay match_type "League".

    Filing it as anything else would move ~29 pro academies' League records
    out of League, so `mt team stats <club>` — which defaults to -c League —
    would return nothing for any of them.
    """
    assert _cli_match_type("Homegrown") == "League"


@pytest.mark.parametrize("league", ["Homegrown", "Academy", "Flex"])
def test_both_paths_agree_on_team_names(league):
    # The CLI normaliser takes no league; the agent's does. They must still
    # agree for the leagues where the agent has no override.
    cli = normalize_team_name_for_display(FEED_NAME)
    agent = _normalize_team_name(FEED_NAME, league=league)
    if league == "Academy":
        # The one deliberate divergence: Academy maps to a different DB team.
        assert agent == "IFA Academy"
        assert cli == "IFA"
    else:
        assert cli == agent == "IFA"


def test_an_unmapped_team_name_passes_through_both_paths_unchanged():
    name = "Some Club With No Mapping"
    assert (
        normalize_team_name_for_display(name)
        == _normalize_team_name(name, league="Homegrown")
        == name
    )
