"""Run summary report builder for Telegram notifications."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from telegram_notify import escape

# K3s CronJob schedule hours (UTC) — weekdays 4x, weekends 8x
_CRON_HOURS_WEEKDAY = [2, 8, 14, 20]
_CRON_HOURS_WEEKEND = [2, 5, 8, 11, 14, 17, 20, 23]

# Display timezone for reports
_DISPLAY_TZ = ZoneInfo("America/New_York")

# Telegram rejects a sendMessage over this length outright with a 400, so an
# over-long report is not a long report — it is no report at all (SB-1015).
_TELEGRAM_MAX_CHARS = 4096


def build_report(
    *,
    result_summary: str,
    actions: list[dict[str, Any]],
    matches_found: int,
    matches_submitted: int,
    scraped_matches: list[dict[str, Any]],
    submission_errors: list[dict[str, str]],
    ingest_failures: list[dict[str, Any]] | None = None,
    protected_matches: list[dict[str, Any]] | None = None,
    env: str,
    target: str | None,
    dry_run: bool,
    mt_status: str = "",
    scrape_plan: Any = None,
    now: datetime | None = None,
) -> str:
    """Build a MarkdownV2-formatted run summary report.

    Args:
        result_summary: Agent's summary string.
        actions: List of AgentAction dicts (action, detail, dry_run).
        matches_found: Total matches found by scraper.
        matches_submitted: Total matches submitted to queue.
        scraped_matches: Raw match dicts from RunContext._scraped_matches.
        submission_errors: Error dicts from RunContext._submission_errors.
            These are RabbitMQ PUBLISH failures only — see ingest_failures.
        ingest_failures: Rows from missing-table's /api/admin/ingest-failures
            (SB-829). Publishing to the queue succeeds whether or not
            missing-table can resolve the names, so without these a run that
            landed nothing still reports as green.
        env: Environment name (local, prod).
        target: Target filter name or None.
        dry_run: Whether this was a dry run.
        now: Override current time (for testing). Defaults to UTC now.

    Returns:
        MarkdownV2-formatted report string ready for Telegram.
    """
    now = now or datetime.now(tz=UTC)
    lines: list[str] = []

    # --- Header ---
    lines.append("*Match Scraper Report*")
    local = now.astimezone(_DISPLAY_TZ)
    tz_abbr = local.strftime("%Z")  # EDT or EST
    ts = escape(local.strftime(f"%Y-%m-%d %-I:%M %p {tz_abbr}"))
    target_label = escape(target) if target else "all targets"
    header_parts = [ts]
    if target:
        header_parts.append(target_label)
    if dry_run:
        header_parts.append("DRY RUN")
    lines.append(f"_{' · '.join(header_parts)}_")
    lines.append("")

    # --- Agent Awareness ---
    awareness = _agent_awareness(now, scraped_matches)
    lines.append(awareness)

    # --- Scrape Plan ---
    if scrape_plan and hasattr(scrape_plan, "plans"):
        # Skipped targets are the count in the header line and nothing more.
        # There are 70-odd of them on a quiet run, each saying the same
        # "up to date" — listing them is most of what pushed the message past
        # Telegram's limit, and none of it is news.
        plan_parts = []
        for p in scrape_plan.plans:
            if p.action.value == "skip":
                continue
            icon = {
                "full_sync": "🔄",
                "score_sync": "🎯",
                "kickoff_sync": "⏰",
            }.get(p.action.value, "•")
            plan_parts.append(f"  {icon} {escape(p.target_label)}: {escape(p.reason)}")
        if mt_status.startswith("failed:"):
            lines.append(escape("⚠️ MT status FAILED — full-season fallback"))
        else:
            skipped = sum(1 for p in scrape_plan.plans if p.action.value == "skip")
            active = len(scrape_plan.plans) - skipped
            lines.append(escape(f"📡 Smart scrape: {active} active, {skipped} skipped"))
        for part in plan_parts:
            lines.append(part)
    elif mt_status.startswith("failed:"):
        lines.append(escape("⚠️ MT status FAILED — full-season fallback"))
    elif target:
        lines.append(escape("📡 Targeted run (no plan)"))
    lines.append("")

    # --- Actions Taken ---
    # One line per skipped target repeats the scrape plan it was computed from,
    # so they are collapsed to a count here for the same reason (SB-1015).
    skipped = 0
    for action in actions:
        if action.get("action") == "skip":
            skipped += 1
            continue
        prefix = escape("[DRY RUN] ") if action.get("dry_run") else ""
        icon = _action_icon(action.get("action", ""))
        # Use only the first line — full match list lives in the pod logs
        detail_str = action.get("detail", "")
        detail = escape(detail_str.split("\n")[0])
        lines.append(f"{icon} {prefix}{detail}")

    if skipped:
        lines.append(f"⏭️ {escape(f'{skipped} target(s) up to date')}")

    if not actions:
        lines.append(escape("No actions taken."))
    lines.append("")

    # --- Match Summary ---
    failures = ingest_failures or []
    dropped = sum(f.get("match_count", 0) for f in failures)

    completed = sum(1 for m in scraped_matches if m.get("match_status") == "completed")
    scheduled = sum(1 for m in scraped_matches if m.get("match_status") == "scheduled")
    tbd = sum(1 for m in scraped_matches if m.get("match_status") == "tbd")
    error_count = len(submission_errors)

    summary_parts = [
        escape(f"{matches_found} found"),
        escape(f"{matches_submitted} submitted"),
    ]
    if error_count:
        summary_parts.append(escape(f"{error_count} errors"))
    if dropped:
        # Sits next to "submitted" deliberately. Submitted-but-dropped is the
        # gap this whole section exists to close, and the two numbers only
        # mean anything side by side.
        summary_parts.append(escape(f"{dropped} rejected by MT"))
    lines.append(f"*Matches:* {' · '.join(summary_parts)}")

    no_kickoff = sum(
        1
        for m in scraped_matches
        if m.get("match_time") is None and m.get("match_status") in ("scheduled", "tbd")
    )

    status_parts = []
    if completed:
        status_parts.append(escape(f"{completed} completed"))
    if scheduled:
        status_parts.append(escape(f"{scheduled} scheduled"))
    if tbd:
        status_parts.append(escape(f"{tbd} tbd"))
    if no_kickoff:
        status_parts.append(escape(f"{no_kickoff} no time"))
    if status_parts:
        lines.append(f"  {' · '.join(status_parts)}")
    lines.append("")

    # --- Submission Errors ---
    if submission_errors:
        lines.append(f"*Submission Errors \\({escape(str(error_count))}\\):*")
        for err in submission_errors:
            match = escape(err.get("match", "unknown"))
            error = escape(err.get("error", "unknown"))
            lines.append(f"  • {match} — {error}")
        lines.append("")

    # --- Ingest Failures (missing-table side) ---
    if failures:
        lines.append(
            f"*Ingest Failures \\({escape(str(len(failures)))} names, {escape(str(dropped))} matches\\):*"
        )
        lines.append(escape("  Matches published but rejected by missing-table."))
        for f in failures:
            name = escape(str(f.get("raw_name", "unknown")))
            kind = escape(str(f.get("kind", "name")))
            count = escape(str(f.get("match_count", 0)))
            lines.append(f"  • {kind}: {name} ×{count}")
        # The fix is one command per line above, so say which one rather than
        # leaving the reader to remember it.
        lines.append(escape('  Fix a team name: mt team alias add <team> "<name>"'))
        lines.append("")

    # --- Live Score Protected ---
    protected = protected_matches or []
    if protected:
        n = len(protected)
        lines.append(f"*Live Score Protected \\({escape(str(n))}\\):*")
        lines.append(
            escape(
                "  ⚠️ mlssoccer.com not yet updated — withheld to protect MT live scores"
            )
        )
        lines.append(
            escape(
                "  Run 'audit' after mlssoccer.com posts scores to detect any discrepancies"
            )
        )
        for m in sorted(protected, key=lambda x: x.get("match_date", "")):
            md = escape(m.get("match_date", "?"))
            home = escape(m.get("home_team", "?"))
            away = escape(m.get("away_team", "?"))
            status = escape(m.get("match_status", "?"))
            lines.append(f"  • {md} {home} vs {away} \\[{status}\\]")
        lines.append("")

    # --- Weekend Scores ---
    scored_lines = _weekend_scores_section(now, scraped_matches)
    if scored_lines:
        lines.extend(scored_lines)
        lines.append("")

    # --- Missing Scores ---
    missing_lines = _missing_scores_section(now, scraped_matches)
    if missing_lines:
        lines.extend(missing_lines)
        lines.append("")

    # --- Missing Kick-off Times ---
    kickoff_lines = _missing_kickoff_section(scraped_matches)
    if kickoff_lines:
        lines.extend(kickoff_lines)
        lines.append("")

    # --- Next Run ---
    next_run, delta = _next_scheduled_run(now)
    next_local = next_run.astimezone(_DISPLAY_TZ)
    next_tz = next_local.strftime("%Z")
    next_str = escape(next_local.strftime(f"%-I:%M %p {next_tz}"))
    delta_str = _format_delta(delta)
    footer = f"*Next run:* {next_str} \\(in {escape(delta_str)}\\)"

    return "\n".join(_clamp_to_telegram_limit(lines, footer))


def _clamp_to_telegram_limit(body: list[str], footer: str) -> list[str]:
    """Drop trailing body lines until the message fits Telegram's limit.

    Whole lines, never a partial one: every bold marker and backslash escape
    in this report is balanced within its own line, and a cut inside one
    yields unparseable MarkdownV2 — which Telegram rejects with the same 400
    this function exists to avoid.

    The footer is kept whatever else goes. "When does it run next" is the one
    line a reader needs from a report that had to be trimmed.
    """
    if len("\n".join([*body, footer])) <= _TELEGRAM_MAX_CHARS:
        return [*body, footer]

    kept = list(body)
    dropped = 0
    while kept:
        kept.pop()
        dropped += 1
        marker = escape(f"… {dropped} line(s) dropped — full detail in the pod logs")
        if len("\n".join([*kept, marker, footer])) <= _TELEGRAM_MAX_CHARS:
            return [*kept, marker, footer]

    return [escape("… report too long to send — see the pod logs"), footer]


def _agent_awareness(now: datetime, matches: list[dict[str, Any]]) -> str:
    """Generate context-aware message based on day of week and match data."""
    day = now.weekday()  # 0=Mon, 5=Sat, 6=Sun

    if day in (5, 6):  # Sat/Sun
        return escape("🧠 Active match day — scores may still be posting")

    if day in (0, 1, 2):  # Mon/Tue/Wed
        # Check for unscored weekend matches
        weekend_unscored = [
            m
            for m in matches
            if _is_last_weekend(m.get("match_date", ""), now)
            and m.get("match_status") != "completed"
        ]
        if weekend_unscored:
            n = len(weekend_unscored)
            return escape(f"🧠 Mid-week — {n} weekend match(es) still awaiting scores")
        # Check if there were any weekend matches at all
        weekend_all = [
            m for m in matches if _is_last_weekend(m.get("match_date", ""), now)
        ]
        if weekend_all:
            return escape("🧠 Mid-week — all weekend scores are posted ✓")
        return escape("🧠 Mid-week — no recent weekend matches found")

    # Thu/Fri
    return escape("🧠 No recent match activity — routine schedule sync")


def _is_last_weekend(match_date: str, now: datetime) -> bool:
    """Check if a match date falls on the most recent Saturday or Sunday."""
    try:
        md = datetime.strptime(match_date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return False

    today = now.date()
    day = today.weekday()  # 0=Mon

    # Find last Saturday and Sunday
    days_since_sunday = (day + 1) % 7
    last_sunday = today - timedelta(days=days_since_sunday)
    last_saturday = last_sunday - timedelta(days=1)

    return md in (last_saturday, last_sunday)


def _weekend_scores_section(now: datetime, matches: list[dict[str, Any]]) -> list[str]:
    """Show completed weekend match scores (Mon-Wed only)."""
    day = now.weekday()
    if day not in (0, 1, 2):  # Only Mon/Tue/Wed
        return []

    scored = [
        m
        for m in matches
        if _is_last_weekend(m.get("match_date", ""), now)
        and m.get("match_status") == "completed"
    ]
    if not scored:
        return []

    lines: list[str] = []
    n = len(scored)
    lines.append(f"*Weekend Scores \\({escape(str(n))}\\):*")
    for m in sorted(scored, key=lambda x: x.get("match_date", "")):
        home = escape(m.get("home_team", "?"))
        away = escape(m.get("away_team", "?"))
        hs = m.get("home_score", "?")
        aws = m.get("away_score", "?")
        md = escape(m.get("match_date", "?"))
        lines.append(f"  • {md} {home} {hs}\\-{aws} {away}")
    return lines


def _missing_scores_section(now: datetime, matches: list[dict[str, Any]]) -> list[str]:
    """Build the missing scores section if there are unscored matches to highlight."""
    today_str = now.strftime("%Y-%m-%d")
    day = now.weekday()
    lines: list[str] = []

    # Today's unscored matches (Sat/Sun primarily, but show any day)
    today_unscored = [
        m
        for m in matches
        if m.get("match_date") == today_str and m.get("match_status") != "completed"
    ]
    if today_unscored:
        n = len(today_unscored)
        lines.append(f"*Today's Matches Awaiting Scores \\({escape(str(n))}\\):*")
        for m in today_unscored:
            home = escape(m.get("home_team", "?"))
            away = escape(m.get("away_team", "?"))
            status = escape(m.get("match_status", "?"))
            lines.append(f"  • {home} vs {away} — {status}")

    # Mon-Wed: also show unscored weekend matches
    if day in (0, 1, 2):
        weekend_unscored = [
            m
            for m in matches
            if _is_last_weekend(m.get("match_date", ""), now)
            and m.get("match_status") != "completed"
        ]
        if weekend_unscored:
            n = len(weekend_unscored)
            if lines:
                lines.append("")
            lines.append(f"*Weekend Matches Awaiting Scores \\({escape(str(n))}\\):*")
            for m in weekend_unscored:
                home = escape(m.get("home_team", "?"))
                away = escape(m.get("away_team", "?"))
                status = escape(m.get("match_status", "?"))
                md = escape(m.get("match_date", "?"))
                lines.append(f"  • {md} {home} vs {away} — {status}")

    return lines


def _missing_kickoff_section(matches: list[dict[str, Any]]) -> list[str]:
    """Build the missing kick-off times section."""
    missing = [
        m
        for m in matches
        if m.get("match_time") is None and m.get("match_status") in ("scheduled", "tbd")
    ]
    if not missing:
        return []

    lines: list[str] = []
    n = len(missing)
    lines.append(f"*Missing Kick\\-off Times \\({escape(str(n))}\\):*")
    for m in sorted(missing, key=lambda x: x.get("match_date", "")):
        md = escape(m.get("match_date", "?"))
        home = escape(m.get("home_team", "?"))
        away = escape(m.get("away_team", "?"))
        lines.append(f"  • {md} {home} vs {away}")
    return lines


def _next_scheduled_run(now: datetime) -> tuple[datetime, timedelta]:
    """Compute the next scheduled run time from the cron schedule."""
    is_weekend = now.weekday() in (5, 6)  # 5=Sat, 6=Sun
    hours = _CRON_HOURS_WEEKEND if is_weekend else _CRON_HOURS_WEEKDAY

    for hour in hours:
        candidate = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if candidate > now:
            return candidate, candidate - now

    # Wrap to first slot tomorrow
    tomorrow = now + timedelta(days=1)
    tomorrow_is_weekend = tomorrow.weekday() in (5, 6)
    tomorrow_hours = _CRON_HOURS_WEEKEND if tomorrow_is_weekend else _CRON_HOURS_WEEKDAY
    candidate = tomorrow.replace(
        hour=tomorrow_hours[0], minute=0, second=0, microsecond=0
    )
    return candidate, candidate - now


def _format_delta(delta: timedelta) -> str:
    """Format a timedelta as 'Xh Ym'."""
    total_minutes = int(delta.total_seconds() // 60)
    hours, minutes = divmod(total_minutes, 60)
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def _action_icon(action: str) -> str:
    """Map action type to an emoji icon."""
    return {"scrape": "✅", "submit": "✅", "skip": "⏭️"}.get(action, "•")


def build_release_report(
    *,
    season: str,
    newly_live: list[str],
    window_start: str,
    window_end: str,
    total_targets: int,
) -> str:
    """
    Build the MarkdownV2 message announcing a schedule release.

    Deliberately short and actionable: this fires once, possibly at 3am, and
    the only thing the reader needs is what dropped and what to do about it.
    """
    lines = [
        "🎉 *MLS Next schedule published*",
        "",
        f"Season: {escape(season)}",
        f"Window: {escape(window_start)} → {escape(window_end)}",
        "",
        f"*Live now* \\({len(newly_live)} of {total_targets} targets\\):",
    ]
    lines.extend(f"  • {escape(label)}" for label in newly_live)
    lines += [
        "",
        escape(
            "Next: verify a scrape before trusting it, then discover/enrich "
            "any division whose clubs are not yet in missing-table."
        ),
    ]
    return "\n".join(lines)


def build_release_failure_report(
    *,
    season: str,
    consecutive_failures: int,
    total_targets: int,
    sample_error: str,
) -> str:
    """
    Build the MarkdownV2 message for a sustained probe outage.

    Only sent once per streak. A single failed run is not news — the endpoint
    is someone else's server and blips are expected.
    """
    return "\n".join(
        [
            "⚠️ *Schedule watch failing*",
            "",
            f"Season: {escape(season)}",
            escape(
                f"All {total_targets} targets have failed {consecutive_failures} runs in a row."
            ),
            "",
            f"Latest error: {escape(sample_error)}",
            "",
            escape(
                "The watcher cannot tell whether the schedule has dropped while this persists."
            ),
        ]
    )
