"""Tests for the run summary report builder."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from src.orchestrator.planner import RunPlan, ScrapeAction, ScrapePlan
from src.orchestrator.report import (
    _TELEGRAM_MAX_CHARS,
    _agent_awareness,
    _clamp_detail,
    _format_delta,
    _is_last_weekend,
    _missing_kickoff_section,
    _next_scheduled_run,
    _weekend_scores_section,
    build_failure_report,
    build_report,
    build_watchdog_report,
)

_ET = ZoneInfo("America/New_York")


def _match(
    home: str = "IFA",
    away: str = "Revolution",
    match_date: str = "2026-03-08",
    status: str = "completed",
    home_score: int | None = 2,
    away_score: int | None = 1,
    match_time: str | None = "15:00",
) -> dict:
    return {
        "home_team": home,
        "away_team": away,
        "match_date": match_date,
        "match_status": status,
        "home_score": home_score,
        "away_score": away_score,
        "match_time": match_time,
    }


class TestBuildReport:
    def test_basic_report_contains_header(self) -> None:
        now = datetime(2026, 3, 8, 14, 2, tzinfo=UTC)  # Saturday
        report = build_report(
            result_summary="Completed run",
            actions=[
                {"action": "scrape", "detail": "Scraped U14 HG NE", "dry_run": False}
            ],
            matches_found=5,
            matches_submitted=5,
            scraped_matches=[_match()],
            submission_errors=[],
            env="prod",
            target="u14-hg",
            dry_run=False,
            now=now,
        )
        assert "Match Scraper Report" in report
        assert "u14\\-hg" in report

    def test_dry_run_shown_in_header(self) -> None:
        now = datetime(2026, 3, 8, 14, 0, tzinfo=UTC)
        report = build_report(
            result_summary="",
            actions=[],
            matches_found=0,
            matches_submitted=0,
            scraped_matches=[],
            submission_errors=[],
            env="local",
            target=None,
            dry_run=True,
            now=now,
        )
        assert "DRY RUN" in report

    def test_errors_shown(self) -> None:
        now = datetime(2026, 3, 8, 14, 0, tzinfo=UTC)
        report = build_report(
            result_summary="",
            actions=[],
            matches_found=2,
            matches_submitted=1,
            scraped_matches=[_match()],
            submission_errors=[{"match": "IFA vs Rev", "error": "connection refused"}],
            env="prod",
            target=None,
            dry_run=False,
            now=now,
        )
        assert "Submission Errors" in report
        assert "connection refused" in report

    def test_next_run_shown(self) -> None:
        now = datetime(2026, 3, 8, 14, 2, tzinfo=UTC)  # March = EDT (UTC-4)
        report = build_report(
            result_summary="",
            actions=[],
            matches_found=0,
            matches_submitted=0,
            scraped_matches=[],
            submission_errors=[],
            env="prod",
            target=None,
            dry_run=False,
            now=now,
        )
        assert "Next run" in report
        # Sun 14:02 UTC is 10:02 AM EDT, and Sunday is hourly, so the next slot
        # is 11:00 AM ET. It used to assert 1:00 PM, from reading the schedule
        # hours as UTC when the CronJobs schedule in ET (SB-1060).
        assert "11:00 AM EDT" in report

    def test_today_missing_scores_shown(self) -> None:
        now = datetime(2026, 3, 8, 14, 0, tzinfo=UTC)  # Saturday
        matches = [
            _match(status="completed"),
            _match(
                home="NYCFC",
                away="Red Bulls",
                status="scheduled",
                home_score=None,
                away_score=None,
            ),
        ]
        report = build_report(
            result_summary="",
            actions=[],
            matches_found=2,
            matches_submitted=2,
            scraped_matches=matches,
            submission_errors=[],
            env="prod",
            target=None,
            dry_run=False,
            now=now,
        )
        assert "Awaiting Scores" in report
        assert "NYCFC" in report

    def test_weekend_scores_shown_on_monday(self) -> None:
        now = datetime(2026, 3, 9, 14, 0, tzinfo=UTC)  # Monday
        matches = [
            _match(
                match_date="2026-03-07", status="completed", home_score=3, away_score=1
            ),
            _match(
                home="NYCFC",
                away="Red Bulls",
                match_date="2026-03-08",
                status="completed",
                home_score=2,
                away_score=0,
            ),
            _match(
                home="Galaxy",
                away="LAFC",
                match_date="2026-03-08",
                status="scheduled",
                home_score=None,
                away_score=None,
            ),
        ]
        report = build_report(
            result_summary="",
            actions=[],
            matches_found=3,
            matches_submitted=3,
            scraped_matches=matches,
            submission_errors=[],
            env="prod",
            target=None,
            dry_run=False,
            now=now,
        )
        assert "Weekend Scores" in report
        assert "IFA" in report
        assert "NYCFC" in report
        # Missing match should be in Awaiting Scores, not Weekend Scores
        assert "Awaiting Scores" in report
        assert "Galaxy" in report

    def test_header_shows_edt(self) -> None:
        now = datetime(2026, 3, 8, 18, 10, tzinfo=UTC)  # March = EDT
        report = build_report(
            result_summary="",
            actions=[],
            matches_found=0,
            matches_submitted=0,
            scraped_matches=[],
            submission_errors=[],
            env="prod",
            target=None,
            dry_run=False,
            now=now,
        )
        assert "2:10 PM EDT" in report  # 18:10 UTC = 2:10 PM EDT


class TestAgentAwareness:
    def test_saturday(self) -> None:
        now = datetime(2026, 3, 7, 14, 0, tzinfo=UTC)  # Saturday
        result = _agent_awareness(now, [])
        assert "Active match day" in result

    def test_sunday(self) -> None:
        now = datetime(2026, 3, 8, 14, 0, tzinfo=UTC)  # Sunday
        result = _agent_awareness(now, [])
        assert "Active match day" in result

    def test_wednesday_all_scored(self) -> None:
        now = datetime(2026, 3, 11, 14, 0, tzinfo=UTC)  # Wednesday
        matches = [
            _match(match_date="2026-03-07", status="completed"),
            _match(match_date="2026-03-08", status="completed"),
        ]
        result = _agent_awareness(now, matches)
        assert "all weekend scores are posted" in result

    def test_monday_unscored(self) -> None:
        now = datetime(2026, 3, 9, 14, 0, tzinfo=UTC)  # Monday
        matches = [
            _match(match_date="2026-03-07", status="scheduled"),
        ]
        result = _agent_awareness(now, matches)
        assert "still awaiting scores" in result

    def test_thursday(self) -> None:
        now = datetime(2026, 3, 12, 14, 0, tzinfo=UTC)  # Thursday
        result = _agent_awareness(now, [])
        assert "routine schedule sync" in result


class TestIsLastWeekend:
    def test_last_saturday(self) -> None:
        now = datetime(2026, 3, 9, 14, 0, tzinfo=UTC)  # Monday
        assert _is_last_weekend("2026-03-07", now) is True  # Saturday

    def test_last_sunday(self) -> None:
        now = datetime(2026, 3, 9, 14, 0, tzinfo=UTC)  # Monday
        assert _is_last_weekend("2026-03-08", now) is True  # Sunday

    def test_older_weekend(self) -> None:
        now = datetime(2026, 3, 9, 14, 0, tzinfo=UTC)  # Monday
        assert _is_last_weekend("2026-02-28", now) is False  # Previous Sat

    def test_weekday(self) -> None:
        now = datetime(2026, 3, 9, 14, 0, tzinfo=UTC)
        assert _is_last_weekend("2026-03-06", now) is False  # Friday


class TestNextScheduledRun:
    """The CronJobs schedule in America/New_York, so the answer is worked out
    there. These hours are ET, not UTC (SB-1060).

        weekdays   02, 08, 14, 20
        Saturday   02, 08, 14, then hourly 15-23
        Sunday     hourly 00-20
    """

    # --- weekdays -----------------------------------------------------------
    def test_mid_morning_weekday(self) -> None:
        now = datetime(2026, 3, 9, 10, 30, tzinfo=_ET)  # Monday
        next_run, _delta = _next_scheduled_run(now)
        assert next_run.hour == 14

    def test_after_last_slot_weekday(self) -> None:
        now = datetime(2026, 3, 9, 21, 0, tzinfo=_ET)  # Monday, past 20:00
        next_run, _delta = _next_scheduled_run(now)
        assert next_run.hour == 2
        assert next_run.day == 10  # Tuesday

    # --- Saturday -----------------------------------------------------------
    def test_saturday_morning_uses_the_base_schedule(self) -> None:
        """Before 15:00 the hourly window has not opened yet."""
        now = datetime(2026, 9, 12, 9, 0, tzinfo=_ET)
        next_run, _ = _next_scheduled_run(now)
        assert next_run.hour == 14

    def test_saturday_hourly_window_opens_at_15(self) -> None:
        now = datetime(2026, 9, 12, 14, 30, tzinfo=_ET)
        next_run, _ = _next_scheduled_run(now)
        assert next_run.hour == 15

    def test_saturday_inside_the_hourly_window(self) -> None:
        now = datetime(2026, 9, 12, 19, 30, tzinfo=_ET)
        next_run, _ = _next_scheduled_run(now)
        assert next_run.hour == 20
        assert next_run.day == 12

    def test_saturday_last_slot_wraps_into_sunday(self) -> None:
        now = datetime(2026, 9, 12, 23, 30, tzinfo=_ET)
        next_run, _ = _next_scheduled_run(now)
        assert next_run.hour == 0
        assert next_run.day == 13  # Sunday

    # --- Sunday -------------------------------------------------------------
    def test_sunday_is_hourly(self) -> None:
        now = datetime(2026, 9, 13, 11, 15, tzinfo=_ET)
        next_run, _ = _next_scheduled_run(now)
        assert next_run.hour == 12

    def test_sunday_window_closes_at_20(self) -> None:
        """20:00 is the last slot of the weekend — the next is Monday 02:00."""
        now = datetime(2026, 9, 13, 20, 30, tzinfo=_ET)
        next_run, _ = _next_scheduled_run(now)
        assert next_run.hour == 2
        assert next_run.day == 14  # Monday

    # --- the zone itself ----------------------------------------------------
    def test_a_utc_now_is_converted_not_read_as_et(self) -> None:
        """Regression for SB-1060. 23:00 UTC on Saturday is 19:00 EDT, so the
        next run is 20:00 ET. Read as if it were already ET it would answer
        Sunday 00:00 — a five-hour lie in the report footer."""
        now = datetime(2026, 9, 12, 23, 0, tzinfo=UTC)
        next_run, delta = _next_scheduled_run(now)
        assert next_run.hour == 20
        assert next_run.day == 12
        assert delta.total_seconds() == 3600


class TestWeekendScores:
    def test_shows_scores_on_monday(self) -> None:
        now = datetime(2026, 3, 9, 14, 0, tzinfo=UTC)  # Monday
        matches = [
            _match(
                match_date="2026-03-07", status="completed", home_score=3, away_score=1
            ),
        ]
        lines = _weekend_scores_section(now, matches)
        assert len(lines) == 2
        assert "Weekend Scores" in lines[0]
        assert "3" in lines[1]
        assert "1" in lines[1]

    def test_hidden_on_thursday(self) -> None:
        now = datetime(2026, 3, 12, 14, 0, tzinfo=UTC)  # Thursday
        matches = [
            _match(match_date="2026-03-07", status="completed"),
        ]
        lines = _weekend_scores_section(now, matches)
        assert lines == []

    def test_excludes_unscored(self) -> None:
        now = datetime(2026, 3, 9, 14, 0, tzinfo=UTC)  # Monday
        matches = [
            _match(
                match_date="2026-03-07",
                status="scheduled",
                home_score=None,
                away_score=None,
            ),
        ]
        lines = _weekend_scores_section(now, matches)
        assert lines == []


class TestFormatDelta:
    def test_hours_and_minutes(self) -> None:
        from datetime import timedelta

        assert _format_delta(timedelta(hours=5, minutes=58)) == "5h 58m"

    def test_minutes_only(self) -> None:
        from datetime import timedelta

        assert _format_delta(timedelta(minutes=45)) == "45m"


class TestMissingKickoff:
    def test_missing_kickoff_shown(self) -> None:
        matches = [
            _match(
                status="scheduled", home_score=None, away_score=None, match_time=None
            ),
            _match(
                home="NYCFC",
                away="Red Bulls",
                status="scheduled",
                home_score=None,
                away_score=None,
                match_time=None,
            ),
            _match(status="completed", match_time="15:00"),
        ]
        lines = _missing_kickoff_section(matches)
        assert any("Missing Kick\\-off Times" in line for line in lines)
        assert len(lines) == 3  # header + 2 matches

    def test_no_kickoff_section_when_all_have_times(self) -> None:
        matches = [
            _match(
                status="scheduled", home_score=None, away_score=None, match_time="15:00"
            ),
            _match(status="completed", match_time="17:00"),
        ]
        lines = _missing_kickoff_section(matches)
        assert lines == []

    def test_no_kickoff_count_in_summary(self) -> None:
        now = datetime(2026, 3, 8, 14, 0, tzinfo=UTC)
        matches = [
            _match(
                status="scheduled", home_score=None, away_score=None, match_time=None
            ),
            _match(status="tbd", home_score=None, away_score=None, match_time=None),
            _match(status="completed", match_time="15:00"),
        ]
        report = build_report(
            result_summary="",
            actions=[],
            matches_found=3,
            matches_submitted=3,
            scraped_matches=matches,
            submission_errors=[],
            env="prod",
            target=None,
            dry_run=False,
            now=now,
        )
        assert "no time" in report

    def test_kickoff_plan_icon(self) -> None:
        from datetime import date

        from src.orchestrator.planner import RunPlan, ScrapeAction, ScrapePlan

        now = datetime(2026, 3, 12, 14, 0, tzinfo=UTC)
        plan = RunPlan(
            plans=[
                ScrapePlan(
                    target_key="u14-hg",
                    target_label="U14 Homegrown Northeast",
                    action=ScrapeAction.KICKOFF_SYNC,
                    start_date=date(2026, 3, 12),
                    end_date=date(2026, 3, 26),
                    reason="3 missing kick-off times",
                    scraper_params={},
                ),
            ]
        )
        report = build_report(
            result_summary="",
            actions=[],
            matches_found=0,
            matches_submitted=0,
            scraped_matches=[],
            submission_errors=[],
            env="prod",
            target=None,
            dry_run=False,
            scrape_plan=plan,
            now=now,
        )
        assert "⏰" in report


# ── Ingest failures: the gap between "submitted" and "landed" (SB-831) ──


def _failure(
    raw_name: str = "Intercontinental Football Academy of New England",
    kind: str = "team",
    match_count: int = 88,
) -> dict:
    return {
        "raw_name": raw_name,
        "kind": kind,
        "match_count": match_count,
        "league": "Homegrown",
    }


def _report(**overrides) -> str:
    defaults = {
        "result_summary": "Completed run",
        "actions": [],
        "matches_found": 100,
        "matches_submitted": 100,
        "scraped_matches": [_match()],
        "submission_errors": [],
        "env": "prod",
        "target": None,
        "dry_run": False,
        "now": datetime(2026, 9, 5, 14, 0, tzinfo=UTC),
    }
    return build_report(**{**defaults, **overrides})


class TestIngestFailuresSection:
    def test_a_clean_run_says_nothing_about_ingest(self) -> None:
        assert "Ingest Failures" not in _report(ingest_failures=[])

    def test_omitting_the_argument_is_the_old_behaviour(self) -> None:
        # The report is built from several call sites and by tests; a missing
        # argument must degrade to what it said before, not raise.
        assert "Ingest Failures" not in _report()

    def test_rejected_matches_appear_next_to_submitted(self) -> None:
        # "1432 submitted, 0 errors" was the whole problem: publishing to the
        # queue is not missing-table accepting the match. The two numbers only
        # mean anything side by side.
        report = _report(
            ingest_failures=[
                _failure(match_count=88),
                _failure("Connecticut United FC", match_count=61),
            ]
        )
        assert "100 submitted" in report
        assert "149 rejected by MT" in report

    def test_each_unresolved_name_is_listed_with_its_cost(self) -> None:
        report = _report(ingest_failures=[_failure(match_count=88)])
        assert "Intercontinental Football Academy of New England" in report
        assert "×88" in report

    def test_the_heading_counts_names_and_matches(self) -> None:
        report = _report(
            ingest_failures=[
                _failure(match_count=88),
                _failure("Turnpike", kind="division", match_count=3),
            ]
        )
        assert "2 names, 91 matches" in report

    def test_the_section_names_the_fix(self) -> None:
        assert "mt team alias add" in _report(ingest_failures=[_failure()])

    def test_the_kind_distinguishes_a_division_from_a_team(self) -> None:
        report = _report(
            ingest_failures=[_failure("Turnpike", kind="division", match_count=3)]
        )
        assert "division: Turnpike" in report

    def test_a_missing_count_does_not_break_the_report(self) -> None:
        # The API shape is another service's; a row without match_count should
        # cost a number in the summary, not the whole report.
        report = _report(ingest_failures=[{"raw_name": "Mystery FC", "kind": "team"}])
        assert "Mystery FC" in report


class TestTelegramLimit:
    """SB-1015 — Telegram rejects a message over 4096 chars with a 400.

    The 2026-2027 season put 71 targets in the plan, which rendered a 4920-char
    report, so every run reported nothing at all.
    """

    def _skip_actions(self, n: int) -> list[dict]:
        return [
            {
                "action": "skip",
                "detail": f"U15 Flex Bracket{i}: Up to date (30 matches, last played None)",
                "dry_run": False,
            }
            for i in range(n)
        ]

    def test_skip_actions_collapse_to_a_count(self) -> None:
        now = datetime(2026, 9, 5, 20, 0, tzinfo=UTC)
        report = build_report(
            result_summary="Completed run",
            actions=self._skip_actions(71),
            matches_found=0,
            matches_submitted=0,
            scraped_matches=[],
            submission_errors=[],
            env="prod",
            target=None,
            dry_run=False,
            now=now,
        )
        assert len(report) <= _TELEGRAM_MAX_CHARS
        assert "71 target\\(s\\) up to date" in report
        assert "Bracket0" not in report

    def test_scraped_actions_are_still_listed(self) -> None:
        now = datetime(2026, 9, 5, 20, 0, tzinfo=UTC)
        report = build_report(
            result_summary="Completed run",
            actions=[
                *self._skip_actions(70),
                {
                    "action": "scrape",
                    "detail": "U14 Homegrown Northeast: 18 matches",
                    "dry_run": False,
                },
            ],
            matches_found=18,
            matches_submitted=18,
            scraped_matches=[_match()],
            submission_errors=[],
            env="prod",
            target=None,
            dry_run=False,
            now=now,
        )
        assert "U14 Homegrown Northeast: 18 matches" in report
        assert "70 target\\(s\\) up to date" in report

    def test_long_report_is_clamped_and_keeps_the_footer(self) -> None:
        now = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)  # Monday
        matches = [
            _match(
                home=f"Some Long Club Name FC {i}",
                away=f"Another Long Club Name SC {i}",
                match_date="2026-09-05",
            )
            for i in range(400)
        ]
        report = build_report(
            result_summary="Completed run",
            actions=[
                {
                    "action": "scrape",
                    "detail": f"U15 Flex Bracket{i}: scraped 12 matches",
                    "dry_run": False,
                }
                for i in range(71)
            ],
            matches_found=400,
            matches_submitted=400,
            scraped_matches=matches,
            submission_errors=[],
            env="prod",
            target=None,
            dry_run=False,
            now=now,
        )
        assert len(report) <= _TELEGRAM_MAX_CHARS
        assert "line\\(s\\) dropped" in report
        assert report.splitlines()[-1].startswith("*Next run:*")

    def test_plan_lists_only_the_targets_being_scraped(self) -> None:
        now = datetime(2026, 9, 6, 6, 0, tzinfo=UTC)
        plan = RunPlan(
            plans=[
                ScrapePlan(
                    target_key="u14-hg",
                    target_label="U14 Homegrown Northeast",
                    action=ScrapeAction.SCORE_SYNC,
                    reason="4 match(es) awaiting scores",
                ),
                *[
                    ScrapePlan(
                        target_key=f"u15-flex-{i}",
                        target_label=f"U15 Flex Bracket{i}",
                        action=ScrapeAction.SKIP,
                        reason="Up to date (30 matches, last played None)",
                    )
                    for i in range(70)
                ],
            ],
            mt_api_status="ok",
        )
        report = build_report(
            result_summary="Completed run",
            actions=[],
            matches_found=0,
            matches_submitted=0,
            scraped_matches=[],
            submission_errors=[],
            env="prod",
            target=None,
            dry_run=False,
            mt_status="ok",
            scrape_plan=plan,
            now=now,
        )
        assert len(report) <= _TELEGRAM_MAX_CHARS
        assert "1 active, 70 skipped" in report
        assert "U14 Homegrown Northeast" in report
        assert "Bracket0" not in report


class TestAHundredTargets:
    """SB-1024 took the config from 71 targets to 112, and the first run of the
    new ones is a FULL_SYNC apiece — the case SB-1015's collapse-the-skips
    trick does not help with, because none of them are skips."""

    def _plan(self, n: int) -> RunPlan:
        return RunPlan(
            plans=[
                ScrapePlan(
                    target_key=f"u16-hg-conference{i}",
                    target_label=f"U16 Homegrown Conference {i}",
                    action=ScrapeAction.FULL_SYNC,
                    reason="No matches in MT — needs initial sync",
                )
                for i in range(n)
            ],
            mt_api_status="ok",
        )

    def test_a_backfill_run_still_sends(self) -> None:
        now = datetime(2026, 9, 7, 6, 0, tzinfo=UTC)
        report = build_report(
            result_summary="Completed run",
            actions=[
                {
                    "action": "scrape",
                    "detail": f"U16 Homegrown Conference {i}: 132 matches",
                    "dry_run": False,
                }
                for i in range(112)
            ],
            matches_found=8000,
            matches_submitted=8000,
            scraped_matches=[],
            submission_errors=[],
            env="prod",
            target=None,
            dry_run=False,
            mt_status="ok",
            scrape_plan=self._plan(112),
            now=now,
        )

        assert len(report) <= _TELEGRAM_MAX_CHARS
        assert "112 active, 0 skipped" in report
        assert report.splitlines()[-1].startswith("*Next run:*")

    def test_a_quiet_run_at_that_scale_is_short(self) -> None:
        """Once the backfill lands they are all skips again, and the whole
        report is a couple of lines."""
        now = datetime(2026, 9, 14, 6, 0, tzinfo=UTC)
        report = build_report(
            result_summary="Completed run",
            actions=[
                {
                    "action": "skip",
                    "detail": f"target {i}: Up to date",
                    "dry_run": False,
                }
                for i in range(112)
            ],
            matches_found=0,
            matches_submitted=0,
            scraped_matches=[],
            submission_errors=[],
            env="prod",
            target=None,
            dry_run=False,
            now=now,
        )

        assert len(report) < 500
        assert "112 target\\(s\\) up to date" in report


class TestBuildFailureReport:
    """A run that dies must say so. Every failure path used to exit silently,
    and silence was indistinguishable from a quiet weekend (SB-1062)."""

    NOW = datetime(2026, 9, 12, 18, 0, tzinfo=UTC)  # Sat 14:00 ET

    def _report(self, **kwargs) -> str:
        args = {
            "env": "prod",
            "run_id": "03833fd59feb",
            "reason": "missing-table did not answer, so no plan could be built",
            "now": self.NOW,
        }
        args.update(kwargs)
        return build_failure_report(**args)

    def test_says_plainly_that_nothing_was_scraped(self) -> None:
        """The old silence let a reader assume the quiet meant no work to do."""
        assert "No matches were scraped" in self._report()

    def test_names_the_environment_and_run(self) -> None:
        report = self._report()
        assert "prod" in report
        assert "03833fd59feb" in report

    def test_carries_the_reason_and_detail(self) -> None:
        report = self._report(detail="Server error '500 Internal Server Error'")
        assert "did not answer" in report
        assert "500 Internal Server Error" in report

    def test_names_the_phase_when_known(self) -> None:
        assert "planning" in self._report(phase="planning")

    def test_omits_optional_lines_when_absent(self) -> None:
        report = self._report()
        assert "Failed at:" not in report
        assert "Target:" not in report
        assert "Detail:" not in report

    def test_includes_a_target_for_a_targeted_run(self) -> None:
        # MarkdownV2 escaping: hyphens arrive backslashed.
        assert r"u14\-hg\-florida" in self._report(target="u14-hg-florida")

    def test_points_at_the_next_scheduled_run(self) -> None:
        """Saturday 14:00 ET is inside the base schedule; next is 15:00."""
        assert "3:00 PM EDT" in self._report()

    def test_stays_inside_the_telegram_limit(self) -> None:
        """A failure report that fails to send is the bug this change fixes."""
        report = self._report(detail="boom " * 5000)
        assert len(report) <= _TELEGRAM_MAX_CHARS


class TestClampDetail:
    def test_short_detail_is_untouched(self) -> None:
        assert _clamp_detail("a 500 from PostgREST") == "a 500 from PostgREST"

    def test_whitespace_is_collapsed(self) -> None:
        """Tracebacks and PostgREST errors arrive full of newlines."""
        assert _clamp_detail("line one\n\n  line two\t") == "line one line two"

    def test_long_detail_is_truncated_with_an_ellipsis(self) -> None:
        out = _clamp_detail("x" * 900, limit=100)
        assert len(out) == 100
        assert out.endswith("…")


class TestBuildWatchdogReport:
    NOW = datetime(2026, 9, 12, 18, 0, tzinfo=UTC)  # Sat 14:00 ET

    def test_reports_a_stale_journal_with_its_age(self) -> None:
        report = build_watchdog_report(
            env="prod",
            last_run_at="2026-09-11T18:00:29+00:00",
            age_hours=20.0,
            max_age_hours=8.0,
            reason="The last successful run was 20.0h ago",
            now=self.NOW,
        )
        assert "No successful run in too long" in report
        assert r"20\.0h" in report  # MarkdownV2 escapes the decimal point
        assert "8h limit" in report

    def test_reports_a_missing_journal(self) -> None:
        report = build_watchdog_report(
            env="prod",
            last_run_at=None,
            age_hours=None,
            max_age_hours=8.0,
            reason="No run journal could be read",
            now=self.NOW,
        )
        assert "No run journal found at all" in report

    def test_explains_that_the_agent_probably_never_started(self) -> None:
        """The distinguishing fact: the agent reports its own failures now, so
        silence from it points at never having run."""
        report = build_watchdog_report(
            env="prod",
            last_run_at=None,
            age_hours=None,
            max_age_hours=8.0,
            reason="No run journal could be read",
            now=self.NOW,
        )
        assert "never" in report and "started" in report
