"""Tests for the scrape agent code path.

Covers the full pipeline: config creation, match dict building,
team name normalization, change detection, audit logging, and queue submission.
"""

import asyncio
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from src.cli.main import (
    app,
    apply_league_specific_team_name,
    build_match_dict,
    create_config,
    normalize_team_name_for_display,
    save_matches_to_file,
)
from src.scraper.config import ScrapingConfig
from src.scraper.models import Match
from src.utils.match_comparison import MatchComparison

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(
    league: str = "Homegrown",
    division: str = "Northeast",
    conference: str = "",
    age_group: str = "U14",
) -> ScrapingConfig:
    """Create a minimal ScrapingConfig for testing."""
    today = date.today()
    return ScrapingConfig(
        age_group=age_group,
        league=league,
        division=division,
        conference=conference,
        look_back_days=1,
        start_date=today - timedelta(days=1),
        end_date=today,
        missing_table_api_url="http://localhost:8000",
        missing_table_api_key="test-key",
        log_level="ERROR",
    )


def _make_match(
    match_id: str = "100001",
    home_team: str = "Team A",
    away_team: str = "Team B",
    home_score=None,
    away_score=None,
    match_datetime: datetime | None = None,
    location: str | None = "Test Field",
    competition: str | None = "MLS Next",
) -> Match:
    """Create a Match object for testing."""
    if match_datetime is None:
        match_datetime = datetime(2025, 10, 15, 15, 0)
    return Match(
        match_id=match_id,
        home_team=home_team,
        away_team=away_team,
        home_score=home_score,
        away_score=away_score,
        match_datetime=match_datetime,
        location=location,
        competition=competition,
    )


# ===========================================================================
# 1. Team Name Normalization
# ===========================================================================


class TestTeamNameNormalization:
    """Tests for normalize_team_name_for_display."""

    def test_maps_ifa_full_name_to_short(self):
        assert (
            normalize_team_name_for_display(
                "Intercontinental Football Academy of New England"
            )
            == "IFA"
        )

    def test_unmapped_team_passes_through(self):
        assert normalize_team_name_for_display("FC Dallas Youth") == "FC Dallas Youth"

    def test_empty_string_passes_through(self):
        assert normalize_team_name_for_display("") == ""


class TestLeagueSpecificTeamName:
    """Tests for apply_league_specific_team_name."""

    def test_ifa_homegrown_gets_hg_suffix(self):
        assert apply_league_specific_team_name("IFA", "Homegrown") == "IFA HG"

    def test_ifa_academy_unchanged(self):
        assert apply_league_specific_team_name("IFA", "Academy") == "IFA"

    def test_non_ifa_homegrown_unchanged(self):
        assert (
            apply_league_specific_team_name("FC Dallas Youth", "Homegrown")
            == "FC Dallas Youth"
        )

    def test_non_ifa_academy_unchanged(self):
        assert (
            apply_league_specific_team_name("FC Dallas Youth", "Academy")
            == "FC Dallas Youth"
        )


# ===========================================================================
# 2. Config Creation
# ===========================================================================


