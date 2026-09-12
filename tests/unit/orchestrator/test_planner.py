"""Tests for the deterministic scrape planner."""

from __future__ import annotations

from datetime import date, timedelta

import httpx

from src.orchestrator import planner
from src.orchestrator.planner import (
    _KICKOFF_LOOKAHEAD_DAYS,
    ScrapeAction,
    _match_weekend_window,
    compute_scrape_plan,
)

SEASON_END = date(2026, 6, 30)
# Matching season start for the 2025-2026 fixtures these tests use, so the
# SB-546 clamp is a no-op here rather than rewriting every expected date.
SEASON_START = date(2025, 8, 1)

# Minimal target configs (mirrors _TARGET_SCRAPER_CONFIG without IFA entries)
SAMPLE_CONFIGS = {
    "u14-hg": {"age_group": "U14", "league": "Homegrown", "division": "Northeast"},
    "u13-hg": {"age_group": "U13", "league": "Homegrown", "division": "Northeast"},
    "u14-academy": {
        "age_group": "U14",
        "league": "Academy",
        "conference": "New England",
    },
    # IFA targets should be filtered out by the planner
    "u14-hg-ifa": {"age_group": "U14", "league": "Homegrown", "division": "Northeast"},
}


def _mt_target(
    age_group: str,
    league: str,
    division: str,
    total: int = 100,
    needs_score: int = 0,
    needs_kickoff: int = 0,
    last_played_date: str | None = None,
) -> dict:
    return {
        "age_group": age_group,
        "league": league,
        "division": division,
        "total": total,
        "needs_score": needs_score,
        "needs_kickoff": needs_kickoff,
        "by_status": {"scheduled": total},
        "date_range": {"earliest": "2026-03-01", "latest": "2026-06-28"},
        "last_played_date": last_played_date,
    }


class TestMatchWeekendWindow:
    """Two modes (SB-1064). At the weekend, scrape only the weekend being
    played; midweek, reconcile the one gone and look at the one coming.

    March 2026 reference: Sat 14th and Sun 15th are the weekend, Fri 13th
    precedes it, Mon 16th follows it. The next weekend is the 21st/22nd.
    """

    # --- the weekend in play: Friday .. Monday, four days -------------------
    def test_on_saturday(self):
        start, end = _match_weekend_window(date(2026, 3, 14))
        assert (start, end) == (date(2026, 3, 13), date(2026, 3, 16))

    def test_on_sunday(self):
        start, end = _match_weekend_window(date(2026, 3, 15))
        assert (start, end) == (date(2026, 3, 13), date(2026, 3, 16))

    def test_on_monday_still_the_weekend_just_gone(self):
        """Sunday evening's scores post on Monday — under SB-1058 a Sunday
        17:00 ET kick-off is not even due until 20:00 ET."""
        start, end = _match_weekend_window(date(2026, 3, 16))
        assert (start, end) == (date(2026, 3, 13), date(2026, 3, 16))

    def test_the_weekend_window_is_four_days(self):
        for day in (date(2026, 3, 14), date(2026, 3, 15), date(2026, 3, 16)):
            start, end = _match_weekend_window(day)
            assert (end - start).days + 1 == 4

    def test_the_weekend_window_excludes_the_next_weekend(self):
        """The whole point: next weekend's fixtures cannot have scores yet, and
        scraping for them 25 times over a weekend is most of the work wasted."""
        start, end = _match_weekend_window(date(2026, 3, 14))
        assert end < date(2026, 3, 21)  # Saturday of the following weekend

    # --- midweek reconciliation: last Friday .. next Monday, eleven days ----
    def test_on_tuesday(self):
        start, end = _match_weekend_window(date(2026, 3, 17))
        assert (start, end) == (date(2026, 3, 13), date(2026, 3, 23))

    def test_on_wednesday(self):
        start, end = _match_weekend_window(date(2026, 3, 18))
        assert (start, end) == (date(2026, 3, 13), date(2026, 3, 23))

    def test_on_thursday(self):
        start, end = _match_weekend_window(date(2026, 3, 19))
        assert (start, end) == (date(2026, 3, 13), date(2026, 3, 23))

    def test_on_friday(self):
        start, end = _match_weekend_window(date(2026, 3, 20))
        assert (start, end) == (date(2026, 3, 13), date(2026, 3, 23))

    def test_midweek_covers_both_the_weekend_gone_and_the_one_coming(self):
        start, end = _match_weekend_window(date(2026, 3, 18))  # Wednesday
        assert start <= date(2026, 3, 14) and date(2026, 3, 15) <= end  # gone
        assert start <= date(2026, 3, 21) and date(2026, 3, 22) <= end  # coming

    def test_every_day_of_the_week_is_covered(self):
        """No day may fall through to an empty or inverted window."""
        for i in range(7):
            day = date(2026, 3, 16) + timedelta(days=i)
            start, end = _match_weekend_window(day)
            assert start < end


