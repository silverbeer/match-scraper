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


# --- Completeness gaps (SB-1786) -------------------------------------------
#
# The backfill CronJob records which official results it found missing from
# missing-table, which it sent, and which were still not in MT at the end:
#
#     {"day": "2026-11-26", "found": [...], "submitted": [...],
#      "still_missing": [...]}
#
# The next run reads ``submitted`` to tell a new gap from one its own send did
# not close — the second is the louder alert — and the digest reads
# ``still_missing`` for its "N official results not in MT" line. Same failure
# rule as above: unreadable state means "no previous run", which can only make
# an alert fresher, never swallow one.


def read_gap_state(path: str) -> dict[str, Any]:
    """The last completeness run's record, or {} if there is none."""
    try:
        state = json.loads(Path(path).read_text())
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        logger.warning("alert_state.read_failed", path=path, error=str(exc))
        return {}
    return state if isinstance(state, dict) else {}


def repeat_gaps(found: list[str], path: str) -> list[str]:
    """The game keys in ``found`` the previous run sent, and that are missing
    again. A key it only found — refused, no bracket, send failed — is not a
    repeat: nothing was tried, so nothing failed to land."""
    previous = set(read_gap_state(path).get("submitted") or [])
    return sorted(key for key in found if key in previous)


def write_gap_state(
    path: str,
    today: date,
    found: list[str],
    submitted: list[str],
    still_missing: list[str],
) -> None:
    """Record this run's gaps for the next run and the digest."""
    target = Path(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {
                    "day": today.isoformat(),
                    "found": sorted(found),
                    "submitted": sorted(submitted),
                    "still_missing": sorted(still_missing),
                },
                indent=2,
            )
        )
    except OSError as exc:
        logger.warning("alert_state.write_failed", path=str(target), error=str(exc))
