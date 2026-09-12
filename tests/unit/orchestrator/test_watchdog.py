"""Tests for the run watchdog and the failure notifier (SB-1062).

Between them these cover the two halves of "a failed run notifies nobody":
the agent reporting its own failures, and an outside observer noticing when the
agent never ran at all.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
import typer

from src.orchestrator.cli import _send_telegram_failure, watchdog
from src.orchestrator.journal import RunJournal


def _journal(age_hours: float) -> RunJournal:
    stamp = datetime.now(tz=UTC) - timedelta(hours=age_hours)
    return RunJournal(timestamp=stamp.isoformat(), run_id="abc123def456")


class TestWatchdog:
    """Exit codes are outcomes: 0 healthy, 10 stale. A non-zero exit Kubernetes
    read as a failed Job would retry it and bury the signal."""

    def _run(self, journal, **kwargs):
        sent = []
        with (
            patch("src.orchestrator.journal.read_journal", return_value=journal),
            patch(
                "src.orchestrator.cli._send_telegram_message",
                side_effect=lambda _s, msg, **_k: sent.append(msg),
            ),
            patch("src.orchestrator.settings.AgentSettings", MagicMock()),
        ):
            try:
                watchdog(env="local", **kwargs)
            except typer.Exit as exc:
                return exc.exit_code, sent
            return 0, sent

    def test_a_recent_run_is_healthy_and_silent(self):
        code, sent = self._run(_journal(age_hours=2), max_age_hours=8.0)
        assert code == 0
        assert sent == []

    def test_a_stale_run_alerts_and_exits_ten(self):
        code, sent = self._run(_journal(age_hours=20), max_age_hours=8.0)
        assert code == 10
        assert len(sent) == 1
        assert "No successful run in too long" in sent[0]

    def test_a_missing_journal_alerts(self):
        """No journal at all is the shape of a pod that never started."""
        code, sent = self._run(None, max_age_hours=8.0)
        assert code == 10
        assert "No run journal found at all" in sent[0]

    def test_the_boundary_is_not_an_alert(self):
        code, sent = self._run(_journal(age_hours=7.9), max_age_hours=8.0)
        assert code == 0
        assert sent == []

    def test_an_unreadable_timestamp_alerts_rather_than_crashing(self):
        """A corrupt journal must not look healthy, and must not raise either."""
        code, sent = self._run(
            RunJournal(timestamp="not a timestamp", run_id="abc123def456"),
            max_age_hours=8.0,
        )
        assert code == 10
        assert len(sent) == 1

    def test_dry_run_reports_the_finding_without_sending(self):
        code, sent = self._run(_journal(age_hours=20), max_age_hours=8.0, dry_run=True)
        assert code == 10
        assert sent == []


class TestSendTelegramFailure:
    def test_sends_a_failure_report(self):
        settings = MagicMock()
        with patch("src.orchestrator.cli._send_telegram_message") as send:
            _send_telegram_failure(
                settings,
                env="prod",
                run_id="03833fd59feb",
                reason="missing-table did not answer",
                detail="500 Internal Server Error",
                phase="planning",
            )
        assert send.call_count == 1
        message = send.call_args[0][1]
        assert "Run failed" in message
        assert "No matches were scraped" in message
        assert "planning" in message

    def test_never_raises(self):
        """A failure inside the failure notifier must not replace the exit code
        the caller is on its way to returning."""
        settings = MagicMock()
        with patch(
            "src.orchestrator.cli._send_telegram_message",
            side_effect=RuntimeError("telegram is down"),
        ):
            _send_telegram_failure(
                settings, env="prod", run_id="abc123", reason="whatever"
            )


class TestRunReportsItsFailures:
    """The regression that started it: an MT 500 halted the run and sent
    nothing, four times in a row across a match weekend."""

    def test_the_failure_branch_calls_the_notifier(self):
        """Read the source of `run` and assert the notifier is on the MT branch.

        Cheaper and far more stable than standing up Celery, Playwright and a
        settings file to reach one `if`, and it fails loudly if someone moves
        the notify call back out of the halt path.
        """
        import inspect

        from src.orchestrator import cli

        source = inspect.getsource(cli.run)
        mt_branch = source.split('if mt_status_str.startswith("failed:"):')[1]
        halt = mt_branch.split("raise typer.Exit")[0]
        assert "_send_telegram_failure" in halt

    def test_the_catch_all_branch_calls_the_notifier(self):
        import inspect

        from src.orchestrator import cli

        source = inspect.getsource(cli.run)
        handler = source.split("except Exception as exc:")[1]
        assert "_send_telegram_failure" in handler.split("raise typer.Exit")[0]


@pytest.mark.parametrize("command", ["watchdog", "notify"])
def test_commands_are_registered(command):
    """The manifests invoke these by name; a rename must fail here, not at
    02:00 in a CronJob."""
    from src.orchestrator.cli import app

    names = {c.name or c.callback.__name__ for c in app.registered_commands}
    assert command in names