class TestComputeScrapePlan:
    def test_all_targets_up_to_date_skips(self):
        mt_targets = [
            _mt_target(
                "U14",
                "Homegrown",
                "Northeast",
                total=105,
                last_played_date="2026-03-08",
            ),
            _mt_target(
                "U13",
                "Homegrown",
                "Northeast",
                total=100,
                last_played_date="2026-03-08",
            ),
            _mt_target(
                "U14", "Academy", "New England", total=99, last_played_date="2026-03-07"
            ),
        ]
        plan = compute_scrape_plan(
            mt_targets,
            SAMPLE_CONFIGS,
            date(2026, 3, 12),
            SEASON_END,
            SEASON_START,
        )

        assert len(plan.plans) == 3  # excludes u14-hg-ifa
        for p in plan.plans:
            assert p.action == ScrapeAction.SKIP
            assert "Up to date" in p.reason

    def test_needs_score_triggers_score_sync(self):
        mt_targets = [
            _mt_target(
                "U14",
                "Homegrown",
                "Northeast",
                total=105,
                needs_score=3,
                last_played_date="2026-03-08",
            ),
            _mt_target(
                "U13",
                "Homegrown",
                "Northeast",
                total=100,
                last_played_date="2026-03-08",
            ),
            _mt_target("U14", "Academy", "New England", total=99),
        ]
        plan = compute_scrape_plan(
            mt_targets,
            SAMPLE_CONFIGS,
            date(2026, 3, 12),
            SEASON_END,
            SEASON_START,
        )

        u14 = next(p for p in plan.plans if p.target_key == "u14-hg")
        assert u14.action == ScrapeAction.SCORE_SYNC
        assert u14.start_date == date(2026, 3, 6)  # Last Friday
        assert u14.end_date == date(2026, 3, 16)  # Monday after this weekend
        assert "3 match(es) awaiting scores" in u14.reason

    def test_missing_from_mt_triggers_full_sync(self):
        # Only U14 HG exists in MT, U13 and Academy are missing
        mt_targets = [
            _mt_target(
                "U14",
                "Homegrown",
                "Northeast",
                total=105,
                last_played_date="2026-03-08",
            ),
        ]
        plan = compute_scrape_plan(
            mt_targets,
            SAMPLE_CONFIGS,
            date(2026, 3, 12),
            SEASON_END,
            SEASON_START,
        )

        u13 = next(p for p in plan.plans if p.target_key == "u13-hg")
        assert u13.action == ScrapeAction.FULL_SYNC
        assert "No matches in MT" in u13.reason

        academy = next(p for p in plan.plans if p.target_key == "u14-academy")
        assert academy.action == ScrapeAction.FULL_SYNC

    def test_zero_total_triggers_full_sync(self):
        mt_targets = [
            _mt_target("U14", "Homegrown", "Northeast", total=0),
        ]
        plan = compute_scrape_plan(
            mt_targets,
            SAMPLE_CONFIGS,
            date(2026, 3, 12),
            SEASON_END,
            SEASON_START,
        )

        u14 = next(p for p in plan.plans if p.target_key == "u14-hg")
        assert u14.action == ScrapeAction.FULL_SYNC

    def test_empty_mt_response_full_sync_all(self):
        plan = compute_scrape_plan(
            [], SAMPLE_CONFIGS, date(2026, 3, 12), SEASON_END, SEASON_START
        )

        for p in plan.plans:
            assert p.action == ScrapeAction.FULL_SYNC

    def test_ifa_targets_excluded(self):
        plan = compute_scrape_plan(
            [], SAMPLE_CONFIGS, date(2026, 3, 12), SEASON_END, SEASON_START
        )
        keys = [p.target_key for p in plan.plans]
        assert "u14-hg-ifa" not in keys

    def test_academy_conference_mapping(self):
        """Academy targets use conference in config but division in MT response."""
        mt_targets = [
            _mt_target(
                "U14", "Academy", "New England", total=99, last_played_date="2026-03-07"
            ),
        ]
        plan = compute_scrape_plan(
            mt_targets,
            SAMPLE_CONFIGS,
            date(2026, 3, 12),
            SEASON_END,
            SEASON_START,
        )

        academy = next(p for p in plan.plans if p.target_key == "u14-academy")
        assert academy.action == ScrapeAction.SKIP

    def test_needs_kickoff_triggers_kickoff_sync(self):
        mt_targets = [
            _mt_target(
                "U14",
                "Homegrown",
                "Northeast",
                total=105,
                needs_score=0,
                needs_kickoff=3,
                last_played_date="2026-03-08",
            ),
        ]
        plan = compute_scrape_plan(
            mt_targets,
            SAMPLE_CONFIGS,
            date(2026, 3, 12),
            SEASON_END,
            SEASON_START,
        )

        u14 = next(p for p in plan.plans if p.target_key == "u14-hg")
        assert u14.action == ScrapeAction.KICKOFF_SYNC
        assert "3 match(es) missing kick-off time" in u14.reason

    def test_kickoff_sync_date_range(self):
        today = date(2026, 3, 12)
        mt_targets = [
            _mt_target(
                "U14",
                "Homegrown",
                "Northeast",
                total=105,
                needs_kickoff=2,
                last_played_date="2026-03-08",
            ),
        ]
        plan = compute_scrape_plan(
            mt_targets,
            SAMPLE_CONFIGS,
            today,
            SEASON_END,
            SEASON_START,
        )

        u14 = next(p for p in plan.plans if p.target_key == "u14-hg")
        assert u14.start_date == today
        assert u14.end_date == today + timedelta(days=_KICKOFF_LOOKAHEAD_DAYS)

    def test_needs_score_and_kickoff_merges(self):
        mt_targets = [
            _mt_target(
                "U14",
                "Homegrown",
                "Northeast",
                total=105,
                needs_score=3,
                needs_kickoff=2,
                last_played_date="2026-03-08",
            ),
        ]
        plan = compute_scrape_plan(
            mt_targets,
            SAMPLE_CONFIGS,
            date(2026, 3, 12),
            SEASON_END,
            SEASON_START,
        )

        u14 = next(p for p in plan.plans if p.target_key == "u14-hg")
        assert u14.action == ScrapeAction.SCORE_SYNC
        assert "awaiting scores" in u14.reason
        assert "missing kick-off" in u14.reason

    def test_needs_kickoff_zero_skips(self):
        mt_targets = [
            _mt_target(
                "U14",
                "Homegrown",
                "Northeast",
                total=105,
                needs_score=0,
                needs_kickoff=0,
                last_played_date="2026-03-08",
            ),
        ]
        plan = compute_scrape_plan(
            mt_targets,
            SAMPLE_CONFIGS,
            date(2026, 3, 12),
            SEASON_END,
            SEASON_START,
        )

        u14 = next(p for p in plan.plans if p.target_key == "u14-hg")
        assert u14.action == ScrapeAction.SKIP