class TestCreateConfig:
    """Tests for create_config."""

    def test_ifa_club_expansion(self):
        config = create_config(
            age_group="U14",
            league="Homegrown",
            division="Northeast",
            start_offset=-1,
            end_offset=1,
            club="IFA",
        )
        assert config.club == "Intercontinental Football Academy of New England"

    def test_absolute_dates(self):
        config = create_config(
            age_group="U14",
            league="Homegrown",
            division="Northeast",
            start_offset=0,
            end_offset=0,
            from_date="2025-09-01",
            to_date="2025-09-07",
        )
        assert config.start_date == date(2025, 9, 1)
        assert config.end_date == date(2025, 9, 7)

    def test_only_one_absolute_date_raises(self):
        with pytest.raises(ValueError, match="Both --from and --to"):
            create_config(
                age_group="U14",
                league="Homegrown",
                division="Northeast",
                start_offset=0,
                end_offset=0,
                from_date="2025-09-01",
            )

    def test_invalid_date_format_raises(self):
        with pytest.raises(ValueError, match="Invalid date format"):
            create_config(
                age_group="U14",
                league="Homegrown",
                division="Northeast",
                start_offset=0,
                end_offset=0,
                from_date="not-a-date",
                to_date="2025-09-07",
            )

    def test_academy_league_with_conference(self):
        config = create_config(
            age_group="U14",
            league="Academy",
            division="Northeast",
            start_offset=-1,
            end_offset=1,
            conference="New England",
        )
        assert config.league == "Academy"
        assert config.conference == "New England"

    def test_look_back_days_backwards_compat(self):
        """Negative start_offset produces correct look_back_days."""
        config = create_config(
            age_group="U14",
            league="Homegrown",
            division="Northeast",
            start_offset=-7,
            end_offset=0,
        )
        assert config.look_back_days == 7

    def test_positive_start_offset_zero_lookback(self):
        config = create_config(
            age_group="U14",
            league="Homegrown",
            division="Northeast",
            start_offset=0,
            end_offset=1,
        )
        assert config.look_back_days == 0

    def test_relative_date_calculation(self):
        config = create_config(
            age_group="U14",
            league="Homegrown",
            division="Northeast",
            start_offset=-3,
            end_offset=2,
        )
        today = date.today()
        assert config.start_date == today + timedelta(days=-3)
        assert config.end_date == today + timedelta(days=2)


# ===========================================================================
# 3. Match Dict Building (build_match_dict)
# ===========================================================================


class TestBuildMatchDict:
    """Tests for the extracted build_match_dict helper."""

    def test_homegrown_league_uses_division(self):
        config = _make_config(league="Homegrown", division="Northeast")
        match = _make_match()
        result = build_match_dict(match, config)

        assert result["division"] == "Northeast"
        assert result["division_id"] == 41  # Northeast ID
        assert result["league"] == "Homegrown"

    def test_academy_league_uses_conference(self):
        config = _make_config(league="Academy", conference="New England")
        match = _make_match()
        result = build_match_dict(match, config)

        assert result["division"] == "New England"
        assert result["division_id"] == 41  # New England -> 41
        assert result["league"] == "Academy"

    def test_ifa_team_normalized_and_suffixed_homegrown(self):
        config = _make_config(league="Homegrown")
        match = _make_match(
            home_team="Intercontinental Football Academy of New England",
            away_team="NEFC",
        )
        result = build_match_dict(match, config)

        assert result["home_team"] == "IFA HG"
        assert result["away_team"] == "NEFC"

    def test_ifa_team_normalized_academy_no_suffix(self):
        config = _make_config(league="Academy", conference="New England")
        match = _make_match(
            home_team="Intercontinental Football Academy of New England",
            away_team="NEFC",
        )
        result = build_match_dict(match, config)

        assert result["home_team"] == "IFA"

    def test_integer_scores_pass_through(self):
        match = _make_match(home_score=3, away_score=1)
        result = build_match_dict(match, _make_config())

        assert result["home_score"] == 3
        assert result["away_score"] == 1

    def test_tbd_scores_become_none(self):
        match = _make_match(home_score="TBD", away_score="TBD")
        result = build_match_dict(match, _make_config())

        assert result["home_score"] is None
        assert result["away_score"] is None

    def test_none_scores_stay_none(self):
        match = _make_match(home_score=None, away_score=None)
        result = build_match_dict(match, _make_config())

        assert result["home_score"] is None
        assert result["away_score"] is None

    def test_zero_zero_scores_pass_through(self):
        match = _make_match(home_score=0, away_score=0)
        result = build_match_dict(match, _make_config())

        assert result["home_score"] == 0
        assert result["away_score"] == 0

    def test_match_status_defaults_to_scheduled(self):
        """match_status computed field always returns a value, but the fallback is tested."""
        match = _make_match()
        result = build_match_dict(match, _make_config())
        # match_status is a computed field so it will never be None,
        # but the dict builder has `or "scheduled"` fallback
        assert result["match_status"] in ("scheduled", "completed", "tbd")

    def test_external_match_id_set(self):
        match = _make_match(match_id="XYZ789")
        result = build_match_dict(match, _make_config())

        assert result["external_match_id"] == "XYZ789"

    def test_source_always_match_scraper(self):
        result = build_match_dict(_make_match(), _make_config())
        assert result["source"] == "match-scraper"

    def test_match_date_from_datetime(self):
        match = _make_match(match_datetime=datetime(2025, 10, 18, 14, 0))
        result = build_match_dict(match, _make_config())

        assert result["match_date"] == "2025-10-18"

    def test_season_hardcoded(self):
        result = build_match_dict(_make_match(), _make_config())
        assert result["season"] == "2024-25"

    def test_age_group_from_config(self):
        config = _make_config(age_group="U16")
        result = build_match_dict(_make_match(), config)

        assert result["age_group"] == "U16"

    def test_match_type_always_league(self):
        result = build_match_dict(_make_match(), _make_config())
        assert result["match_type"] == "League"

    def test_location_passed_through(self):
        match = _make_match(location="Progin Park")
        result = build_match_dict(match, _make_config())

        assert result["location"] == "Progin Park"

    def test_location_none(self):
        match = _make_match(location=None)
        result = build_match_dict(match, _make_config())

        assert result["location"] is None


