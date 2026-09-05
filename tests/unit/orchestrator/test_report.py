"""Tests for the run summary report builder."""

from __future__ import annotations

from datetime import UTC, datetime

from src.orchestrator.planner import RunPlan, ScrapeAction, ScrapePlan
from src.orchestrator.report import (
    _TELEGRAM_MAX_CHARS,
    _agent_awareness,
    _format_delta,
    _is_last_weekend,
    _missing_kickoff_section,
    _next_scheduled_run,
    _weekend_scores_section,
    build_report,
)


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
        assert (
            "1:00 PM EDT" in report
        )  # Sun 14:02 UTC → next weekend slot 17:00 UTC = 1:00 PM EDT

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
    # Weekend schedule (Sat/Sun): 02:00, 05:00, 08:00, 11:00, 14:00, 17:00, 20:00, 23:00
    def test_mid_morning_weekend(self) -> None:
        now = datetime(2026, 3, 8, 10, 30, tzinfo=UTC)  # Sunday
        next_run, _delta = _next_scheduled_run(now)
        assert next_run.hour == 11

    def test_after_last_slot_weekend(self) -> None:
        now = datetime(2026, 3, 8, 23, 30, tzinfo=UTC)  # Sunday after last slot
        next_run, _delta = _next_scheduled_run(now)
        assert next_run.hour == 2
        assert next_run.day == 9  # Monday

    def test_before_first_slot_weekend(self) -> None:
        now = datetime(2026, 3, 8, 1, 0, tzinfo=UTC)  # Sunday
        next_run, _ = _next_scheduled_run(now)
        assert next_run.hour == 2

    def test_extra_slot_weekend(self) -> None:
        now = datetime(
            2026, 3, 8, 21, 0, tzinfo=UTC
        )  # Sunday 21:00 — extra slot at 23:00
        next_run, _ = _next_scheduled_run(now)
        assert next_run.hour == 23
        assert next_run.day == 8  # same day

    # Weekday schedule (Mon-Fri): 02:00, 08:00, 14:00, 20:00
    def test_mid_morning_weekday(self) -> None:
        now = datetime(2026, 3, 9, 10, 30, tzinfo=UTC)  # Monday
        next_run, _delta = _next_scheduled_run(now)
        assert next_run.hour == 14

    def test_after_last_slot_weekday(self) -> None:
        now = datetime(2026, 3, 9, 21, 0, tzinfo=UTC)  # Monday after last slot
        next_run, _delta = _next_scheduled_run(now)
        assert next_run.hour == 2
        assert next_run.day == 10  # Tuesday


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
