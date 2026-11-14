"""Tests for once-a-day alert suppression (SB-1679)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from src.orchestrator.alert_state import mark_alerted, unalerted

TODAY = date(2026, 11, 14)
A = {"kind": "team", "raw_name": "Some FC", "match_count": 3}
B = {"kind": "team", "raw_name": "Other SC", "match_count": 1}


def test_first_sighting_alerts(tmp_path: Path) -> None:
    assert unalerted([A], str(tmp_path / "s.json"), TODAY) == [A]


def test_repeat_same_day_is_suppressed(tmp_path: Path) -> None:
    path = str(tmp_path / "s.json")
    mark_alerted([A], path, TODAY)
    assert unalerted([A, B], path, TODAY) == [B]


def test_alerts_again_next_day(tmp_path: Path) -> None:
    path = str(tmp_path / "s.json")
    mark_alerted([A], path, TODAY)
    assert unalerted([A], path, date(2026, 11, 15)) == [A]


def test_marks_accumulate(tmp_path: Path) -> None:
    path = str(tmp_path / "s.json")
    mark_alerted([A], path, TODAY)
    mark_alerted([B], path, TODAY)
    assert unalerted([A, B], path, TODAY) == []


def test_unreadable_state_falls_back_to_alerting(tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    path.write_text("{not json")
    assert unalerted([A], str(path), TODAY) == [A]


def test_unwritable_state_does_not_raise(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("")
    mark_alerted([A], str(blocker / "s.json"), TODAY)  # parent is a file