class TestSeasonStartClamping:
    """
    MLS Next only serves dates from the season start forward (SB-546).

    Asking for anything earlier is not a smaller result — the calendar widget
    fails with "Failed to navigate to start date month" and the scrape returns
    nothing, silently.
    """

    SEASON_START = date(2026, 8, 1)
    SEASON_END = date(2027, 7, 15)

    def _plan(self, today, mt_targets=None):
        return compute_scrape_plan(
            mt_targets=mt_targets if mt_targets is not None else [],
            target_configs={
                "u15-hg": {
                    "age_group": "U15",
                    "league": "Homegrown",
                    "division": "Northeast",
                }
            },
            today=today,
            season_end=self.SEASON_END,
            season_start=self.SEASON_START,
        )

    def test_score_sync_window_cannot_predate_the_season(self):
        """
        On 2026-08-02 the raw weekend window starts 2026-07-24 — the previous
        season. This is the case that was still broken after SB-538.
        """
        mt = [
            {
                "age_group": "U15",
                "league": "Homegrown",
                "division": "Northeast",
                "total": 10,
                "needs_score": 3,
                "needs_kickoff": 0,
            }
        ]
        plan = self._plan(date(2026, 8, 2), mt)
        scrape = plan.plans[0]

        assert scrape.start_date >= self.SEASON_START
        assert scrape.start_date == self.SEASON_START

    def test_full_sync_start_is_clamped(self):
        plan = self._plan(date(2026, 7, 20))
        assert plan.plans[0].start_date >= self.SEASON_START

    def test_no_plan_ever_starts_before_the_season(self):
        """Sweep the rollover boundary — no window may predate the season."""
        for day in range(1, 32):
            for month, year in ((7, 2026), (8, 2026)):
                try:
                    today = date(year, month, day)
                except ValueError:
                    continue
                for mt in (
                    [],
                    [
                        {
                            "age_group": "U15",
                            "league": "Homegrown",
                            "division": "Northeast",
                            "total": 10,
                            "needs_score": 2,
                            "needs_kickoff": 0,
                        }
                    ],
                    [
                        {
                            "age_group": "U15",
                            "league": "Homegrown",
                            "division": "Northeast",
                            "total": 10,
                            "needs_score": 0,
                            "needs_kickoff": 4,
                        }
                    ],
                ):
                    plan = self._plan(today, mt)
                    for s in plan.plans:
                        assert s.start_date >= self.SEASON_START, f"{today} {s.action}"
                        assert s.end_date >= s.start_date, (
                            f"{today} {s.action} inverted"
                        )


