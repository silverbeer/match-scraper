"""
Tests for the poll-release state file (SB-499).

The state file is what makes an unattended poller alert *once* on release
rather than every run, so its failure modes matter more than its happy path: a
poller that double-alerts is annoying, one that crashes on a bad line stops
alerting entirely.
"""

import json
from datetime import date, datetime, timezone

from src.cli.main import _append_probe_state, _load_live_targets
from src.models.schedule_release import DivisionRelease, ReleaseProbe, ReleaseState


def _probe(results):
    return ReleaseProbe(
        season="2026-2027",
        window_start=date(2026, 8, 1),
        window_end=date(2026, 12, 31),
        checked_at=datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc),
        results=results,
    )


def _live(age="U15", division="Northeast", count=25):
    return DivisionRelease(
        age_group=age, division=division, state=ReleaseState.LIVE, match_count=count
    )


def _empty(age="U15", division="Northeast"):
    return DivisionRelease(age_group=age, division=division, state=ReleaseState.EMPTY)


class TestLoadLiveTargets:
    def test_missing_file_yields_nothing(self, tmp_path):
        assert _load_live_targets(tmp_path / "absent.ndjson") == set()

    def test_none_path_yields_nothing(self):
        assert _load_live_targets(None) == set()

    def test_reads_live_targets_only(self, tmp_path):
        path = tmp_path / "probe.ndjson"
        _append_probe_state(
            path, _probe([_live(), _empty(age="U14")]), newly_live=[_live()]
        )

        assert _load_live_targets(path) == {"U15 Northeast"}

    def test_accumulates_across_runs(self, tmp_path):
        path = tmp_path / "probe.ndjson"
        _append_probe_state(path, _probe([_live()]), newly_live=[_live()])
        _append_probe_state(
            path,
            _probe([_live(), _live(division="Florida")]),
            newly_live=[_live(division="Florida")],
        )

        assert _load_live_targets(path) == {"U15 Northeast", "U15 Florida"}

    def test_malformed_lines_are_skipped_not_fatal(self, tmp_path):
        path = tmp_path / "probe.ndjson"
        _append_probe_state(path, _probe([_live()]), newly_live=[_live()])
        with path.open("a") as f:
            f.write("this is not json\n")
            f.write("\n")

        assert _load_live_targets(path) == {"U15 Northeast"}

    def test_empty_file_yields_nothing(self, tmp_path):
        path = tmp_path / "probe.ndjson"
        path.write_text("")
        assert _load_live_targets(path) == set()


class TestAppendProbeState:
    def test_creates_parent_directories(self, tmp_path):
        path = tmp_path / "nested" / "deeper" / "probe.ndjson"
        _append_probe_state(path, _probe([_empty()]), newly_live=[])

        assert path.exists()

    def test_records_newly_live_labels(self, tmp_path):
        path = tmp_path / "probe.ndjson"
        _append_probe_state(path, _probe([_live()]), newly_live=[_live()])

        record = json.loads(path.read_text().strip())
        assert record["newly_live"] == ["U15 Northeast"]
        assert record["season"] == "2026-2027"

    def test_one_line_per_probe(self, tmp_path):
        path = tmp_path / "probe.ndjson"
        for _ in range(3):
            _append_probe_state(path, _probe([_empty()]), newly_live=[])

        assert len(path.read_text().strip().splitlines()) == 3

    def test_empty_probe_records_no_new_targets(self, tmp_path):
        path = tmp_path / "probe.ndjson"
        _append_probe_state(path, _probe([_empty()]), newly_live=[])

        record = json.loads(path.read_text().strip())
        assert record["newly_live"] == []
        assert _load_live_targets(path) == set()
