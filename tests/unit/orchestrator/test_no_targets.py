"""A run whose feeds declare no targets fails loudly (SB-1492)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import typer

from src.orchestrator import cli


def test_zero_targets_alerts_and_exits_without_writing_the_journal():
    with (
        patch("src.orchestrator.settings.AgentSettings", MagicMock()),
        patch("src.celery.queue_client.MatchQueueClient", MagicMock()),
        patch.object(cli, "_target_config", return_value={}),
        patch.object(cli, "_send_telegram_failure") as alert,
        patch("src.orchestrator.planner.fetch_mt_status") as mt,
        patch("src.orchestrator.journal.write_journal") as write,
    ):
        with pytest.raises(typer.Exit) as exc:
            cli.run(env="prod", dry_run=False, json_logs=False, target=None)

    assert exc.value.exit_code == 1
    alert.assert_called_once()
    assert alert.call_args.kwargs["phase"] == "targets"
    mt.assert_not_called()
    write.assert_not_called()