# The Pathway and Flex target tests moved to test_targets.py in SB-1024: the
# targets are no longer a literal in cli.py to assert against, they are built
# from a recorded standings feed.


class TestBackfillingANewTarget:
    """A target MT has nothing for is scraped season-to-date (SB-1024).

    The forty Homegrown brackets added in SB-1024 came with a month of results
    already sitting in the feed. A FULL_SYNC starting at `today` would have
    collected the rest of the season and left every played fixture behind —
    and, because the next run would then find matches in MT, it would have
    settled into score-syncing a bracket whose first month never arrived.
    """

    SEASON_START = date(2026, 8, 1)
    SEASON_END = date(2027, 7, 15)
    TODAY = date(2026, 9, 7)

    CONFIG = {
        "u16-hg-mid-atlantic": {
            "age_group": "U16",
            "league": "Homegrown",
            "division": "Mid-Atlantic",
        }
    }

    def _plan(self, mt_targets):
        return compute_scrape_plan(
            mt_targets=mt_targets,
            target_configs=self.CONFIG,
            today=self.TODAY,
            season_end=self.SEASON_END,
            season_start=self.SEASON_START,
        ).plans[0]

    def test_a_target_mt_has_never_heard_of_backfills_the_season(self):
        plan = self._plan([])

        assert plan.action == ScrapeAction.FULL_SYNC
        assert plan.start_date == self.SEASON_START
        assert plan.end_date == self.SEASON_END

    def test_a_target_mt_reports_empty_backfills_the_season(self):
        """`bootstrap_divisions` is MT saying "this division exists and holds
        nothing" — the same case, arriving as a row rather than an absence."""
        plan = self._plan(
            [
                {
                    "age_group": "U16",
                    "league": "Homegrown",
                    "division": "Mid-Atlantic",
                    "total": 0,
                    "needs_score": 0,
                    "needs_kickoff": 0,
                }
            ]
        )

        assert plan.action == ScrapeAction.FULL_SYNC
        assert plan.start_date == self.SEASON_START

    def test_a_populated_target_is_not_backfilled(self):
        """Once the fixtures are in, the weekend window takes over — a
        season-long scrape four times a day is 40x the work for no news."""
        plan = self._plan(
            [
                {
                    "age_group": "U16",
                    "league": "Homegrown",
                    "division": "Mid-Atlantic",
                    "total": 132,
                    "needs_score": 4,
                    "needs_kickoff": 0,
                }
            ]
        )

        assert plan.action == ScrapeAction.SCORE_SYNC
        assert plan.start_date > self.SEASON_START


