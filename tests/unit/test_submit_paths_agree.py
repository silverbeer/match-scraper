"""The two submit paths must produce the same payload (SB-846).

match-scraper can send a fixture to missing-table two ways: the standalone CLI
(`src/cli/main.py build_match_dict`) and the orchestrator
(`src/orchestrator/tools.py build_match_dict`, used by the pipeline,
`scrape --submit`, the audit and `backfill`). Both normalise the same feed
into the same contract, and they have now drifted apart three times in two
days:

  SB-844  the CLI appended "HG" to IFA's team name; the agent did not, so the
          CLI path silently dropped every IFA Homegrown fixture
  SB-846  the CLI hardcoded match_type "League"; the agent derived it, so 68
          Flex fixtures landed in production filed as League

Each time both paths were defensible in isolation and wrong relative to each
other, and nothing compared them. That is what this file is for.
"""

import ast
import importlib
import inspect
from types import SimpleNamespace

import pytest

from src.cli.main import mt_match_type, normalize_team_name_for_display
from src.orchestrator import tools
from src.orchestrator.tools import _normalize_team_name

FEED_NAME = "Intercontinental Football Academy of New England"


def _cli_match_type(league: str, competition: str | None = None) -> str:
    """The CLI's real mapping, not a copy of it."""
    return mt_match_type(SimpleNamespace(competition=competition), league)


def _agent_match_type(league: str) -> str:
    """The orchestrator's real mapping, not a copy of it."""
    return tools.mt_match_type(league)


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


# The modules that build a queue payload. The CLI is the standalone scraper;
# every orchestrator sender — the pipeline, `scrape --submit`, the audit and
# `backfill` — uses tools.build_match_dict (SB-1786).
BUILDERS = ["src.cli.main", "src.orchestrator.tools"]

# Orchestrator modules that send fixtures but must not build the payload.
SENDERS = ["src.orchestrator.cli", "src.orchestrator.audit.runner"]


def _payload_dicts(module_name: str, marker: str) -> list[ast.Dict]:
    module = importlib.import_module(module_name)
    tree = ast.parse(inspect.getsource(module))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Dict)
        and any(isinstance(k, ast.Constant) and k.value == marker for k in node.keys)
    ]


def _payload_keys(module_name: str, marker: str) -> set[str]:
    """Keys of the queue payload a builder constructs, read from its source.

    Parsed rather than called, so the check covers the source as written.
    """
    for node in _payload_dicts(module_name, marker):
        return {k.value for k in node.keys if isinstance(k, ast.Constant)}
    raise AssertionError(f"no payload dict containing {marker!r} in {module_name}")


@pytest.mark.parametrize("module_name", SENDERS)
def test_orchestrator_senders_use_the_one_builder(module_name):
    """Three copies of the payload drifted three times (SB-844, SB-846, and
    SB-1786: `scrape --submit` and the audit kept match_type "League" after
    the pipeline learned Flex). A sender that builds its own dict is how the
    next drift starts, so none may.
    """
    assert not _payload_dicts(module_name, "external_match_id"), (
        f"{module_name} builds its own queue payload; use tools.build_match_dict"
    )
    source = inspect.getsource(importlib.import_module(module_name))
    assert "build_match_dict(" in source


def _match(**overrides):
    from datetime import datetime

    from src.scraper.models import Match

    fields = {
        "match_id": "28630",
        "match_datetime": datetime(2026, 10, 14, 19, 0),
        "home_team": "New York Red Bulls",
        "away_team": "TSF Academy",
        "home_score": 1,
        "away_score": 1,
        "home_penalty_score": 4,
        "away_penalty_score": 3,
    }
    fields.update(overrides)
    return Match(**fields)


@pytest.mark.parametrize(
    ("league", "expected"),
    [("Flex", "Flex"), ("Homegrown", "League"), ("Academy", "League")],
)
def test_the_shared_builder_files_the_competition(league, expected):
    payload = tools.build_match_dict(
        _match(), {"league": league, "division": "Turnpike", "age_group": "U15"}
    )
    assert payload["match_type"] == expected
    assert payload["division"] == "Turnpike"
    # The shootout travels with the score.
    assert (payload["home_penalty_score"], payload["away_penalty_score"]) == (4, 3)


def test_the_shared_builder_files_an_academy_bracket_as_the_division():
    payload = tools.build_match_dict(
        _match(),
        {"league": "Academy", "conference": "New England", "age_group": "U14"},
    )
    assert payload["division"] == "New England"


def test_scrape_submit_sends_flex_as_flex(monkeypatch):
    """`scrape --target <flex> --submit` hardcoded "League" (SB-1786)."""
    from typer.testing import CliRunner

    from src.orchestrator import cli

    sent: list[dict] = []

    class FakeQueue:
        def __init__(self, **kwargs):
            pass

        def submit_match(self, match_data):
            sent.append(match_data)

    class FakeScraper:
        def __init__(self, config, headless=True):
            pass

        async def scrape_matches(self):
            return [_match()]

    monkeypatch.setattr(
        cli,
        "_target_config",
        lambda settings: {
            "u15-flex-turnpike": {
                "age_group": "U15",
                "league": "Flex",
                "division": "Turnpike",
            }
        },
    )
    monkeypatch.setattr("src.scraper.mls_scraper.MLSScraper", FakeScraper)
    monkeypatch.setattr("src.celery.queue_client.MatchQueueClient", FakeQueue)

    result = CliRunner().invoke(
        cli.app,
        [
            "scrape",
            "--target",
            "u15-flex-turnpike",
            "--from",
            "2026-10-01",
            "--to",
            "2026-10-31",
            "--submit",
        ],
    )

    assert result.exit_code == 0, result.output
    assert [m["match_type"] for m in sent] == ["Flex"]
    assert sent[0]["league"] == "Flex"
    assert sent[0]["division"] == "Turnpike"


@pytest.mark.parametrize("module_name", BUILDERS)
def test_every_submit_path_sends_the_shootout(module_name):
    """A Flex draw is decided on penalties, and every sender must say so.

    Three builders construct the queue payload, and a field added to one and
    forgotten in another is exactly how SB-844 and SB-846 happened. Compare the
    key sets rather than trusting a reviewer to notice (SB-1019).
    """
    keys = _payload_keys(module_name, "external_match_id")
    assert {"home_penalty_score", "away_penalty_score"} <= keys


@pytest.mark.parametrize("module_name", BUILDERS)
def test_every_payload_key_survives_the_wire_contract(module_name):
    """MatchData is what gets published, not the dict a builder returns.

    MatchQueueClient.submit_match validates the payload into MatchData and
    publishes the model, so Pydantic drops any key the model has no field for.
    SB-1019 added the penalty pair to all three builders, all three agreed with
    each other, and every one of them was discarded one layer down (SB-1025).
    """
    from src.models.match_data import MatchData

    keys = _payload_keys(module_name, "external_match_id")
    unknown = keys - set(MatchData.model_fields)
    assert not unknown, (
        f"{module_name} sends keys MatchData will drop: {sorted(unknown)}"
    )


@pytest.mark.parametrize("module_name", BUILDERS)
def test_every_submit_path_sends_the_utc_kickoff(module_name):
    """match_time is the venue's wall clock with no zone; missing-table read it
    as Eastern and stored Pacific kickoffs 3 h early (SB-1202). Every sender
    must carry the feed's exact instant alongside it (SB-1203).
    """
    keys = _payload_keys(module_name, "external_match_id")
    assert "scheduled_kickoff" in keys
