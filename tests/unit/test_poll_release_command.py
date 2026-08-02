"""
Unit tests for the `poll-release` CLI command and the async probe path.

The exit codes are a contract with an unattended CronJob wrapper, so they are
tested as behaviour rather than as an implementation detail: 10 means "wake
someone", 20 means "the site may be down", 0 means "go back to sleep".
"""

import json
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from typer.testing import CliRunner

from src.cli.main import app
from src.models.schedule_release import DivisionRelease, ReleaseProbe, ReleaseState
from src.scraper.release_detector import ReleaseDetectorError, ScheduleReleaseDetector

runner = CliRunner()

EMPTY_BODY = '<div class="text-center"><p>No data available.</p></div>'
MATCH_BODY = (
    '<div class="row table-content-row" js-match-game="1">A vs B</div>'
    '<div class="row table-content-row" js-match-game="1">C vs D</div>'
)


def _probe(results, season="2026-2027"):
    return ReleaseProbe(
        season=season,
        window_start=date(2026, 8, 1),
        window_end=date(2026, 12, 31),
        checked_at=datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc),
        results=results,
    )


def _result(
    age="U15", division="Northeast", state=ReleaseState.EMPTY, count=0, error=None
):
    return DivisionRelease(
        age_group=age,
        division=division,
        state=state,
        match_count=count,
        error=error,
    )


# ---------------------------------------------------------------------------
# Async probe path, with the network mocked at the transport layer
# ---------------------------------------------------------------------------


# Captured before any patching: `release_detector` does `import httpx`, so
# patching `release_detector.httpx.AsyncClient` rebinds the attribute on the
# shared httpx module. Without this the factory below would call itself.
_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _mock_transport(handler):
    """Patch the detector's client so its requests are served by ``handler``."""

    def factory(**kwargs):
        return _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler), **kwargs)

    return patch("src.scraper.release_detector.httpx.AsyncClient", factory)