class TestFetchMtStatusRetry:
    """MT's match-summary endpoint 500s on a cold Supabase gateway timeout and
    succeeds on the call right behind it (SB-1055). The run halts fail-fast
    without a plan, so one flaky response used to cost the whole run."""

    URL = "https://api.example.test"
    OK_BODY = {"targets": [{"age_group": "U14", "league": "Homegrown", "total": 3}]}

    @staticmethod
    def _response(status_code: int, json_body: dict | None = None) -> httpx.Response:
        return httpx.Response(
            status_code,
            json=json_body if json_body is not None else {"detail": "boom"},
            request=httpx.Request(
                "GET", "https://api.example.test/api/agent/match-summary"
            ),
        )

    def _call(self, monkeypatch, responses):
        """Run fetch_mt_status against a scripted sequence of responses.

        Each entry is either an httpx.Response to return or an Exception to
        raise. Returns (result, attempt_count, recorded_sleeps).
        """
        remaining = list(responses)
        sleeps: list[float] = []

        def fake_get(*_args, **_kwargs):
            item = remaining.pop(0)
            if isinstance(item, Exception):
                raise item
            if item.status_code >= 400:
                raise httpx.HTTPStatusError(
                    "error", request=item.request, response=item
                )
            return item

        monkeypatch.setattr(httpx, "get", fake_get)
        monkeypatch.setattr(planner.time, "sleep", lambda d: sleeps.append(d))

        result = planner.fetch_mt_status(
            self.URL, "token", "2026-2027", today=date(2026, 9, 12)
        )
        return result, len(responses) - len(remaining), sleeps

    def test_a_cold_500_is_retried_and_the_run_survives(self, monkeypatch):
        (targets, status), attempts, sleeps = self._call(
            monkeypatch,
            [self._response(500), self._response(200, self.OK_BODY)],
        )

        assert status == "ok"
        assert len(targets) == 1
        assert attempts == 2
        assert sleeps == [2.0]

    def test_a_transport_error_is_retried_too(self, monkeypatch):
        (targets, status), attempts, _ = self._call(
            monkeypatch,
            [
                httpx.ConnectTimeout("timed out"),
                self._response(200, self.OK_BODY),
            ],
        )

        assert status == "ok"
        assert attempts == 2

    def test_backoff_doubles_and_gives_up_after_four_attempts(self, monkeypatch):
        (targets, status), attempts, sleeps = self._call(
            monkeypatch, [self._response(500)] * planner._MT_FETCH_ATTEMPTS
        )

        assert targets == []
        assert status.startswith("failed:")
        assert attempts == planner._MT_FETCH_ATTEMPTS
        # Three waits between four attempts, no wait after the last one.
        assert sleeps == [2.0, 4.0, 8.0]

    def test_a_4xx_is_not_retried(self, monkeypatch):
        """A bad token or a bad query returns the same answer every time —
        retrying only delays the failure the report needs to show."""
        (targets, status), attempts, sleeps = self._call(
            monkeypatch, [self._response(401)]
        )

        assert targets == []
        assert status.startswith("failed:")
        assert attempts == 1
        assert sleeps == []

    def test_a_first_attempt_success_does_not_sleep(self, monkeypatch):
        (targets, status), attempts, sleeps = self._call(
            monkeypatch, [self._response(200, self.OK_BODY)]
        )

        assert status == "ok"
        assert attempts == 1
        assert sleeps == []

    def test_an_empty_target_list_is_still_reported_as_empty(self, monkeypatch):
        """Retry must not turn 'MT answered, it has nothing' into a failure."""
        (targets, status), attempts, _ = self._call(
            monkeypatch, [self._response(200, {"targets": []})]
        )

        assert targets == []
        assert status == "empty"
        assert attempts == 1