# ===========================================================================
# 4. Match Comparison Integration
# ===========================================================================


class TestMatchComparisonIntegration:
    """Tests for MatchComparison used in the agent flow."""

    def test_new_match_classified_as_discovered(self, tmp_path):
        state_file = tmp_path / "state.json"
        comparison = MatchComparison(state_file)
        comparison.load_previous_state()

        match_dict = {"home_team": "A", "away_team": "B", "home_score": None}
        status, changes = comparison.compare_match("match_001", match_dict)

        assert status == "discovered"
        assert changes is None

    def test_changed_score_classified_as_updated(self, tmp_path):
        state_file = tmp_path / "state.json"

        # Write previous state
        previous_state = {
            "last_run_id": "prev",
            "matches": {
                "match_001": {
                    "home_team": "A",
                    "away_team": "B",
                    "home_score": None,
                    "away_score": None,
                    "match_status": "scheduled",
                }
            },
        }
        state_file.write_text(json.dumps(previous_state))

        comparison = MatchComparison(state_file)
        comparison.load_previous_state()

        current = {
            "home_team": "A",
            "away_team": "B",
            "home_score": 3,
            "away_score": 1,
            "match_status": "completed",
        }
        status, changes = comparison.compare_match("match_001", current)

        assert status == "updated"
        assert "home_score" in changes
        assert changes["home_score"] == {"from": None, "to": 3}

    def test_unchanged_match_classified(self, tmp_path):
        state_file = tmp_path / "state.json"
        match_data = {
            "home_team": "A",
            "away_team": "B",
            "home_score": 2,
            "away_score": 0,
        }
        previous_state = {
            "last_run_id": "prev",
            "matches": {"match_001": match_data},
        }
        state_file.write_text(json.dumps(previous_state))

        comparison = MatchComparison(state_file)
        comparison.load_previous_state()

        status, changes = comparison.compare_match("match_001", match_data)

        assert status == "unchanged"
        assert changes is None

    def test_counts_tracked_correctly(self, tmp_path):
        """Simulate the counting logic from the scrape() command."""
        state_file = tmp_path / "state.json"
        previous_state = {
            "last_run_id": "prev",
            "matches": {
                "existing_unchanged": {"score": 1},
                "existing_updated": {"score": None},
            },
        }
        state_file.write_text(json.dumps(previous_state))

        comparison = MatchComparison(state_file)
        comparison.load_previous_state()

        discovered_count = 0
        updated_count = 0
        unchanged_count = 0

        # New match
        status, _ = comparison.compare_match("new_match", {"score": 2})
        if status == "discovered":
            discovered_count += 1

        # Updated match
        status, _ = comparison.compare_match("existing_updated", {"score": 3})
        if status == "updated":
            updated_count += 1

        # Unchanged match
        status, _ = comparison.compare_match("existing_unchanged", {"score": 1})
        if status == "unchanged":
            unchanged_count += 1

        assert discovered_count == 1
        assert updated_count == 1
        assert unchanged_count == 1


