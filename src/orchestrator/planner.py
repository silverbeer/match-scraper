"""Deterministic scrape planner — replaces LLM decision-making."""

from __future__ import annotations

import time
from datetime import date, timedelta
from enum import StrEnum
from typing import Any

import structlog
from pydantic import BaseModel

logger = structlog.get_logger()

# Kickoff-sync lookahead: check matches within this many days for missing kick-off times
_KICKOFF_LOOKAHEAD_DAYS = 14

# MT's match-summary endpoint intermittently 500s on a cold Supabase gateway
# timeout; a retry seconds later succeeds. See fetch_mt_status.
_MT_FETCH_ATTEMPTS = 4
_MT_FETCH_BACKOFF_SECONDS = 2.0


class ScrapeAction(StrEnum):
    FULL_SYNC = "full_sync"
    SCORE_SYNC = "score_sync"
    KICKOFF_SYNC = "kickoff_sync"
    SKIP = "skip"


class ScrapePlan(BaseModel):
    """Scrape plan for a single target."""

    target_key: str  # e.g. "u14-hg"
    target_label: str  # e.g. "U14 Homegrown Northeast"
    action: ScrapeAction
    start_date: date | None = None
    end_date: date | None = None
    reason: str = ""
    scraper_params: dict[str, str] = {}


class RunPlan(BaseModel):
    """Full scrape plan for all targets in a single run."""

    plans: list[ScrapePlan] = []
    mt_api_status: str = ""  # "ok", "failed:<reason>", "empty"


def _target_label(cfg: dict[str, str]) -> str:
    """Build a human-readable label from a scraper config dict."""
    ag = cfg.get("age_group", "?")
    league = cfg.get("league", "?")
    if cfg.get("conference"):
        return f"{ag} {league} {cfg['conference']}"
    return f"{ag} {league} {cfg.get('division', '?')}"


def _match_weekend_window(today: date) -> tuple[date, date]:
    """Return the window a SCORE_SYNC should scrape.

    Two modes, because the weekend and the week after it are asking different
    questions (SB-1064):

    Saturday, Sunday, Monday — the weekend in play, Friday through Monday.
    Four days. During the weekend the only thing worth scraping is the weekend
    being played; next weekend's fixtures cannot have scores yet. Monday belongs
    here because Sunday evening's scores post on Monday — under SB-1058 a Sunday
    17:00 ET kick-off is not even due until 20:00 ET.

    Tuesday to Friday — last Friday through next Monday. Eleven days. This is
    the reconciliation pass: whatever the weekend missed, plus the forward look
    that notices a fixture moved or added for the weekend coming. Cheap, because
    by midweek needs_score is normally 0 and every target SKIPs, so the width
    costs nothing until there is something to find.

    The split matters now that the weekend runs hourly (SB-1056). Twenty-five
    runs each scraping eleven days of date-picker range, to read scores from
    four of them, is most of a weekend's work spent on fixtures nobody has
    played.

    Examples (all dates 2026):
        Saturday  Sep 12 -> Sep 11 to Sep 14   (the weekend being played)
        Sunday    Sep 13 -> Sep 11 to Sep 14
        Monday    Sep 14 -> Sep 11 to Sep 14   (the weekend just gone)
        Wednesday Sep 16 -> Sep 11 to Sep 21   (reconcile, and look ahead)

    Returns:
        (start, end) — Friday to Monday of the weekend in play at the weekend,
        last Friday to next Monday midweek.
    """
    weekday = today.weekday()  # 0=Mon … 6=Sun

    if weekday in (5, 6, 0):  # Saturday, Sunday, Monday
        sat, sun = _last_weekend(today)
        return sat - timedelta(days=1), sun + timedelta(days=1)

    # Tuesday-Friday: reconcile the weekend gone and look at the one coming.
    days_until_fri = (4 - weekday) % 7
    this_friday = today + timedelta(days=days_until_fri)
    last_friday = this_friday - timedelta(days=7)
    this_monday = this_friday + timedelta(days=3)
    return last_friday, this_monday


def _mt_key(age_group: str, league: str, division: str) -> tuple[str, str, str]:
    """Normalize MT response fields into a lookup key."""
    return (age_group, league, division)


