"""Unit tests for the score canary.

The canary exists because a scrape that returns every fixture and no result is
indistinguishable from a quiet week. These tests pin that distinction: fixtures
that have kicked off are the denominator, scores are the numerator, and an
empty numerator over a non-empty denominator is the alarm.
"""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from src.cli.main import app
from src.scraper.assist_client import (
    AssistEvent,
    AssistSchedule,
    AssistSeasonNotPublished,
)
from src.scraper.score_canary import ScoreCheck, check_feed

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


def _event(
    game_key="g1",
    day=(2026, 9, 5),
    hour=17,
    home_score=None,
    away_score=None,
    completed=False,
):
    return AssistEvent(
        id=abs(hash(game_key)) % 100000,
        game_key=game_key,
        start_time=datetime(*day, hour, 0, tzinfo=timezone.utc),
        local_timezone="America/New_York",
        completed=completed,
        home_score=home_score,
        away_score=away_score,
    )


def _client(events=None, raises=None):
    client = AsyncMock()
    if raises is not None:
        client.schedule = AsyncMock(side_effect=raises)
    else:
        client.schedule = AsyncMock(
            return_value=AssistSchedule(events=events or [], synced_at=NOW)
        )
    return client


async def _check(events=None, raises=None, **kwargs):
    return await check_feed(
        "league",
        window_start=kwargs.pop("window_start", date(2026, 9, 5)),
        window_end=kwargs.pop("window_end", date(2026, 9, 6)),
        season_year=2026,
        now=kwargs.pop("now", NOW),
        client=_client(events, raises),
        **kwargs,
    )


class TestCheckFeed:
    @pytest.mark.asyncio
    async def test_scored_fixtures_are_counted(self):
        check = await _check(
            [
                _event("a", home_score=2, away_score=1, completed=True),
                _event("b", home_score=0, away_score=0, completed=True),
                _event("c"),
            ]
        )

        assert check.kicked_off == 3
        assert check.scored == 2
        assert check.has_scores
        assert "2/3" in check.verdict

    @pytest.mark.asyncio
    async def test_a_nil_nil_is_a_score_not_a_blank(self):
        """0-0 is a result. Only null means no result."""
        check = await _check([_event("a", home_score=0, away_score=0, completed=True)])

        assert check.scored == 1

    @pytest.mark.asyncio
    async def test_played_fixtures_with_no_scores_is_the_alarm(self):
        check = await _check([_event("a"), _event("b")])

        assert check.kicked_off == 2
        assert check.scored == 0
        assert not check.has_scores
        assert not check.nothing_to_judge
        assert check.verdict.startswith("BROKEN")

    @pytest.mark.asyncio
    async def test_fixtures_that_have_not_kicked_off_are_not_judged(self):
        """Before kick-off, a null score is correct — silence proves nothing."""
        check = await _check(
            [_event("a", day=(2026, 9, 6), hour=23)],
            now=datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc),
        )

        assert check.kicked_off == 0
        assert check.nothing_to_judge
        assert check.verdict == "no fixtures played in window"

    @pytest.mark.asyncio
    async def test_fixtures_outside_the_window_are_ignored(self):
        check = await _check(
            [
                _event("in", day=(2026, 9, 5), home_score=1, away_score=0),
                _event("out", day=(2026, 9, 12), home_score=3, away_score=3),
            ],
            now=datetime(2026, 9, 30, tzinfo=timezone.utc),
        )

        assert check.kicked_off == 1
        assert check.scored == 1

    @pytest.mark.asyncio
    async def test_unpublished_season_is_reported_not_raised(self):
        check = await _check(raises=AssistSeasonNotPublished("no feed"))

        assert not check.published
        assert check.verdict == "season not published"
        assert check.kicked_off == 0

    @pytest.mark.asyncio
    async def test_completed_without_scores_is_surfaced(self):
        """Flagged played but carrying no score — a half-populated result."""
        check = await _check(
            [
                _event("a", completed=True),
                _event("b", completed=True, home_score=1, away_score=1),
            ]
        )

        assert check.completed == 2
        assert check.scored == 1
        assert check.completed_without_scores == 1


class TestVerifyScoresCommand:
    """Exit codes are the contract with an unattended caller."""

    runner = CliRunner()

    @staticmethod
    def _returning(check):
        return patch(
            "src.scraper.score_canary.check_feed", AsyncMock(return_value=check)
        )

    @staticmethod
    def _check(**kwargs):
        base = {
            "feed": "league",
            "season": "2026-2027",
            "window_start": date(2026, 9, 5),
            "window_end": date(2026, 9, 6),
        }
        return ScoreCheck(**{**base, **kwargs})

    def test_scores_arriving_exits_zero(self):
        with self._returning(self._check(kicked_off=40, completed=40, scored=40)):
            result = self.runner.invoke(app, ["verify-scores", "--json"])

        assert result.exit_code == 0

    def test_played_but_unscored_exits_ten(self):
        with self._returning(self._check(kicked_off=40)):
            result = self.runner.invoke(app, ["verify-scores", "--json"])

        assert result.exit_code == 10

    def test_nothing_played_yet_exits_zero(self):
        """A pre-season run must stay quiet rather than page every night."""
        with self._returning(self._check()):
            result = self.runner.invoke(app, ["verify-scores", "--json"])

        assert result.exit_code == 0

    def test_unpublished_season_exits_twenty(self):
        with self._returning(self._check(published=False)):
            result = self.runner.invoke(app, ["verify-scores", "--json"])

        assert result.exit_code == 20

    def test_every_named_feed_is_probed(self):
        """The k3s canary probes league, flex and academy (SB-1016)."""
        probe = AsyncMock(
            side_effect=[
                self._check(feed="league", kicked_off=40, completed=40, scored=40),
                self._check(feed="flex", kicked_off=20, completed=20, scored=20),
                self._check(feed="academy", kicked_off=10, completed=10, scored=10),
            ]
        )
        with patch("src.scraper.score_canary.check_feed", probe):
            result = self.runner.invoke(
                app,
                [
                    "verify-scores",
                    "--json",
                    "-f",
                    "league",
                    "-f",
                    "flex",
                    "-f",
                    "academy",
                ],
            )

        assert result.exit_code == 0
        assert [call.args[0] for call in probe.await_args_list] == [
            "league",
            "flex",
            "academy",
        ]

    def test_one_silent_feed_among_several_still_exits_ten(self):
        """A healthy league feed must not mask a Flex feed delivering nothing."""
        with patch(
            "src.scraper.score_canary.check_feed",
            AsyncMock(
                side_effect=[
                    self._check(feed="league", kicked_off=40, completed=40, scored=40),
                    self._check(feed="flex", kicked_off=20),
                ]
            ),
        ):
            result = self.runner.invoke(
                app, ["verify-scores", "--json", "-f", "league", "-f", "flex"]
            )

        assert result.exit_code == 10

    def test_bad_date_is_rejected(self):
        result = self.runner.invoke(app, ["verify-scores", "--from", "5th September"])

        assert result.exit_code == 1
        assert "Invalid --from" in result.output