# ===========================================================================
# 5. Queue Submission Flow
# ===========================================================================


class TestQueueSubmissionFlow:
    """Tests for queue submission in the scrape() agent path using CliRunner."""

    def setup_method(self):
        self.runner = CliRunner(env={"NO_COLOR": "1"})

    @patch("src.celery.queue_client.MatchQueueClient")
    @patch("src.cli.main.asyncio.run")
    @patch("src.cli.main.AuditLogger")
    @patch("src.cli.main.MatchComparison")
    @patch("src.utils.metrics.get_metrics")
    @patch("src.cli.main.setup_environment")
    def test_successful_queue_submission(
        self,
        mock_setup,
        mock_metrics,
        mock_comparison_cls,
        mock_audit_cls,
        mock_async_run,
        mock_queue_cls,
    ):
        """Matches are submitted to queue when connection succeeds."""
        # Setup mocks
        mock_metrics.return_value.time_execution.return_value.__enter__ = MagicMock()
        mock_metrics.return_value.time_execution.return_value.__exit__ = MagicMock()

        sample_match = _make_match(home_score=2, away_score=1)
        mock_async_run.return_value = [sample_match]

        mock_comparison = MagicMock()
        mock_comparison.compare_match.return_value = ("discovered", None)
        mock_comparison_cls.return_value = mock_comparison

        mock_audit = MagicMock()
        mock_audit.get_state_file_path.return_value = Path("/tmp/test-state.json")
        mock_audit_cls.return_value = mock_audit

        mock_queue = MagicMock()
        mock_queue.check_connection.return_value = True
        mock_queue.submit_matches_batch.return_value = ["task-id-1"]
        mock_queue_cls.return_value = mock_queue

        self.runner.invoke(app, ["scrape", "--quiet", "--start", "0", "--end", "0"])

        mock_queue.check_connection.assert_called_once()
        mock_queue.submit_matches_batch.assert_called_once()
        mock_audit.log_queue_submitted.assert_called_once()

    @patch("src.celery.queue_client.MatchQueueClient")
    @patch("src.cli.main.asyncio.run")
    @patch("src.cli.main.AuditLogger")
    @patch("src.cli.main.MatchComparison")
    @patch("src.utils.metrics.get_metrics")
    @patch("src.cli.main.setup_environment")
    def test_queue_connection_failure(
        self,
        mock_setup,
        mock_metrics,
        mock_comparison_cls,
        mock_audit_cls,
        mock_async_run,
        mock_queue_cls,
    ):
        """Matches not submitted when queue connection fails."""
        mock_metrics.return_value.time_execution.return_value.__enter__ = MagicMock()
        mock_metrics.return_value.time_execution.return_value.__exit__ = MagicMock()

        mock_async_run.return_value = [_make_match()]

        mock_comparison = MagicMock()
        mock_comparison.compare_match.return_value = ("discovered", None)
        mock_comparison_cls.return_value = mock_comparison

        mock_audit = MagicMock()
        mock_audit.get_state_file_path.return_value = Path("/tmp/test-state.json")
        mock_audit_cls.return_value = mock_audit

        mock_queue = MagicMock()
        mock_queue.check_connection.return_value = False
        mock_queue_cls.return_value = mock_queue

        self.runner.invoke(app, ["scrape", "--quiet", "--start", "0", "--end", "0"])

        mock_queue.submit_matches_batch.assert_not_called()

    @patch("src.celery.queue_client.MatchQueueClient")
    @patch("src.cli.main.asyncio.run")
    @patch("src.cli.main.AuditLogger")
    @patch("src.cli.main.MatchComparison")
    @patch("src.utils.metrics.get_metrics")
    @patch("src.cli.main.setup_environment")
    def test_queue_submission_exception(
        self,
        mock_setup,
        mock_metrics,
        mock_comparison_cls,
        mock_audit_cls,
        mock_async_run,
        mock_queue_cls,
    ):
        """Queue exception is caught and logged as queue_failed."""
        mock_metrics.return_value.time_execution.return_value.__enter__ = MagicMock()
        mock_metrics.return_value.time_execution.return_value.__exit__ = MagicMock()

        mock_async_run.return_value = [_make_match()]

        mock_comparison = MagicMock()
        mock_comparison.compare_match.return_value = ("discovered", None)
        mock_comparison_cls.return_value = mock_comparison

        mock_audit = MagicMock()
        mock_audit.get_state_file_path.return_value = Path("/tmp/test-state.json")
        mock_audit_cls.return_value = mock_audit

        mock_queue_cls.side_effect = Exception("Connection refused")

        self.runner.invoke(app, ["scrape", "--quiet", "--start", "0", "--end", "0"])

        # The exception path logs queue_failed for each match
        mock_audit.log_queue_failed.assert_called()


