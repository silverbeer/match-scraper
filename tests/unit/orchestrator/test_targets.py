"""Targets come from the feed, not from a list somebody maintained (SB-1024).

The fixtures under ``fixtures/`` are slices of the real standings feeds,
recorded on 2026-09-07 and trimmed to a handful of brackets with two squads
each. They keep the real conference names — including the ones that collide
across leagues, and the Pathway brackets that exist at U16/U17 but not below —
because those are the shapes the naming rules have to survive.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.orchestrator.targets import build_targets, load_targets, slug, target_key
from src.scraper.assist_client import AssistIndex

FIXTURES = Path(__file__).parent / "fixtures"


def _index(feed: str) -> AssistIndex:
    payload = json.loads((FIXTURES / f"standings_{feed}.json").read_text())
    return AssistIndex.from_standings(f"recorded-{feed}", payload)


@pytest.fixture
def indexes() -> dict[str, AssistIndex]:
    return {feed: _index(feed) for feed in ("league", "flex", "academy")}


class TestBuildTargets:
    def test_every_bracket_the_feed_lists_becomes_a_target(self, indexes):
        targets = build_targets(indexes)

        league = indexes["league"].brackets
        flex = indexes["flex"].brackets
        planned = {k: v for k, v in targets.items() if not k.endswith("-ifa")}
        assert len(planned) == len(league) + len(flex)

    def test_a_bracket_the_feed_does_not_list_is_not_a_target(self, indexes):
        """There is no Pathway bracket at U13 — targeting one is a standing
        empty scrape, and the hand-written list had no way to know."""
        targets = build_targets(indexes)

        assert "u16-ppp-central" in targets
        assert "u13-ppp-central" not in targets
        assert "u15-ppp-central" not in targets

    def test_a_conference_missing_one_age_group_keeps_the_others(self, indexes):
        """Florida is recorded at U15 only; the rule is per bracket, not per
        conference."""
        targets = build_targets(indexes)

        assert targets["u15-hg-florida"]["division"] == "Florida"
        assert "u13-hg-florida" not in targets

    def test_academy_is_opt_in(self, indexes):
        without = build_targets(indexes)
        with_academy = build_targets(indexes, leagues=("Homegrown", "Flex", "Academy"))

        assert not [k for k in without if "academy" in k and not k.endswith("-ifa")]
        assert with_academy["u14-academy"] == {
            "age_group": "U14",
            "league": "Academy",
            "conference": "New England",
        }

    def test_a_feed_that_did_not_load_costs_only_its_own_league(self, indexes):
        targets = build_targets(
            {"league": indexes["league"]}, leagues=("Homegrown", "Flex")
        )

        assert any(k.endswith("-hg") or "-hg-" in k for k in targets)
        assert not [k for k in targets if "-flex-" in k]


class TestTargetKeys:
    def test_the_default_conference_keeps_its_bare_key(self):
        """u14-hg and u14-academy are in the journal and in muscle memory."""
        assert target_key("Homegrown", "Northeast", "U14") == "u14-hg"
        assert target_key("Academy", "New England", "U14") == "u14-academy"

    def test_other_conferences_are_suffixed(self):
        assert target_key("Homegrown", "Mid-Atlantic", "U16") == "u16-hg-mid-atlantic"
        assert target_key("Flex", "Turnpike", "U15") == "u15-flex-turnpike"

    def test_pathway_brackets_keep_their_own_prefix(self):
        assert (
            target_key("Homegrown", "Northeast (Pro Player Pathway)", "U16")
            == "u16-ppp-northeast"
        )

    def test_parentheses_become_readable_keys(self):
        assert slug("Mid-America (East)") == "mid-america-east"
        assert (
            target_key("Flex", "Southwest (North)", "U17") == "u17-flex-southwest-north"
        )

    def test_a_name_shared_across_leagues_gets_distinct_keys(self, indexes):
        """Florida, Frontier, Northwest and Southeast exist in both Homegrown
        and Flex, and Mid-Atlantic in all three."""
        assert target_key("Homegrown", "Mid-Atlantic", "U16") != target_key(
            "Flex", "Mid-Atlantic (North)", "U16"
        )

    def test_every_key_maps_to_one_config(self, indexes):
        targets = build_targets(indexes, leagues=("Homegrown", "Flex", "Academy"))
        seen: dict[tuple[str, str, str], str] = {}
        for key, cfg in targets.items():
            if key.endswith("-ifa"):
                continue
            ident = (
                cfg["age_group"],
                cfg["league"],
                cfg.get("division") or cfg["conference"],
            )
            assert ident not in seen, f"{key} and {seen[ident]} both scrape {ident}"
            seen[ident] = key


class TestScraperConfigShape:
    def test_every_target_names_its_league(self, indexes):
        """missing-table scopes its division lookup by league — Florida in
        Homegrown and Florida in Flex are different divisions (SB-836)."""
        targets = build_targets(indexes, leagues=("Homegrown", "Flex", "Academy"))

        for key, cfg in targets.items():
            assert cfg["league"] in ("Homegrown", "Flex", "Academy"), key

    def test_homegrown_and_flex_file_a_division_academy_a_conference(self, indexes):
        targets = build_targets(indexes, leagues=("Homegrown", "Flex", "Academy"))

        for key, cfg in targets.items():
            if cfg["league"] == "Academy":
                assert "conference" in cfg and "division" not in cfg, key
            else:
                assert "division" in cfg and "conference" not in cfg, key

    def test_pathway_stays_in_the_homegrown_league(self, indexes):
        targets = build_targets(indexes)

        for key, cfg in targets.items():
            if "-ppp-" in key:
                assert cfg["league"] == "Homegrown"
                assert cfg["division"].endswith("(Pro Player Pathway)")

    def test_the_ifa_variants_track_their_bracket(self, indexes):
        targets = build_targets(indexes)

        assert targets["u16-hg-ifa"] == targets["u16-hg"]


class FakeClient:
    """Stands in for AssistClient — index() is all load_targets asks of it."""

    def __init__(self, indexes: dict[str, AssistIndex], fails: set[str] | None = None):
        self._indexes = indexes
        self._fails = fails or set()
        self.asked: list[str] = []

    async def index(self, feed: str) -> AssistIndex:
        self.asked.append(feed)
        if feed in self._fails:
            raise RuntimeError(f"{feed} feed unavailable")
        return self._indexes[feed]


class TestLoadTargets:
    @pytest.mark.asyncio
    async def test_it_reads_one_feed_per_league(self, indexes):
        client = FakeClient(indexes)

        targets = await load_targets(leagues=("Homegrown", "Flex"), client=client)

        assert client.asked == ["league", "flex"]
        assert targets["u16-hg-mid-atlantic"]["division"] == "Mid-Atlantic"

    @pytest.mark.asyncio
    async def test_a_feed_that_will_not_load_does_not_take_the_run_with_it(
        self, indexes
    ):
        """The league feed is the one that matters most; losing Flex should not
        cost the Homegrown scrape its targets."""
        client = FakeClient(indexes, fails={"flex"})

        targets = await load_targets(leagues=("Homegrown", "Flex"), client=client)

        assert any("-hg" in k for k in targets)
        assert not [k for k in targets if "-flex-" in k]

    @pytest.mark.asyncio
    async def test_academy_asks_for_its_own_feed(self, indexes):
        client = FakeClient(indexes)

        targets = await load_targets(
            leagues=("Homegrown", "Flex", "Academy"), client=client
        )

        assert "academy" in client.asked
        assert targets["u19-academy-pioneer"]["conference"] == "Pioneer"
