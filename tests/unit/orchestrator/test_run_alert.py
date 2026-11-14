"""The run report reaches Telegram only when it needs a person (SB-1679)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.orchestrator.cli import _send_telegram_report

FAILURE = {"kind": "team", "raw_name": "Some FC", "match_count": 2}


def _ctx(**overrides):
    ctx = SimpleNamespace(
        missing_table_api_url="http://mt",
        missing_table_api_key="k",
        _started_at=None,
        _scraped_matches=[],
        _submission_errors=[],
        _protected_matches=[],
        _mt_status="ok",
        _scrape_plan=None,
        dry_run=False,
    )
    for k, v in overrides.items():
        setattr(ctx, k, v)
    return ctx


def _send(tmp_path, ctx, failures):
    settings = SimpleNamespace(
        telegram_bot_token="t",
        telegram_chat_id="c",
        alert_state_path=str(tmp_path / "alerts.json"),
    )
    result = SimpleNamespace(
        summary="", actions=[], matches_found=0, matches_submitted=0
    )
    client = MagicMock()
    with (
        patch(
            "src.orchestrator.ingest_failures.fetch_ingest_failures",
            return_value=failures,
        ),
        patch("telegram_notify.TelegramClient", return_value=client),
    ):
        _send_telegram_report(
            settings=settings, result=result, ctx=ctx, env="prod", target=None
        )
    return client.send.call_count


def test_quiet_run_sends_nothing(tmp_path):
    assert _send(tmp_path, _ctx(), []) == 0


def test_mt_failure_sends(tmp_path):
    assert _send(tmp_path, _ctx(_mt_status="failed: 504"), []) == 1


def test_rejected_name_alerts_once_a_day(tmp_path):
    assert _send(tmp_path, _ctx(), [FAILURE]) == 1
    assert _send(tmp_path, _ctx(), [FAILURE]) == 0