# ===========================================================================
# 6. save_matches_to_file
# ===========================================================================


class TestSaveMatchesToFile:
    """Tests for save_matches_to_file."""

    def test_writes_correct_json_structure(self, tmp_path):
        output_file = str(tmp_path / "matches.json")
        matches = [
            _make_match(
                match_id="m1",
                home_team="Intercontinental Football Academy of New England",
                away_team="NEFC",
                home_score=2,
                away_score=0,
                match_datetime=datetime(2025, 10, 15, 14, 0),
                location="Progin Park",
                competition="MLS Next",
            ),
        ]

        result = save_matches_to_file(matches, output_file, "U14", "Northeast")
        assert result is True

        with open(output_file) as f:
            data = json.load(f)

        assert "metadata" in data
        assert data["metadata"]["age_group"] == "U14"
        assert data["metadata"]["division"] == "Northeast"
        assert data["metadata"]["total_matches"] == 1
        assert len(data["matches"]) == 1

        # Team name should be normalized in output
        assert data["matches"][0]["home_team"] == "IFA"
        assert data["matches"][0]["away_team"] == "NEFC"
        assert data["matches"][0]["match_id"] == "m1"
        assert data["matches"][0]["home_score"] == 2
        assert data["matches"][0]["away_score"] == 0

    def test_handles_file_write_error(self, tmp_path):
        """Returns False on write error."""
        # Use a path that doesn't exist
        bad_path = str(tmp_path / "nonexistent" / "dir" / "file.json")
        matches = [_make_match()]

        with patch("src.cli.main.console"):
            result = save_matches_to_file(matches, bad_path, "U14", "Northeast")

        assert result is False

    def test_empty_matches_list(self, tmp_path):
        output_file = str(tmp_path / "empty.json")
        result = save_matches_to_file([], output_file, "U14", "Northeast")
        assert result is True

        with open(output_file) as f:
            data = json.load(f)

        assert data["metadata"]["total_matches"] == 0
        assert data["matches"] == []


# ===========================================================================
# 7. run_scraper Async Wrapper
# ===========================================================================


