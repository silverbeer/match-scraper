"""Unit tests for schedule release detection (SB-499)."""

from datetime import date, datetime, timezone

import pytest

from src.models.schedule_release import DivisionRelease, ReleaseProbe, ReleaseState
from src.scraper.modular11 import (
    AGE_GROUP_IDS,
    DIVISION_GROUP_IDS,
    PRIORITY_DIVISIONS,
    current_season_year,
    fall_segment_window,
    season_label,
    season_window,
)
from src.scraper.release_detector import (
    ReleaseDetectorError,
    ScheduleReleaseDetector,
    count_matches,
)

# The pre-release response, verbatim from the live endpoint on 2026-08-02.
EMPTY_RESPONSE = '<div class="text-center"><p>No data available.</p></div>'

MATCH_ROW = (
    '<div class="row table-content-row" js-match-game="1" '
    'js-match-group="Northeast">Downtown United vs Long Island</div>'
)


class TestSeasonHelpers:
    """Season boundaries must be derived, not pinned — that is what went stale."""

    @pytest.mark.parametrize(
        ("today", "expected"),
        [
            (date(2026, 8, 1), 2026),  # first day of the season
            (date(2026, 8, 2), 2026),
            (date(2026, 12, 31), 2026),
            (date(2027, 1, 1), 2026),  # still the 2026-2027 season
            (date(2027, 7, 31), 2026),
            (date(2027, 8, 1), 2027),  # rolls over
        ],
    )
    def test_current_season_year(self, today, expected):
        assert current_season_year(today) == expected

    def test_season_label_format_matches_agent(self):
        """The agent posts '2026-2027'; this repo must not diverge to '26-27'."""
        assert season_label(2026) == "2026-2027"

    def test_season_window_spans_august_to_july(self):
        start, end = season_window(2026)
        assert start == date(2026, 8, 1)
        assert end == date(2027, 7, 15)

    def test_fall_segment_stops_at_year_end(self):
        start, end = fall_segment_window(2026)
        assert start == date(2026, 8, 1)
        assert end == date(2026, 12, 31)

    def test_fall_window_is_inside_season_window(self):
        s_start, s_end = season_window(2026)
        f_start, f_end = fall_segment_window(2026)
        assert s_start <= f_start
        assert f_end <= s_end


class TestModular11Constants:
    def test_priority_divisions_are_known(self):
        for division in PRIORITY_DIVISIONS:
            assert division in DIVISION_GROUP_IDS

    def test_priority_division_ids_match_live_site(self):
        """Verified against select[js-groups] on 2026-08-02."""
        assert DIVISION_GROUP_IDS["Northeast"] == "41"
        assert DIVISION_GROUP_IDS["Florida"] == "46"
        assert DIVISION_GROUP_IDS["Mid-Atlantic"] == "68"

    def test_age_group_ids_match_live_site(self):
        assert AGE_GROUP_IDS == {
            "U13": "21",
            "U14": "22",
            "U15": "33",
            "U16": "14",
            "U17": "15",
            "U19": "26",
        }


class TestCountMatches:
    def test_empty_marker_counts_as_zero(self):
        assert count_matches(EMPTY_RESPONSE) == 0

    def test_empty_marker_is_case_insensitive(self):
        assert count_matches("<p>NO DATA AVAILABLE.</p>") == 0

    def test_blank_response_counts_as_zero(self):
        assert count_matches("") == 0
        assert count_matches("   \n  ") == 0

    def test_counts_match_rows(self):
        assert count_matches(MATCH_ROW * 3) == 3

    def test_html_without_rows_counts_as_zero(self):
        assert count_matches("<div class='wrapper'><p>Something else</p></div>") == 0


class TestDetectorValidation:
    def test_rejects_unknown_age_group(self):
        with pytest.raises(ReleaseDetectorError, match="Unknown age groups"):
            ScheduleReleaseDetector(age_groups=["U12"])

    def test_rejects_unknown_division(self):
        with pytest.raises(ReleaseDetectorError, match="Unknown divisions"):
            ScheduleReleaseDetector(divisions=["Atlantis"])

    def test_defaults_to_priority_targets(self):
        detector = ScheduleReleaseDetector()
        assert detector.divisions == list(PRIORITY_DIVISIONS)
        assert detector.age_groups[0] == "U15", "U15 is the top priority for SB-499"

    def test_fall_only_narrows_the_window(self):
        full = ScheduleReleaseDetector(season_year=2026, fall_only=False).window
        fall = ScheduleReleaseDetector(season_year=2026, fall_only=True).window
        assert fall[1] < full[1]


def _result(age="U15", division="Northeast", state=ReleaseState.EMPTY, count=0):
    return DivisionRelease(
        age_group=age, division=division, state=state, match_count=count
    )


def _probe(results):
    return ReleaseProbe(
        season="2026-2027",
        window_start=date(2026, 8, 1),
        window_end=date(2026, 12, 31),
        checked_at=datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc),
        results=results,
    )


class TestReleaseProbe:
    def test_all_empty_is_not_released(self):
        probe = _probe([_result(), _result(age="U14")])
        assert not probe.is_released
        assert not probe.all_failed
        assert probe.total_matches == 0

    def test_one_live_target_means_released(self):
        probe = _probe(
            [_result(), _result(age="U14", state=ReleaseState.LIVE, count=25)]
        )
        assert probe.is_released
        assert len(probe.live) == 1
        assert probe.total_matches == 25

    def test_all_errors_flagged_separately_from_empty(self):
        """'MLS Next is down' must not read the same as 'schedule not out yet'."""
        probe = _probe(
            [
                _result(state=ReleaseState.ERROR),
                _result(age="U14", state=ReleaseState.ERROR),
            ]
        )
        assert probe.all_failed
        assert not probe.is_released

    def test_partial_errors_are_not_all_failed(self):
        probe = _probe([_result(), _result(age="U14", state=ReleaseState.ERROR)])
        assert not probe.all_failed
        assert len(probe.errors) == 1

    def test_empty_result_set_is_not_all_failed(self):
        assert not _probe([]).all_failed

    def test_summary_mentions_live_targets(self):
        probe = _probe([_result(state=ReleaseState.LIVE, count=25)])
        summary = probe.summary()
        assert "U15 Northeast" in summary
        assert "2026-2027" in summary

    def test_summary_when_nothing_published(self):
        assert "no fixtures yet" in _probe([_result()]).summary()

    def test_summary_when_everything_failed(self):
        probe = _probe([_result(state=ReleaseState.ERROR)])
        assert "failed to probe" in probe.summary()


class TestDivisionRelease:
    def test_label_is_age_then_division(self):
        assert _result().label == "U15 Northeast"

    def test_age_group_is_upper_cased(self):
        assert (
            DivisionRelease(
                age_group=" u15 ", division="Northeast", state=ReleaseState.EMPTY
            ).age_group
            == "U15"
        )

    def test_blank_division_rejected(self):
        with pytest.raises(ValueError):
            DivisionRelease(age_group="U15", division="  ", state=ReleaseState.EMPTY)

    def test_is_live_tracks_state(self):
        assert _result(state=ReleaseState.LIVE).is_live
        assert not _result(state=ReleaseState.EMPTY).is_live
        assert not _result(state=ReleaseState.ERROR).is_live
