"""Once-a-day suppression for repeated run alerts (SB-1679).

An unresolved team name is rejected by missing-table on every run until
someone adds an alias. Reporting it every run turns one fix into a stream of
identical messages, so each name is alerted at most once per day.

The state is one small JSON file on the agent-state PVC:

    {"day": "2026-11-14", "sent": ["team:Some FC", ...]}

Any failure to read or write it falls back to alerting. A duplicate message is
an annoyance; a swallowed one is a fix nobody makes.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()


def _key(failure: dict[str, Any]) -> str:
    return f"{failure.get('kind', 'name')}:{failure.get('raw_name', '')}"


def _read_sent(path: Path, today: date) -> set[str]:
    try:
        state = json.loads(path.read_text())
    except FileNotFoundError:
        return set()
    except (OSError, ValueError) as exc:
        logger.warning("alert_state.read_failed", path=str(path), error=str(exc))
        return set()
    if state.get("day") != today.isoformat():
        return set()
    return set(state.get("sent", []))


def unalerted(
    failures: list[dict[str, Any]], path: str, today: date
) -> list[dict[str, Any]]:
    """The failures not yet alerted today."""
    sent = _read_sent(Path(path), today)
    return [f for f in failures if _key(f) not in sent]


def mark_alerted(failures: list[dict[str, Any]], path: str, today: date) -> None:
    """Record these failures as alerted today."""
    if not failures:
        return
    target = Path(path)
    sent = _read_sent(target, today) | {_key(f) for f in failures}
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps({"day": today.isoformat(), "sent": sorted(sent)}, indent=2)
        )
    except OSError as exc:
        logger.warning("alert_state.write_failed", path=str(target), error=str(exc))