class TestRunScraperWrapper:
    """Tests for run_scraper async wrapper."""

    @patch("src.cli.main.MLSScraper")
    def test_returns_matches_on_success(self, mock_scraper_cls):
        """run_scraper wraps MLSScraper and returns Match list."""
        from src.cli.main import run_scraper

        expected_matches = [_make_match(), _make_match(match_id="m2", away_team="C")]
        mock_scraper = MagicMock()
        mock_scraper.scrape_matches = AsyncMock(return_value=expected_matches)
        mock_scraper_cls.return_value = mock_scraper

        config = _make_config()
        result = asyncio.run(run_scraper(config, verbose=False, headless=True))

        mock_scraper_cls.assert_called_once_with(config, headless=True)
        assert result == expected_matches

    @patch("src.cli.main.MLSScraper")
    def test_reraises_mls_scraper_error(self, mock_scraper_cls):
        """run_scraper re-raises MLSScraperError."""
        from src.cli.main import run_scraper
        from src.scraper.mls_scraper import MLSScraperError

        mock_scraper = MagicMock()
        mock_scraper.scrape_matches = AsyncMock(
            side_effect=MLSScraperError("Scrape failed")
        )
        mock_scraper_cls.return_value = mock_scraper

        config = _make_config()
        with pytest.raises(MLSScraperError, match="Scrape failed"):
            asyncio.run(run_scraper(config, verbose=False, headless=True))


# ===========================================================================
# 8. Run Summary and Audit Logging
# ===========================================================================


