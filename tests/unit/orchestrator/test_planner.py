"""Tests for the deterministic scrape planner."""

from __future__ import annotations

from datetime import date, timedelta

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
    def test_on_friday(self):
        # Friday Mar 13 → last Fri Mar 6, this Mon Mar 16
        fri, mon = _match_weekend_window(date(2026, 3, 13))
        assert fri == date(2026, 3, 6)
        assert mon == date(2026, 3, 16)

    def test_on_saturday(self):
        # Saturday Mar 14 → last Fri Mar 13, this Mon Mar 23
        # (this Friday is Mar 20)
        fri, mon = _match_weekend_window(date(2026, 3, 14))
        assert fri == date(2026, 3, 13)
        assert mon == date(2026, 3, 23)

    def test_on_monday(self):
        # Monday Mar 16 → last Fri Mar 13, this Mon Mar 23
        fri, mon = _match_weekend_window(date(2026, 3, 16))
        assert fri == date(2026, 3, 13)
        assert mon == date(2026, 3, 23)

    def test_on_wednesday(self):
        # Wednesday Mar 18 → last Fri Mar 13, this Mon Mar 23
        fri, mon = _match_weekend_window(date(2026, 3, 18))
        assert fri == date(2026, 3, 13)
        assert mon == date(2026, 3, 23)

    def test_on_thursday(self):
        # Thursday Mar 19 → last Fri Mar 13, this Mon Mar 23
        fri, mon = _match_weekend_window(date(2026, 3, 19))
        assert fri == date(2026, 3, 13)
        assert mon == date(2026, 3, 23)


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


# ── Pro Player Pathway targets (SB-827) ──────────────────────────────


class TestPathwayTargets:
    def test_all_twelve_pathway_brackets_are_targets(self):
        from src.orchestrator.cli import _TARGET_SCRAPER_CONFIG

        ppp = {k: v for k, v in _TARGET_SCRAPER_CONFIG.items() if "-ppp-" in k}
        assert len(ppp) == 12, "4 brackets x U16/U17/U19"

    def test_pathway_targets_name_the_bracket_exactly_as_the_feed_does(self):
        # AssistIndex keys on the bracket name, and MT resolves the division by
        # name too (SB-830). A near-miss here yields zero matches with only a
        # warning, which is the silent gap SB-827 exists to close.
        from src.orchestrator.cli import _TARGET_SCRAPER_CONFIG

        assert _TARGET_SCRAPER_CONFIG["u16-ppp-northeast"] == {
            "age_group": "U16",
            "league": "Homegrown",
            "division": "Northeast (Pro Player Pathway)",
        }

    def test_pathway_is_the_homegrown_league_not_a_competition_of_its_own(self):
        # Pathway fixtures are League fixtures in a different bracket. Sending
        # any other league would break MT's league-scoped division lookup.
        from src.orchestrator.cli import _TARGET_SCRAPER_CONFIG

        for key, cfg in _TARGET_SCRAPER_CONFIG.items():
            if "-ppp-" in key:
                assert cfg["league"] == "Homegrown"

    def test_no_pathway_target_below_u16(self):
        # There is no Pathway bracket at U13/U14/U15 — 29 of 30 Pathway clubs
        # field no U15 side, that cohort plays up. Targeting them would be a
        # standing empty scrape.
        from src.orchestrator.cli import _TARGET_SCRAPER_CONFIG

        for key, cfg in _TARGET_SCRAPER_CONFIG.items():
            if "-ppp-" in key:
                assert cfg["age_group"] in ("U16", "U17", "U19")

    def test_pathway_targets_do_not_collide_with_geographic_ones(self):
        # u16-hg is Northeast geographic; u16-ppp-northeast is the Pathway
        # bracket. Different divisions, disjoint fixtures.
        from src.orchestrator.cli import _TARGET_SCRAPER_CONFIG as T

        assert T["u16-hg"]["division"] == "Northeast"
        assert T["u16-ppp-northeast"]["division"] == "Northeast (Pro Player Pathway)"


# ── MLS NEXT Flex targets (SB-836) ───────────────────────────────────


class TestFlexTargets:
    def test_all_flex_brackets_are_targets(self):
        from src.orchestrator.cli import _TARGET_SCRAPER_CONFIG

        flex = {k: v for k, v in _TARGET_SCRAPER_CONFIG.items() if "-flex-" in k}
        assert len(flex) == 52, "13 brackets x U15/U16/U17/U19"

    def test_flex_targets_use_the_flex_league(self):
        # Not "Homegrown". The league drives match_type, so posting these as
        # Homegrown would file every Flex goal as a League goal.
        from src.orchestrator.cli import _TARGET_SCRAPER_CONFIG

        for key, cfg in _TARGET_SCRAPER_CONFIG.items():
            if "-flex-" in key:
                assert cfg["league"] == "Flex"

    def test_no_flex_target_at_u13_or_u14(self):
        # Those age groups play no Flex at all — the feed has no bracket for
        # them, so targeting them would be a standing empty scrape.
        from src.orchestrator.cli import _TARGET_SCRAPER_CONFIG

        for key, cfg in _TARGET_SCRAPER_CONFIG.items():
            if "-flex-" in key:
                assert cfg["age_group"] in ("U15", "U16", "U17", "U19")

    def test_colliding_bracket_names_get_distinct_target_keys(self):
        # Florida, Frontier, Northwest and Southeast name both a Homegrown
        # division and a Flex bracket. The keys must not collide or one
        # competition silently overwrites the other in the target dict.
        from src.orchestrator.cli import _TARGET_SCRAPER_CONFIG as T

        assert T["u15-flex-florida"]["league"] == "Flex"
        assert T["u15-hg"]["league"] == "Homegrown"
        assert T["u15-flex-florida"]["division"] == "Florida"

    def test_bracket_names_with_parentheses_produce_readable_keys(self):
        from src.orchestrator.cli import _TARGET_SCRAPER_CONFIG as T

        assert T["u16-flex-mid-america-east"]["division"] == "Mid-America (East)"
        assert T["u16-flex-southwest-north"]["division"] == "Southwest (North)"

    def test_every_target_key_is_unique_to_one_config(self):
        # The dict cannot hold duplicates, so this asserts the generators do
        # not silently overwrite each other: 12 base + 12 Pathway + 52 Flex.
        from src.orchestrator.cli import _TARGET_SCRAPER_CONFIG as T

        assert len(T) == 76
