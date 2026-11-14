"""Tests for the daily scores digest (SB-1679)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import MagicMock, patch

import typer

from src.orchestrator.cli import digest
from src.orchestrator.digest import DigestSummary, build_digest_report, summarize

# Sat 14 Nov 2026, 11:00 PM EST (UTC-5).
NOW = datetime(2026, 11, 15, 4, 0, tzinfo=UTC)


def _m(
    match_date: str = "2026-11-14",
    status: str = "completed",
    kickoff: str | None = "2026-11-14T17:00:00+00:00",
    source: str = "match-scraper-agent",
    league: str = "Homegrown",
) -> dict:
    return {
        "match_date": match_date,
        "match_status": status,
        "scheduled_kickoff": kickoff,
        "source": source,
        "league_name": league,
    }


class TestSummarize:
    def test_counts_todays_scored_and_unscored(self) -> None:
        s = summarize(
            [
                _m(),
                _m(),
                _m(status="scheduled", league="Flex"),
            ],
            NOW,
        )
        assert s.day == date(2026, 11, 14)
        assert (s.played_today, s.scored_today, s.unscored_today) == (3, 2, 1)
        assert s.unscored_by_league == {"Flex": 1}

    def test_not_yet_past_grace_is_not_missing(self) -> None:
        """Kicked off 2h ago: inside the 3h grace, so not late yet."""
        s = summarize(
            [_m(status="scheduled", kickoff="2026-11-15T02:00:00+00:00")], NOW
        )
        assert s.played_today == 0
        assert s.unscored_total == 0

    def test_no_kickoff_counts_once_the_day_is_over(self) -> None:
        s = summarize(
            [
                _m(status="scheduled", kickoff=None),  # today, no time
                _m(match_date="2026-11-08", status="tbd", kickoff=None),
            ],
            NOW,
        )
        assert s.unscored_today == 0
        assert s.unscored_earlier == 1
        assert s.oldest_unscored == date(2026, 11, 8)

    def test_backlog_reports_oldest(self) -> None:
        s = summarize(
            [
                _m(
                    match_date="2026-11-08",
                    status="scheduled",
                    kickoff="2026-11-08T15:00:00+00:00",
                ),
                _m(
                    match_date="2026-11-07",
                    status="scheduled",
                    kickoff="2026-11-07T15:00:00+00:00",
                ),
            ],
            NOW,
        )
        assert s.unscored_earlier == 2
        assert s.oldest_unscored == date(2026, 11, 7)

    def test_ignores_manual_postponed_old_and_earlier_scored(self) -> None:
        s = summarize(
            [
                _m(status="scheduled", source="manual"),
                _m(status="postponed"),
                _m(status="cancelled"),
                _m(match_date="2026-10-01", status="scheduled"),
                _m(match_date="2026-11-08"),  # scored earlier: not "today"
            ],
            NOW,
        )
        assert s == DigestSummary(day=date(2026, 11, 14))


class TestBuildDigestReport:
    def test_scored_and_waiting(self) -> None:
        msg = build_digest_report(
            DigestSummary(
                day=date(2026, 11, 14),
                played_today=10,
                scored_today=8,
                unscored_today=2,
                unscored_earlier=3,
                oldest_unscored=date(2026, 11, 7),
                unscored_by_league={"Flex": 4, "Homegrown": 1},
            )
        )
        assert "Scored today: 8 of 10" in msg
        assert "still need a score: 5" in msg
        assert "today: 2" in msg
        assert "earlier this week: 3 \\(oldest Sat 7 Nov\\)" in msg
        assert "Flex 4 · Homegrown 1" in msg

    def test_quiet_day(self) -> None:
        msg = build_digest_report(DigestSummary(day=date(2026, 11, 11)))
        assert "No matches played today" in msg
        assert "Every played match has a score" in msg


class TestDigestCommand:
    def _run(self, matches=None, error: Exception | None = None):
        sent: list[str] = []
        fetch = MagicMock(return_value=matches or [], side_effect=error)
        with (
            patch("src.orchestrator.digest.fetch_recent_matches", fetch),
            patch(
                "src.orchestrator.cli._send_telegram_message",
                side_effect=lambda _s, msg, **_k: sent.append(msg),
            ),
            patch("src.orchestrator.settings.AgentSettings", MagicMock()),
        ):
            try:
                digest(env="local")
            except typer.Exit as exc:
                return exc.exit_code, sent
            return 0, sent

    def test_sends_one_digest(self) -> None:
        code, sent = self._run([_m(match_date="2026-01-01")])
        assert code == 0
        assert len(sent) == 1
        assert "Scores digest" in sent[0]

    def test_fetch_failure_alerts_and_exits_nonzero(self) -> None:
        """A digest that silently said zero would read as "all scores in"."""
        code, sent = self._run(error=RuntimeError("503"))
        assert code == 1
        assert len(sent) == 1
        assert "digest failed" in sent[0]