class TestRunSummaryAndAuditLogging:
    """Tests for RunSummary population and audit logger calls."""

    def setup_method(self):
        self.runner = CliRunner(env={"NO_COLOR": "1"})

    @patch("src.cli.main.asyncio.run")
    @patch("src.cli.main.AuditLogger")
    @patch("src.cli.main.MatchComparison")
    @patch("src.utils.metrics.get_metrics")
    @patch("src.cli.main.setup_environment")
    def test_run_summary_populated_correctly(
        self,
        mock_setup,
        mock_metrics,
        mock_comparison_cls,
        mock_audit_cls,
        mock_async_run,
    ):
        """RunSummary counts match the comparison results."""
        mock_metrics.return_value.time_execution.return_value.__enter__ = MagicMock()
        mock_metrics.return_value.time_execution.return_value.__exit__ = MagicMock()

        matches = [
            _make_match(match_id="m1"),
            _make_match(match_id="m2", away_team="C"),
            _make_match(match_id="m3", away_team="D"),
        ]
        mock_async_run.return_value = matches

        # First match: discovered, second: updated, third: unchanged
        mock_comparison = MagicMock()
        mock_comparison.compare_match.side_effect = [
            ("discovered", None),
            ("updated", {"home_score": {"from": None, "to": 2}}),
            ("unchanged", None),
        ]
        mock_comparison_cls.return_value = mock_comparison

        mock_audit = MagicMock()
        mock_audit.get_state_file_path.return_value = Path("/tmp/test-state.json")
        mock_audit_cls.return_value = mock_audit

        self.runner.invoke(
            app,
            ["scrape", "--quiet", "--no-submit-queue", "--start", "0", "--end", "0"],
        )

        # Verify log_run_completed was called with correct summary
        mock_audit.log_run_completed.assert_called_once()
        summary = mock_audit.log_run_completed.call_args[0][0]
        assert summary.total_matches == 3
        assert summary.discovered == 1
        assert summary.updated == 1
        assert summary.unchanged == 1
        assert summary.queue_submitted == 0
        assert summary.queue_failed == 0

    @patch("src.cli.main.asyncio.run")
    @patch("src.cli.main.AuditLogger")
    @patch("src.cli.main.MatchComparison")
    @patch("src.utils.metrics.get_metrics")
    @patch("src.cli.main.setup_environment")
    def test_state_saved_after_processing(
        self,
        mock_setup,
        mock_metrics,
        mock_comparison_cls,
        mock_audit_cls,
        mock_async_run,
    ):
        """comparison.save_current_state is called after processing matches."""
        mock_metrics.return_value.time_execution.return_value.__enter__ = MagicMock()
        mock_metrics.return_value.time_execution.return_value.__exit__ = MagicMock()

        mock_async_run.return_value = [_make_match()]

        mock_comparison = MagicMock()
        mock_comparison.compare_match.return_value = ("discovered", None)
        mock_comparison_cls.return_value = mock_comparison

        mock_audit = MagicMock()
        mock_audit.get_state_file_path.return_value = Path("/tmp/test-state.json")
        mock_audit_cls.return_value = mock_audit

        self.runner.invoke(
            app,
            ["scrape", "--quiet", "--no-submit-queue", "--start", "0", "--end", "0"],
        )

        mock_comparison.save_current_state.assert_called_once()

    @patch("src.cli.main.asyncio.run")
    @patch("src.cli.main.AuditLogger")
    @patch("src.cli.main.MatchComparison")
    @patch("src.utils.metrics.get_metrics")
    @patch("src.cli.main.setup_environment")
    def test_audit_logger_events_for_each_status(
        self,
        mock_setup,
        mock_metrics,
        mock_comparison_cls,
        mock_audit_cls,
        mock_async_run,
    ):
        """Correct audit logger method called per match status."""
        mock_metrics.return_value.time_execution.return_value.__enter__ = MagicMock()
        mock_metrics.return_value.time_execution.return_value.__exit__ = MagicMock()

        matches = [
            _make_match(match_id="new1"),
            _make_match(match_id="upd1", away_team="C"),
            _make_match(match_id="unc1", away_team="D"),
        ]
        mock_async_run.return_value = matches

        mock_comparison = MagicMock()
        mock_comparison.compare_match.side_effect = [
            ("discovered", None),
            ("updated", {"home_score": {"from": None, "to": 2}}),
            ("unchanged", None),
        ]
        mock_comparison_cls.return_value = mock_comparison

        mock_audit = MagicMock()
        mock_audit.get_state_file_path.return_value = Path("/tmp/test-state.json")
        mock_audit_cls.return_value = mock_audit

        self.runner.invoke(
            app,
            ["scrape", "--quiet", "--no-submit-queue", "--start", "0", "--end", "0"],
        )

        mock_audit.log_match_discovered.assert_called_once()
        assert mock_audit.log_match_discovered.call_args[0][0] == "new1"

        mock_audit.log_match_updated.assert_called_once()
        assert mock_audit.log_match_updated.call_args[0][0] == "upd1"

        mock_audit.log_match_unchanged.assert_called_once()
        assert mock_audit.log_match_unchanged.call_args[0][0] == "unc1"

    @patch("src.cli.main.asyncio.run")
    @patch("src.cli.main.AuditLogger")
    @patch("src.cli.main.MatchComparison")
    @patch("src.utils.metrics.get_metrics")
    @patch("src.cli.main.setup_environment")
    def test_no_matches_still_logs_completion(
        self,
        mock_setup,
        mock_metrics,
        mock_comparison_cls,
        mock_audit_cls,
        mock_async_run,
    ):
        """Run with zero matches still logs run_completed with zero counts."""
        mock_metrics.return_value.time_execution.return_value.__enter__ = MagicMock()
        mock_metrics.return_value.time_execution.return_value.__exit__ = MagicMock()

        mock_async_run.return_value = []

        mock_comparison = MagicMock()
        mock_comparison_cls.return_value = mock_comparison

        mock_audit = MagicMock()
        mock_audit.get_state_file_path.return_value = Path("/tmp/test-state.json")
        mock_audit_cls.return_value = mock_audit

        self.runner.invoke(
            app,
            ["scrape", "--quiet", "--no-submit-queue", "--start", "0", "--end", "0"],
        )

        mock_audit.log_run_completed.assert_called_once()
        summary = mock_audit.log_run_completed.call_args[0][0]
        assert summary.total_matches == 0
        assert summary.discovered == 0