def _serving(body, status=200):
    """Patch the detector's client to answer every request identically."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text=body)

    return _mock_transport(handler)


class TestProbeAgainstMockedEndpoint:
    @pytest.mark.asyncio
    async def test_empty_response_yields_empty_state(self):
        detector = ScheduleReleaseDetector(age_groups=["U15"], divisions=["Northeast"])

        with _serving(EMPTY_BODY):
            probe = await detector.probe()

        assert not probe.is_released
        assert probe.results[0].state is ReleaseState.EMPTY
        assert probe.results[0].match_count == 0

    @pytest.mark.asyncio
    async def test_fixture_rows_yield_live_state(self):
        detector = ScheduleReleaseDetector(age_groups=["U15"], divisions=["Northeast"])

        with _serving(MATCH_BODY):
            probe = await detector.probe()

        assert probe.is_released
        assert probe.results[0].match_count == 2
        assert probe.total_matches == 2

    @pytest.mark.asyncio
    async def test_http_error_becomes_an_error_result_not_an_exception(self):
        """One dead target must not sink the whole probe."""
        detector = ScheduleReleaseDetector(age_groups=["U15"], divisions=["Northeast"])
        detector.RETRY_DELAY_BASE = 0  # no need to actually back off in a test

        with _serving("boom", status=503):
            probe = await detector.probe()

        assert probe.all_failed
        assert probe.results[0].state is ReleaseState.ERROR
        assert probe.results[0].error

    @pytest.mark.asyncio
    async def test_probes_every_age_group_division_pair(self):
        detector = ScheduleReleaseDetector(
            age_groups=["U15", "U14"], divisions=["Northeast", "Florida"]
        )

        with _serving(EMPTY_BODY):
            probe = await detector.probe()

        assert len(probe.results) == 4
        assert {r.label for r in probe.results} == {
            "U15 Northeast",
            "U14 Northeast",
            "U15 Florida",
            "U14 Florida",
        }

    @pytest.mark.asyncio
    async def test_request_carries_the_configured_window_and_ids(self):
        """The season window and IDs must reach the wire, not just the object."""
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, text=EMPTY_BODY)

        detector = ScheduleReleaseDetector(
            age_groups=["U15"], divisions=["Mid-Atlantic"], season_year=2026
        )

        with _mock_transport(handler):
            await detector.probe()

        url = str(captured[0].url)
        assert "age%5B%5D=33" in url  # U15
        assert "groups%5B%5D=68" in url  # Mid-Atlantic
        assert "2026-08-01" in url
        assert "2026-12-31" in url
        assert "status=all" in url


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------


def _patch_probe(probe):
    return patch(
        "src.scraper.release_detector.ScheduleReleaseDetector.probe",
        new=AsyncMock(return_value=probe),
    )


class TestPollReleaseExitCodes:
    def test_no_fixtures_exits_zero(self):
        with _patch_probe(_probe([_result()])):
            result = runner.invoke(
                app, ["poll-release", "-a", "U15", "-d", "Northeast"]
            )

        assert result.exit_code == 0
        assert "No fixtures published yet" in result.stdout

    def test_newly_live_exits_ten(self):
        with _patch_probe(_probe([_result(state=ReleaseState.LIVE, count=25)])):
            result = runner.invoke(
                app, ["poll-release", "-a", "U15", "-d", "Northeast"]
            )

        assert result.exit_code == 10
        assert "Schedule published" in result.stdout

    def test_all_targets_failing_exits_twenty(self):
        with _patch_probe(_probe([_result(state=ReleaseState.ERROR, error="boom")])):
            result = runner.invoke(
                app, ["poll-release", "-a", "U15", "-d", "Northeast"]
            )

        assert result.exit_code == 20
        assert "All targets failed" in result.stdout

    def test_error_outranks_new_release_when_everything_failed(self):
        """A total outage must not be reported as a release."""
        with _patch_probe(
            _probe(
                [
                    _result(state=ReleaseState.ERROR, error="boom"),
                    _result(age="U14", state=ReleaseState.ERROR, error="boom"),
                ]
            )
        ):
            result = runner.invoke(app, ["poll-release"])

        assert result.exit_code == 20

    def test_unknown_division_exits_one(self):
        result = runner.invoke(app, ["poll-release", "-d", "Atlantis"])

        assert result.exit_code == 1
        assert "Unknown divisions" in result.stdout

    def test_unknown_age_group_exits_one(self):
        result = runner.invoke(app, ["poll-release", "-a", "U12"])

        assert result.exit_code == 1
        assert "Unknown age groups" in result.stdout


class TestPollReleaseStateFileIntegration:
    def test_second_run_does_not_re_alert(self, tmp_path):
        """The whole point of --state-file: alert once, not every run."""
        state = tmp_path / "probe.ndjson"
        probe = _probe([_result(state=ReleaseState.LIVE, count=25)])

        with _patch_probe(probe):
            first = runner.invoke(
                app,
                [
                    "poll-release",
                    "-a",
                    "U15",
                    "-d",
                    "Northeast",
                    "--state-file",
                    str(state),
                ],
            )
        with _patch_probe(probe):
            second = runner.invoke(
                app,
                [
                    "poll-release",
                    "-a",
                    "U15",
                    "-d",
                    "Northeast",
                    "--state-file",
                    str(state),
                ],
            )

        assert first.exit_code == 10
        assert second.exit_code == 0
        assert "already known" in second.stdout

    def test_new_division_after_a_known_one_re_alerts(self, tmp_path):
        state = tmp_path / "probe.ndjson"

        with _patch_probe(_probe([_result(state=ReleaseState.LIVE, count=25)])):
            runner.invoke(app, ["poll-release", "--state-file", str(state)])

        with _patch_probe(
            _probe(
                [
                    _result(state=ReleaseState.LIVE, count=25),
                    _result(division="Florida", state=ReleaseState.LIVE, count=12),
                ]
            )
        ):
            second = runner.invoke(app, ["poll-release", "--state-file", str(state)])

        assert second.exit_code == 10
        assert "U15 Florida" in second.stdout

    def test_state_file_records_every_run(self, tmp_path):
        state = tmp_path / "nested" / "probe.ndjson"

        for _ in range(2):
            with _patch_probe(_probe([_result()])):
                runner.invoke(app, ["poll-release", "--state-file", str(state)])

        assert len(state.read_text().strip().splitlines()) == 2


class TestPollReleaseJsonOutput:
    def test_json_output_is_parseable(self):
        with _patch_probe(_probe([_result(state=ReleaseState.LIVE, count=25)])):
            result = runner.invoke(
                app, ["poll-release", "-a", "U15", "-d", "Northeast", "--json"]
            )

        payload = json.loads(result.stdout)
        assert payload["season"] == "2026-2027"
        assert payload["newly_live"] == ["U15 Northeast"]
        assert payload["results"][0]["state"] == "live"

    def test_json_output_marks_nothing_new_when_empty(self):
        with _patch_probe(_probe([_result()])):
            result = runner.invoke(app, ["poll-release", "--json"])

        payload = json.loads(result.stdout)
        assert payload["newly_live"] == []


class TestPollReleaseDisplay:
    def test_error_rows_are_surfaced_with_detail(self):
        with _patch_probe(
            _probe(
                [
                    _result(),
                    _result(
                        age="U14", state=ReleaseState.ERROR, error="TimeoutError: x"
                    ),
                ]
            )
        ):
            result = runner.invoke(app, ["poll-release"])

        assert "TimeoutError" in result.stdout
        assert result.exit_code == 0, "a partial failure is not an outage"

    def test_full_season_flag_widens_the_window(self):
        captured = {}

        original_init = ScheduleReleaseDetector.__init__

        def spy(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            captured["fall_only"] = self.fall_only

        with (
            patch.object(ScheduleReleaseDetector, "__init__", spy),
            _patch_probe(_probe([_result()])),
        ):
            runner.invoke(app, ["poll-release", "--full-season"])

        assert captured["fall_only"] is False

    def test_detector_error_is_reported_cleanly(self):
        with patch(
            "src.scraper.release_detector.ScheduleReleaseDetector.probe",
            new=AsyncMock(side_effect=ReleaseDetectorError("endpoint gone")),
        ):
            result = runner.invoke(app, ["poll-release"])

        assert result.exit_code == 1
        assert "endpoint gone" in result.stdout