def _cfg_key(cfg: dict[str, str]) -> tuple[str, str, str]:
    """Normalize scraper config fields into a lookup key.

    For Academy targets, MT stores the conference in the division field.
    """
    if cfg.get("conference"):
        return (cfg["age_group"], cfg["league"], cfg["conference"])
    return (cfg["age_group"], cfg["league"], cfg.get("division", ""))


def _last_weekend(today: date) -> tuple[date, date]:
    """Return (saturday, sunday) of the most recent past weekend.

    On Sat/Sun returns the current weekend. On Mon-Fri returns last weekend.
    """
    weekday = today.weekday()  # 0=Mon … 6=Sun
    if weekday == 6:  # Sunday
        return today - timedelta(days=1), today
    if weekday == 5:  # Saturday
        return today, today + timedelta(days=1)
    # Mon-Fri: go back to last Saturday
    days_since_sat = weekday + 2
    sat = today - timedelta(days=days_since_sat)
    return sat, sat + timedelta(days=1)


def fetch_mt_status(
    api_url: str,
    api_key: str,
    season: str,
    today: date | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """Call MT match-summary API synchronously.

    Passes last weekend's date range as score_from/score_to so that
    needs_score only reflects matches from last weekend.

    Retries a server-side failure before giving up. The endpoint reads the whole
    season out of PostgREST, so the first caller after an idle gap can trip
    Supabase's gateway timeout and come back 500 while the call right behind it
    succeeds in under two seconds (SB-1055; MT-side fix is SB-1057). This agent
    runs hours apart and is always that first caller, and because the run halts
    fail-fast without a plan, one cold 504 used to cost the entire run.

    Returns:
        (targets_list, status_string) where status is "ok", "failed:<reason>", or "empty".
    """
    import httpx

    if today is None:
        today = date.today()

    sat, sun = _last_weekend(today)
    url = f"{api_url}/api/agent/match-summary"
    logger.info(
        "planner.fetch_mt_status", url=url, season=season, score_from=sat, score_to=sun
    )

    params = {
        "season": season,
        "score_from": sat.isoformat(),
        "score_to": sun.isoformat(),
    }
    headers = {"Authorization": f"Bearer {api_key}"}

    data: dict[str, Any] | None = None
    last_error = ""

    for attempt in range(1, _MT_FETCH_ATTEMPTS + 1):
        try:
            resp = httpx.get(url, params=params, headers=headers, timeout=15.0)
            resp.raise_for_status()
            data = resp.json()
            break
        except httpx.HTTPStatusError as exc:
            # A 4xx is a bad request or a bad token: the next attempt sends the
            # same thing and gets the same answer. Only 5xx is worth repeating.
            if exc.response.status_code < 500:
                logger.warning(
                    "planner.fetch_mt_status.failed",
                    error=str(exc),
                    status_code=exc.response.status_code,
                )
                return [], f"failed:{exc}"
            last_error = str(exc)
        except Exception as exc:
            last_error = str(exc)

        if attempt < _MT_FETCH_ATTEMPTS:
            delay = _MT_FETCH_BACKOFF_SECONDS * 2 ** (attempt - 1)
            logger.warning(
                "planner.fetch_mt_status.retrying",
                error=last_error,
                attempt=attempt,
                of=_MT_FETCH_ATTEMPTS,
                retry_in=delay,
            )
            time.sleep(delay)

    if data is None:
        logger.error(
            "planner.fetch_mt_status.failed",
            error=last_error,
            attempts=_MT_FETCH_ATTEMPTS,
        )
        return [], f"failed:{last_error}"

    targets = data.get("targets", [])
    if not targets:
        return [], "empty"

    logger.info("planner.fetch_mt_status.ok", target_count=len(targets))
    return targets, "ok"


def _clamp(start: date, end: date, season_start: date) -> tuple[date, date]:
    """
    Confine a planned window to dates MLS Next will serve.

    Mirrors ``tools.clamp_scrape_range``, applied here as well so that plans,
    logs and Telegram reports quote the dates actually scraped rather than the
    ones we would have liked.
    """
    clamped_start = max(start, season_start)
    return clamped_start, max(end, clamped_start)


def compute_scrape_plan(
    mt_targets: list[dict[str, Any]],
    target_configs: dict[str, dict[str, str]],
    today: date,
    season_end: date,
    season_start: date,
) -> RunPlan:
    """Compute a deterministic scrape plan for all non-IFA targets.

    Args:
        mt_targets: Target dicts from the MT API response.
        target_configs: The _TARGET_SCRAPER_CONFIG dict from main.py.
        today: Today's date.
        season_end: Season end date (SEASON_END constant).
        season_start: Earliest date MLS Next serves (SEASON_START constant).
            Windows are clamped to it — the score-sync window looks back to the
            Friday before last weekend, which in early August lands in the
            previous season and the site rejects outright. Required rather than
            defaulted, so this planner stays a pure function of its arguments
            instead of quietly depending on the wall clock.
    """
    # Build lookup: (age_group, league, division) → MT target data
    mt_lookup: dict[tuple[str, str, str], dict[str, Any]] = {}
    for t in mt_targets:
        key = _mt_key(t["age_group"], t["league"], t["division"])
        mt_lookup[key] = t

    # Only plan for division-level targets (skip IFA-specific ones)
    plan_targets = {k: v for k, v in target_configs.items() if not k.endswith("-ifa")}

    plans: list[ScrapePlan] = []
    for target_key, cfg in plan_targets.items():
        label = _target_label(cfg)
        lookup_key = _cfg_key(cfg)
        mt_data = mt_lookup.get(lookup_key)

        if mt_data is None or mt_data.get("total", 0) == 0:
            # Season-to-date, not today onwards. A target MT has nothing for is
            # either new to the config or new to MLS Next, and in both cases
            # the fixtures it is missing are the ones already played: the forty
            # Homegrown brackets added in SB-1024 had a month of results
            # waiting in the feed. Starting at `today` would have scraped the
            # rest of the season and quietly left the season so far behind.
            full_start, full_end = _clamp(season_start, season_end, season_start)
            plans.append(
                ScrapePlan(
                    target_key=target_key,
                    target_label=label,
                    action=ScrapeAction.FULL_SYNC,
                    start_date=full_start,
                    end_date=full_end,
                    reason="No matches in MT — needs initial sync",
                    scraper_params=cfg,
                )
            )
            continue

        needs_score = mt_data.get("needs_score", 0)
        needs_kickoff = mt_data.get("needs_kickoff", 0)

        if needs_score > 0:
            fri, mon = _clamp(*_match_weekend_window(today), season_start)

            reason_parts = [f"{needs_score} match(es) awaiting scores"]
            if needs_kickoff > 0:
                reason_parts.append(f"{needs_kickoff} missing kick-off time(s)")

            plans.append(
                ScrapePlan(
                    target_key=target_key,
                    target_label=label,
                    action=ScrapeAction.SCORE_SYNC,
                    start_date=fri,
                    end_date=mon,
                    reason=", ".join(reason_parts),
                    scraper_params=cfg,
                )
            )
            continue

        if needs_kickoff > 0:
            ko_start, ko_end = _clamp(
                today, today + timedelta(days=_KICKOFF_LOOKAHEAD_DAYS), season_start
            )
            plans.append(
                ScrapePlan(
                    target_key=target_key,
                    target_label=label,
                    action=ScrapeAction.KICKOFF_SYNC,
                    start_date=ko_start,
                    end_date=ko_end,
                    reason=f"{needs_kickoff} match(es) missing kick-off time",
                    scraper_params=cfg,
                )
            )
            continue

        # Fully up to date
        total = mt_data.get("total", 0)
        last_played = mt_data.get("last_played_date", "none")
        plans.append(
            ScrapePlan(
                target_key=target_key,
                target_label=label,
                action=ScrapeAction.SKIP,
                reason=f"Up to date ({total} matches, last played {last_played})",
                scraper_params=cfg,
            )
        )

    mt_status = (
        "ok" if mt_targets else ("empty" if mt_targets is not None else "failed")
    )
    return RunPlan(plans=plans, mt_api_status=mt_status)
