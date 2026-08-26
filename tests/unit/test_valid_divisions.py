"""Division names are the feed's to decide, not this repo's (SB-827).

LEGACY_DIVISIONS went stale in both directions and nothing said so. For
2026-2027 it still offered Great Lakes, Texas and California — removed by MLS
Next — while omitting Frontier, Mid-America and the four Pro Player Pathway
brackets. Six of the twelve Homegrown brackets could not be scraped, and asking
for a Pathway bracket failed with "Invalid division" before any fetch happened.

So the CLI no longer pre-rejects a division for the assist source. The scrape
checks the name against the feed it has already loaded and, on a miss, raises
with the published brackets listed.
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.cli.main import LEGACY_DIVISIONS, valid_divisions
from src.scraper.config import ScrapingConfig
from src.scraper.mls_scraper import MLSScraper, MLSScraperError

FEED_BRACKETS = [
    "Florida",
    "Frontier",
    "Mid-America",
    "Mid-Atlantic",
    "Northeast",
    "Northeast (Pro Player Pathway)",
]


class TestValidDivisions:
    def test_the_assist_source_has_no_fixed_list(self, monkeypatch):
        monkeypatch.setenv("MATCH_SOURCE", "assist")
        assert valid_divisions("Homegrown") is None

    def test_the_source_defaults_to_assist(self, monkeypatch):
        monkeypatch.delenv("MATCH_SOURCE", raising=False)
        assert valid_divisions("Homegrown") is None

    def test_the_playwright_source_keeps_the_legacy_list(self, monkeypatch):
        # 2025-2026 backfill runs against modular11, where those names are the
        # correct ones and the assist feed has no data for that season at all.
        monkeypatch.setenv("MATCH_SOURCE", "playwright")
        assert valid_divisions("Homegrown") == LEGACY_DIVISIONS

    def test_validation_does_no_network_io(self, monkeypatch):
        # Reading the feed here would put a network call in argument parsing,
        # and it would run before — and separately from — the scrape's own
        # feed read. It also silently consumed a patched asyncio.run in the
        # agent tests, which is how this was caught.
        monkeypatch.delenv("MATCH_SOURCE", raising=False)
        with patch("src.scraper.assist_client.AssistClient") as client:
            valid_divisions("Homegrown")
        client.assert_not_called()


def _config(**kw):
    base = {
        "age_group": "U16",
        "division": "Northeast",
        "league": "Homegrown",
        "club": "",
        "competition": "",
        "look_back_days": 1,
        "start_date": date(2026, 9, 5),
        "end_date": date(2026, 9, 30),
        "missing_table_api_url": "https://api.test.com",
        "missing_table_api_key": "test-key",
        "log_level": "INFO",
    }
    base.update(kw)
    return ScrapingConfig(**base)


@pytest.mark.asyncio
class TestUnknownBracketIsLoud:
    async def test_an_unknown_bracket_raises_and_lists_the_real_ones(self):
        # Before this, a wrong bracket name returned zero matches and a log
        # line — a successful scrape of nothing, which is exactly how the
        # Pathway brackets stayed missing.
        client = AsyncMock()
        client.get_matches.return_value = []
        client.divisions.return_value = FEED_BRACKETS
        client.__aenter__.return_value = client

        with (
            patch("src.scraper.mls_scraper.AssistClient", return_value=client),
            pytest.raises(MLSScraperError) as exc,
        ):
            await MLSScraper(_config(division="Northeast (PPP)")).scrape_matches()

        assert "Northeast (PPP)" in str(exc.value)
        assert "Northeast (Pro Player Pathway)" in str(exc.value)

    async def test_a_known_bracket_that_is_simply_empty_does_not_raise(self):
        # A real bracket with no fixtures in the window is a legitimate empty
        # result, not an error. Conflating the two would make every quiet week
        # a failure.
        client = AsyncMock()
        client.get_matches.return_value = []
        client.divisions.return_value = FEED_BRACKETS
        client.__aenter__.return_value = client

        with patch("src.scraper.mls_scraper.AssistClient", return_value=client):
            assert await MLSScraper(_config(division="Frontier")).scrape_matches() == []

    async def test_the_feed_is_not_re_read_when_matches_come_back(self):
        # The check runs on the empty path only.
        client = AsyncMock()
        client.get_matches.return_value = [MagicMock(match_status="scheduled")]
        client.__aenter__.return_value = client

        with patch("src.scraper.mls_scraper.AssistClient", return_value=client):
            await MLSScraper(_config(division="Northeast")).scrape_matches()

        client.divisions.assert_not_awaited()
