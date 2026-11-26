"""Typer CLI for match-scraper-agent."""

from __future__ import annotations

import uuid
from datetime import UTC
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, NoReturn

import structlog
import typer

from src.orchestrator.targets import TEAM_FILTER_TARGETS as _TARGET_TEAM_FILTER
from src.orchestrator.targets import load_targets

if TYPE_CHECKING:
    from src.models.match_data import MatchData
    from src.models.tournament import TournamentContext, TournamentMatch
    from src.orchestrator.release_watch import ReleaseWatchState
    from src.orchestrator.settings import AgentSettings
    from src.scraper.tournament.base import TournamentSource

app = typer.Typer(name="match-scraper-agent", no_args_is_help=True)
logger = structlog.get_logger()


# What to scrape is read from the standings feeds, not typed out here — see
# src/orchestrator/targets.py. The hand-written list this replaces covered
# Northeast plus Florida at U13/U14, which left forty of the league's
# forty-eight brackets unscraped and silent about it (SB-1024).


def _target_config(settings: AgentSettings) -> dict[str, dict[str, str]]:
    """The targets the feeds declare, for this run.

    Academy is opt-in: ``AGENT_ACADEMY_TARGETS`` takes every conference,
    ``AGENT_ACADEMY_CONFERENCES`` only the ones named. Most Academy clubs
    share their bare name with the club's Homegrown team in missing-table, so
    a conference is only safe to scrape once its clubs have Academy-scoped
    aliases (SB-1652); until then its fixtures land on Homegrown rows.
    """
    import asyncio

    conferences = settings.academy_conference_set()
    leagues = ["Homegrown", "Flex"]
    if settings.academy_targets or conferences:
        leagues.append("Academy")
    targets = asyncio.run(load_targets(leagues=leagues))
    if settings.academy_targets or not conferences:
        return targets
    return {
        key: cfg
        for key, cfg in targets.items()
        if cfg.get("league") != "Academy" or cfg.get("conference") in conferences
    }


def _queue_client_kwargs(settings: AgentSettings) -> dict[str, str]:
    """Build kwargs for MatchQueueClient based on settings."""
    kwargs: dict[str, str] = {"broker_url": settings.rabbitmq_url}
    if settings.queue_name:
        kwargs["queue_name"] = settings.queue_name
    else:
        kwargs["exchange_name"] = settings.exchange_name
    return kwargs


def _send_email_alert(settings: AgentSettings, subject: str, body: str) -> bool:
    """Send a plain-text email via Resend. No-op if not configured.

    Returns whether the email was handed to Resend.
    """
    if not settings.resend_api_key:
        logger.debug("email_alert.skipped", reason="resend_api_key not configured")
        return False

    import resend

    resend.api_key = settings.resend_api_key
    try:
        resend.Emails.send(
            {
                "from": settings.alert_email_from,
                "to": settings.alert_email_to,
                "subject": subject,
                "text": body,
            }
        )
        logger.info("email_alert.sent", to=settings.alert_email_to)
        return True
    except Exception as exc:
        logger.error("email_alert.failed", error=str(exc))
        return False


def _send_telegram_failure(
    settings: AgentSettings,
    *,
    env: str,
    run_id: str,
    reason: str,
    detail: str = "",
    target: str | None = None,
    phase: str = "",
) -> None:
    """Tell Telegram the run died.

    Every failure path used to exit without sending anything, because
    _send_telegram_report sits after the try/except and both handlers skip it.
    A successful run always reported, so silence meant either "quiet weekend"
    or "dead" — indistinguishable, and on a day when every target correctly
    SKIPs the healthy signal is near-silence too. Four consecutive runs died
    unnoticed on 2026-09-11/12 (SB-1062).

    Never raises: a failure inside the failure notifier must not replace the
    exit code the caller is on its way to returning.
    """
    from src.orchestrator.report import build_failure_report

    try:
        message = build_failure_report(
            env=env,
            run_id=run_id,
            reason=reason,
            detail=detail,
            target=target,
            phase=phase,
        )
        _send_telegram_message(
            settings, message, subject="[match-scraper-agent] Run failed"
        )
    except Exception as exc:  # pragma: no cover — belt and braces
        logger.warning("telegram.failure_report_failed", error=str(exc))


def _send_telegram_report(
    settings: AgentSettings,
    result: Any,
    ctx: Any,
    env: str,
    target: str | None,
) -> None:
    """Send the run report to Telegram — only when it needs a person (SB-1679)."""
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.debug("telegram.skipped", reason="not configured")
        return

    from datetime import date

    from telegram_notify import TelegramClient

    from src.orchestrator.alert_state import mark_alerted, unalerted
    from src.orchestrator.ingest_failures import fetch_ingest_failures
    from src.orchestrator.report import build_report, needs_attention

    # Asked after the work is done: publishing to the queue says nothing about
    # whether missing-table could resolve the names, and that gap is how a run
    # that landed nothing still reported as green (SB-831).
    all_failures = fetch_ingest_failures(
        api_url=ctx.missing_table_api_url,
        api_key=ctx.missing_table_api_key,
        since=ctx._started_at,
    )
    # A name stays rejected on every run until someone adds an alias; say so
    # once a day, not every run.
    today = date.today()
    ingest_failures = unalerted(all_failures, settings.alert_state_path, today)

    if not needs_attention(
        submission_errors=ctx._submission_errors,
        ingest_failures=ingest_failures,
        protected_matches=ctx._protected_matches,
        mt_status=ctx._mt_status,
    ):
        logger.info(
            "telegram.quiet",
            reason="nothing needs attention",
            repeat_failures=len(all_failures),
        )
        return

    report = build_report(
        result_summary=result.summary,
        actions=[a.model_dump() for a in result.actions],
        matches_found=result.matches_found,
        matches_submitted=result.matches_submitted,
        scraped_matches=ctx._scraped_matches,
        submission_errors=ctx._submission_errors,
        ingest_failures=ingest_failures,
        protected_matches=ctx._protected_matches,
        env=env,
        target=target,
        dry_run=ctx.dry_run,
        mt_status=ctx._mt_status,
        scrape_plan=ctx._scrape_plan,
    )

    try:
        client = TelegramClient(
            bot_token=settings.telegram_bot_token,
            chat_id=settings.telegram_chat_id,
        )
        client.send(report)
        logger.info("telegram.sent", chat_id=settings.telegram_chat_id)
        if not ctx.dry_run:
            mark_alerted(ingest_failures, settings.alert_state_path, today)
    except Exception as exc:
        logger.warning("telegram.failed", error=str(exc))
        _send_email_alert(
            settings,
            subject="[match-scraper-agent] Telegram failed — run report",
            body=f"Telegram notification failed: {exc}\n\n{report}",
        )


@app.command()
def run(
    env: Annotated[
        str, typer.Option("--env", help="Environment name (local, prod)")
    ] = "local",
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Skip mutating operations")
    ] = False,
    json_logs: Annotated[
        bool, typer.Option("--json-logs", help="Output JSON log lines")
    ] = False,
    target: Annotated[
        str | None,
        typer.Option(
            "--target", help="Scrape only this target (u14-hg, u13-hg, u14-academy)"
        ),
    ] = None,
) -> None:
    """Run the match-scraper pipeline engine."""
    import asyncio

    from src.celery.queue_client import MatchQueueClient
    from src.orchestrator.deps import RunContext
    from src.orchestrator.logger import configure_logging
    from src.orchestrator.settings import AgentSettings, env_file_path

    settings = AgentSettings(_env_file=env_file_path(env))
    if dry_run:
        settings.dry_run = True

    configure_logging(
        json_output=json_logs or settings.json_logs, log_level=settings.log_level
    )

    run_id = uuid.uuid4().hex[:12]
    structlog.contextvars.bind_contextvars(run_id=run_id, env=env)

    logger.info(
        "engine.starting",
        dry_run=settings.dry_run,
    )

    try:
        queue_client = MatchQueueClient(**_queue_client_kwargs(settings))

        target_configs = _target_config(settings)
        if not target_configs:
            # The feeds declared nothing to scrape. That is never a quiet day:
            # it means every standings feed failed to parse. Fail the run so
            # the journal is not refreshed and the watchdog goes stale too —
            # days of "0 targets scraped" went out as healthy runs while
            # the platform's v2 format went unread (SB-1492).
            logger.error(
                "engine.no_targets",
                reason="No standings feed declared any bracket — halting run",
            )
            _send_telegram_failure(
                settings,
                env=env,
                run_id=run_id,
                target=target,
                phase="targets",
                reason="the standings feeds declared no targets, so nothing can be scraped",
                detail="see targets.index_failed in the run log",
            )
            raise typer.Exit(code=1)
        if target and target not in target_configs:
            valid = ", ".join(sorted(target_configs))
            typer.echo(f"Unknown target '{target}'. Valid targets: {valid}", err=True)
            raise typer.Exit(code=1)

        team_filter = _TARGET_TEAM_FILTER.get(target or "", "")
        ctx = RunContext(
            queue_client=queue_client,
            missing_table_api_url=settings.missing_table_api_url,
            missing_table_api_key=settings.missing_table_api_key or "",
            dry_run=settings.dry_run,
            headless=settings.headless,
            team_filter=team_filter,
            age_group=settings.age_group,
            league=settings.league,
            division=settings.division,
        )

        if target:
            # Targeted run — build a single-entry RunPlan
            from datetime import date

            from src.orchestrator.planner import RunPlan, ScrapeAction, ScrapePlan
            from src.orchestrator.tools import current_segment_window

            target_cfg = target_configs[target]
            label = _target_label(target_cfg)
            plan = RunPlan(
                plans=[
                    ScrapePlan(
                        target_key=target,
                        target_label=label,
                        action=ScrapeAction.FULL_SYNC,
                        start_date=date.today(),
                        end_date=current_segment_window()[1],
                        reason="Targeted run",
                        scraper_params=target_cfg,
                    )
                ],
            )
            ctx._scrape_plan = plan
            logger.info(
                "engine.target_run", target=target, team_filter=team_filter or None
            )
            journal = None
        else:
            # Full run — compute scrape plan from MT data
            from datetime import UTC, datetime

            from src.orchestrator.planner import compute_scrape_plan, fetch_mt_status
            from src.orchestrator.tools import (
                SEASON_START,
                _current_season,
                current_segment_window,
            )

            now_utc = datetime.now(tz=UTC)
            mt_targets, mt_status_str = fetch_mt_status(
                api_url=settings.missing_table_api_url,
                api_key=settings.missing_table_api_key or "",
                season=_current_season(),
            )
            ctx._mt_status = mt_status_str

            if mt_status_str.startswith("failed:"):
                logger.error(
                    "engine.mt_api_failed",
                    mt_status=mt_status_str,
                    reason="Cannot plan without MT data — halting run",
                )
                _send_telegram_failure(
                    settings,
                    env=env,
                    run_id=run_id,
                    target=target,
                    phase="planning",
                    reason="missing-table did not answer, so no plan could be built",
                    detail=mt_status_str.removeprefix("failed:"),
                )
                raise typer.Exit(code=1)

            # Scrape the current segment, not the whole remaining season: a
            # range ending in the season's final month cannot be expressed in
            # the MLS Next date picker and fails every full_sync (SB-551).
            _, segment_end = current_segment_window(now_utc.date())

            plan = compute_scrape_plan(
                mt_targets=mt_targets,
                target_configs=target_configs,
                today=now_utc.date(),
                season_end=segment_end,
                season_start=SEASON_START,
            )
            ctx._scrape_plan = plan

            logger.info(
                "planner.computed",
                mt_status=mt_status_str,
                full_sync=sum(1 for p in plan.plans if p.action.value == "full_sync"),
                score_sync=sum(1 for p in plan.plans if p.action.value == "score_sync"),
                reconcile=sum(1 for p in plan.plans if p.action.value == "reconcile"),
                skip=sum(1 for p in plan.plans if p.action.value == "skip"),
            )

            # Read previous journal for modifier rules. S3 when a bucket is
            # configured, otherwise a file on the mounted PVC — with neither,
            # the modifier rules are dead and a failed target never retries.
            journal = None
            if settings.journal_s3_bucket or settings.journal_path:
                from src.orchestrator.journal import read_journal

                journal = read_journal(
                    settings.journal_s3_bucket,
                    settings.journal_s3_key,
                    settings.journal_path,
                )
                if journal:
                    logger.info("journal.loaded", run_id=journal.run_id)

        # Run the pipeline engine
        from src.orchestrator.engine import run_pipeline

        result = asyncio.run(run_pipeline(plan, ctx, journal))

    except typer.Exit:
        # Already reported at the point it was decided — the halt paths know
        # which phase they are in and say so, which a handler here could not.
        raise
    except Exception as exc:
        logger.error("engine.failed", error=str(exc), exc_info=exc)
        _send_telegram_failure(
            settings,
            env=env,
            run_id=run_id,
            target=target,
            phase="pipeline",
            reason=f"The run raised {type(exc).__name__}",
            detail=str(exc),
        )
        raise typer.Exit(code=1) from None

    logger.info(
        "engine.completed",
        summary=result.summary,
        actions=len(result.actions),
        matches_found=result.matches_found,
        matches_submitted=result.matches_submitted,
    )

    if json_logs or settings.json_logs:
        print(result.model_dump_json(indent=2))
    else:
        typer.echo(f"\n{result.summary}")
        for action in result.actions:
            prefix = "[DRY RUN] " if action.dry_run else ""
            typer.echo(f"  {prefix}{action.action}: {action.detail}")

    # Write run journal for next run's context. A dry run does not write: its
    # journal would claim work it never did, and the next real run would skip
    # targets on the strength of it.
    if (settings.journal_s3_bucket or settings.journal_path) and not settings.dry_run:
        from src.orchestrator.journal import build_journal, write_journal

        journal_out = build_journal(
            run_id=run_id,
            result=result,
            scraped_matches=ctx._scraped_matches,
            submission_errors=ctx._submission_errors,
            target=target,
            dry_run=settings.dry_run,
        )
        write_journal(
            settings.journal_s3_bucket,
            settings.journal_s3_key,
            journal_out,
            settings.journal_path,
        )

    # Send Telegram summary report
    _send_telegram_report(
        settings=settings,
        result=result,
        ctx=ctx,
        env=env,
        target=target,
    )

    structlog.contextvars.unbind_contextvars("run_id", "env")


def _target_label(cfg: dict[str, str]) -> str:
    """Build a human-readable label from a scraper config dict."""
    ag = cfg.get("age_group", "?")
    league = cfg.get("league", "?")
    if cfg.get("conference"):
        return f"{ag} {league} {cfg['conference']}"
    return f"{ag} {league} {cfg.get('division', '?')}"


@app.command()
def check(
    env: Annotated[
        str, typer.Option("--env", help="Environment name (local, prod)")
    ] = "local",
) -> None:
    """Check RabbitMQ connectivity."""
    from src.orchestrator.logger import configure_logging
    from src.orchestrator.settings import AgentSettings, env_file_path

    configure_logging(json_output=False)

    settings = AgentSettings(_env_file=env_file_path(env))

    typer.echo(f"environment: {env}")

    # Check RabbitMQ
    typer.echo(f"rabbitmq: checking {settings.rabbitmq_url}")
    try:
        from src.celery.queue_client import MatchQueueClient

        client = MatchQueueClient(**_queue_client_kwargs(settings))
        if client.check_connection():
            typer.echo("  status: connected")
        else:
            typer.echo("  status: UNREACHABLE")
    except Exception as exc:
        typer.echo(f"  status: ERROR ({exc})")


@app.command()
def scrape(
    target: Annotated[
        str,
        typer.Option(
            "--target", help="Scrape target (u14-hg, u14-hg-ifa, u13-hg, etc.)"
        ),
    ],
    env: Annotated[
        str, typer.Option("--env", help="Environment name (local, prod)")
    ] = "local",
    json_output: Annotated[
        bool, typer.Option("--json", help="Output raw match dicts as JSON")
    ] = False,
    from_date: Annotated[
        str | None,
        typer.Option("--from", help="Start date (YYYY-MM-DD). Defaults to today."),
    ] = None,
    to_date: Annotated[
        str | None,
        typer.Option(
            "--to", help="End date (YYYY-MM-DD). Defaults to season end (2026-06-30)."
        ),
    ] = None,
    submit: Annotated[
        bool,
        typer.Option("--submit", help="Submit scraped matches to RabbitMQ queue"),
    ] = False,
    club: Annotated[
        str | None,
        typer.Option("--club", help="Filter to a specific club name"),
    ] = None,
) -> None:
    """Scrape matches directly — no pipeline, just browser automation."""
    import asyncio
    from datetime import date

    from src.orchestrator.logger import configure_logging
    from src.orchestrator.settings import AgentSettings, env_file_path
    from src.orchestrator.tools import (
        build_match_dict,
        clamp_scrape_range,
        current_segment_window,
    )
    from src.scraper.config import ScrapingConfig
    from src.scraper.mls_scraper import MLSScraper

    configure_logging(json_output=False)

    settings = AgentSettings(_env_file=env_file_path(env))

    target_configs = _target_config(settings)
    if target not in target_configs:
        valid = ", ".join(sorted(target_configs))
        typer.echo(f"Unknown target '{target}'. Valid targets: {valid}", err=True)
        raise typer.Exit(code=1)

    target_cfg = target_configs[target]
    team_filter = _TARGET_TEAM_FILTER.get(target, "")

    try:
        start = date.fromisoformat(from_date) if from_date else date.today()
        end = date.fromisoformat(to_date) if to_date else current_segment_window()[1]
    except ValueError as exc:
        typer.echo(f"Invalid date format: {exc}. Use YYYY-MM-DD.", err=True)
        raise typer.Exit(code=1) from None

    # This path builds ScrapingConfig directly rather than going through
    # tools.scrape_matches, so it needs its own clamp.
    requested = (start, end)
    start, end = clamp_scrape_range(start, end)
    if (start, end) != requested:
        typer.echo(
            f"Adjusted date range {requested[0]}..{requested[1]} -> {start}..{end} "
            "(MLS Next only serves the current season, and not its final month)."
        )

    config = ScrapingConfig(
        age_group=target_cfg.get("age_group", settings.age_group),
        league=target_cfg.get("league", settings.league),
        division=target_cfg.get("division", settings.division),
        conference=target_cfg.get("conference", ""),
        club=club or "",
        start_date=start,
        end_date=end,
        look_back_days=(end - start).days,
        missing_table_api_url=settings.missing_table_api_url,
        missing_table_api_key=settings.missing_table_api_key or "unused",
    )

    label = f"{config.age_group} {config.league}"
    if config.conference:
        label += f" {config.conference}"
    elif config.division:
        label += f" {config.division}"
    typer.echo(f"Scraping {label} ({start} to {end})...")

    scraper = MLSScraper(config, headless=True)
    matches = asyncio.run(scraper.scrape_matches())

    if not matches:
        typer.echo("No matches found.")
        raise typer.Exit(code=0)

    # The engine's own builder, so this path cannot drift from it. It used to
    # carry a copy with match_type hardcoded to "League", which filed every
    # Flex fixture sent from here as League (SB-1786).
    # From the resolved config, settings fallbacks included, so what is sent
    # is what was scraped.
    resolved = {
        "age_group": config.age_group,
        "league": config.league,
        "division": config.division,
        "conference": config.conference,
    }
    built = [build_match_dict(m, resolved) for m in matches]

    # Apply team filter
    if team_filter:
        built = [m for m in built if team_filter in (m["home_team"], m["away_team"])]

    if json_output:
        import json

        print(json.dumps(built, indent=2))
    else:
        typer.echo(f"\nFound {len(matches)} matches ({len(built)} after filtering):\n")
        for m in built:
            has_score = m["home_score"] is not None
            score = f" ({m['home_score']}-{m['away_score']})" if has_score else ""
            typer.echo(
                f"  {m['match_date']} | {m['home_team']} vs {m['away_team']}"
                f"{score} [{m['match_status']}]"
            )

    if submit:
        from src.celery.queue_client import MatchQueueClient

        queue_client = MatchQueueClient(**_queue_client_kwargs(settings))
        submitted = 0
        errors = 0
        for match_dict in built:
            try:
                queue_client.submit_match(match_dict)
                submitted += 1
            except Exception as exc:
                errors += 1
                logger.warning(
                    "scrape.submit_error",
                    match=f"{match_dict['home_team']} vs {match_dict['away_team']}",
                    error=str(exc),
                )
        typer.echo(f"\nSubmitted {submitted} matches to queue ({errors} errors).")


@app.command()
def backfill(
    leagues: Annotated[
        list[str] | None,
        typer.Option(
            "--league", help="Homegrown or Flex; repeat for both. Default: both."
        ),
    ] = None,
    from_date: Annotated[
        str | None,
        typer.Option("--from", help="Start date (YYYY-MM-DD). Default: season start."),
    ] = None,
    to_date: Annotated[
        str | None,
        typer.Option("--to", help="End date (YYYY-MM-DD). Default: two days ago."),
    ] = None,
    env: Annotated[
        str, typer.Option("--env", help="Environment name (local, prod)")
    ] = "local",
    submit: Annotated[
        bool,
        typer.Option(
            "--submit", help="Publish to the queue. Without it this is a dry run."
        ),
    ] = False,
    max_changes: Annotated[
        int,
        typer.Option(
            "--max-changes",
            min=0,
            help="Refuse to publish anything when more results than this are missing.",
        ),
    ] = 200,
    confirm_wait: Annotated[
        float,
        typer.Option(
            "--confirm-wait",
            min=0,
            help="With --submit, seconds to wait for MT to show what was sent.",
        ),
    ] = 600.0,
) -> None:
    """Send completed official results that missing-table never received (SB-1786).

    Reads the official feed and every MT match of the season, and lists each
    completed League or Flex result whose match id is not in MT. With --submit
    those are published through the normal ingest path, MT is re-read to
    confirm they landed, and Telegram hears about it; one missing on two runs
    in a row gets the louder alert. Nothing is ever deleted: an MT result the
    feed does not know is listed, not removed.

    Without --submit nothing is published and nothing is alerted.

    Exit codes: 0 nothing missing; 10 ran, with findings; 1 could not run —
    a feed or MT could not be read, the broker is unreachable, the publish
    target does not match the MT that was read, or more than --max-changes
    results are missing.
    """
    import asyncio
    import time
    from datetime import date, datetime, timedelta
    from zoneinfo import ZoneInfo

    from telegram_notify import escape

    from src.orchestrator.alert_state import repeat_gaps, write_gap_state
    from src.orchestrator.completeness import (
        LEAGUES,
        api_host,
        counts,
        diff,
        fetch_mt_rows,
        in_window,
        mt_pages,
        publish_mismatch,
        read_feed,
        triage,
    )
    from src.orchestrator.logger import configure_logging
    from src.orchestrator.report import build_completeness_report
    from src.orchestrator.settings import AgentSettings, env_file_path
    from src.orchestrator.tools import SEASON_START, build_match_dict
    from src.scraper.assist_client import AssistClient

    settings = AgentSettings(_env_file=env_file_path(env))
    configure_logging(json_output=settings.json_logs)

    chosen = list(dict.fromkeys(leagues or LEAGUES))
    unknown = [league for league in chosen if league not in LEAGUES]
    if unknown:
        typer.echo(
            f"Unknown league(s) {', '.join(unknown)}. Valid: {', '.join(LEAGUES)}",
            err=True,
        )
        raise typer.Exit(code=1)

    # The day MT and the digest mean, not the pod's: the pod runs in UTC, and
    # at 22:40 ET that is already tomorrow for half the year.
    today = datetime.now(ZoneInfo("America/New_York")).date()
    try:
        start = date.fromisoformat(from_date) if from_date else SEASON_START
        end = date.fromisoformat(to_date) if to_date else today - timedelta(days=2)
    except ValueError as exc:
        typer.echo(f"Invalid date: {exc}. Use YYYY-MM-DD.", err=True)
        raise typer.Exit(code=1) from None
    if start > end:
        typer.echo(f"--from {start} is later than --to {end}.", err=True)
        raise typer.Exit(code=1)
    # Only a run over everything may speak for everything: a narrowed run
    # writing state would tell the digest, and the next nightly run, that the
    # leagues and weeks it never looked at are complete.
    # Naming every league is the same scope as naming none; the CronJob
    # spells them out (SB-1786).
    full_scope = set(chosen) == set(LEAGUES) and from_date is None and to_date is None
    state_path = settings.completeness_state_path

    # Where this reads and where it would write, before anything happens.
    mode = "SUBMIT" if submit else "DRY RUN, nothing is published"
    typer.echo(f"Backfill {', '.join(chosen)}, {start} to {end} — {mode}")
    typer.echo(f"MT API: {api_host(settings.missing_table_api_url)}")
    typer.echo(f"Publish target: {_broker_target(settings)}")

    def fail(reason: str) -> NoReturn:
        typer.echo(reason, err=True)
        if submit:
            _send_telegram_message(
                settings,
                escape(f"⚠️ Completeness backfill could not run: {reason}"),
                subject="[match-scraper-agent] Completeness backfill failed",
            )
        raise typer.Exit(code=1)

    queue_client = None
    if submit:
        mismatch = publish_mismatch(
            settings.missing_table_api_url, settings.queue_name, settings.exchange_name
        )
        if mismatch:
            # Not alerted: a misconfigured manual run is the operator's to fix,
            # and the operator is reading this.
            typer.echo(f"Refusing to publish: {mismatch}. Nothing fetched.", err=True)
            raise typer.Exit(code=1)
        from src.celery.queue_client import MatchQueueClient

        queue_client = MatchQueueClient(**_queue_client_kwargs(settings))
        if not queue_client.check_connection():
            fail("broker unreachable: nothing fetched or published")

    async def _feed():
        async with AssistClient() as client:
            return await read_feed(client, chosen)

    try:
        feed = asyncio.run(_feed())
    except Exception as exc:
        fail(f"could not read the official feed: {exc}")

    # MT from season start, whatever the window: a row whose date has moved
    # out of the window still exists, and missing it would read as a gap.
    pages = mt_pages(SEASON_START, today, feed.placeholders)

    def read_mt():
        return fetch_mt_rows(
            settings.missing_table_api_url,
            settings.missing_table_api_key,
            pages,
            expect_days=feed.result_days(),
        )

    try:
        rows = read_mt()
    except Exception as exc:
        fail(f"could not read missing-table, nothing sent: {exc}")

    gaps = diff(feed.events, rows, feed.game_keys)
    creates = [
        g for g in gaps if g.action == "create" and in_window(g.event, start, end)
    ]
    reports = [
        g
        for g in gaps
        if g.action == "report" and g.match_date and start <= g.match_date <= end
    ]
    plan = triage(creates)

    typer.echo(
        f"\nFeed fixtures: {len(feed.events)}, MT rows read: {len(rows)} "
        f"({len(pages)} pages)"
    )
    typer.echo(f"Official results not in MT: {len(creates)}")
    for (league, division, age), n in counts(creates).items():
        typer.echo(f"  {n:>5}  {league} {division} {age}")
    for gap in plan.send:
        typer.echo(f"  {gap.line()}")
    if plan.no_bracket:
        typer.echo(f"Not sendable: no bracket: {len(plan.no_bracket)}")
        for gap in plan.no_bracket:
            typer.echo(f"  {gap.line()}  not sendable: no bracket")
    if plan.placeholder:
        typer.echo(
            f"Needs a person: result on placeholder date: {len(plan.placeholder)}"
        )
        for gap in plan.placeholder:
            typer.echo(f"  {gap.line()}  needs a person: result on placeholder date")
    if reports:
        typer.echo(f"MT results the feed does not have (never deleted): {len(reports)}")
        for gap in reports:
            typer.echo(f"  {gap.line()}")

    found = [g.game_key for g in creates]
    unsent = [g.game_key for g in plan.no_bracket + plan.placeholder]

    def record(submitted_keys: list[str], still_missing: list[str]) -> None:
        if submit and full_scope:
            write_gap_state(state_path, today, found, submitted_keys, still_missing)

    def alert(**fields: Any) -> None:
        _send_telegram_message(
            settings,
            build_completeness_report(
                env=env,
                found=counts(creates),
                game_keys=[g.game_key for g in plan.send],
                no_bracket=[g.game_key for g in plan.no_bracket],
                placeholder=[g.game_key for g in plan.placeholder],
                **fields,
            ),
            subject="[match-scraper-agent] Official results not in MT",
        )

    if not creates:
        record([], [])
        typer.echo("\nNothing missing.")
        raise typer.Exit(code=10 if reports else 0)

    if len(plan.send) > max_changes:
        refused = (
            f"{len(plan.send)} results to send, more than --max-changes "
            f"{max_changes}; nothing published"
        )
        if not submit:
            typer.echo(f"\nDry run: --submit would refuse: {refused}.")
            raise typer.Exit(code=10)
        typer.echo(f"\nRefusing: {refused}.", err=True)
        record([], found)
        alert(
            repeats=[],
            still_missing=[],
            submitted=0,
            send_failed=[],
            refused=refused,
        )
        raise typer.Exit(code=1)

    if queue_client is None:
        typer.echo(f"\nDry run: {len(plan.send)} would be sent with --submit.")
        raise typer.Exit(code=10)

    sent: list[str] = []
    send_failed: list[str] = []
    for gap in plan.send:
        event = gap.event
        if event is None:  # triage only sends gaps with an event
            continue
        try:
            queue_client.submit_match(build_match_dict(event.match, event.target()))
            sent.append(gap.game_key)
        except Exception as exc:
            send_failed.append(gap.game_key)
            typer.echo(f"  {gap.game_key}  send failed: {exc}", err=True)
    typer.echo(f"\nSubmitted {len(sent)} matches to queue ({len(send_failed)} failed).")

    # The workers are asynchronous: give MT time to show what was sent. Only
    # what was sent is waited for, and a failed re-read is retried, never read
    # as "everything is missing".
    deadline = time.monotonic() + confirm_wait
    confirmed = False
    unlanded = list(sent)
    while sent:
        try:
            present = {row.match_id for row in read_mt()}
            confirmed = True
            unlanded = [key for key in sent if key not in present]
        except Exception as exc:
            typer.echo(f"warning: could not re-read missing-table: {exc}", err=True)
        if (confirmed and not unlanded) or time.monotonic() >= deadline:
            break
        time.sleep(min(30.0, max(0.0, deadline - time.monotonic())))
    if not sent:
        confirmed = True
    if confirmed:
        typer.echo(f"Sent but still not in MT: {len(unlanded)}")
    else:
        typer.echo("Could not re-read missing-table to confirm what was sent.")

    repeats = repeat_gaps([g.game_key for g in plan.send], state_path)
    record(sent, unlanded + send_failed + unsent)
    alert(
        repeats=repeats,
        still_missing=unlanded if confirmed else [],
        submitted=len(sent),
        send_failed=send_failed,
        confirmed=confirmed,
    )

    if send_failed and not sent:
        raise typer.Exit(code=1)
    raise typer.Exit(code=10)


@app.command()
def reconcile(
    leagues: Annotated[
        list[str] | None,
        typer.Option(
            "--league",
            help="Homegrown, Flex or Academy; repeat for more. Default: every "
            "league scraped (Academy only when AGENT_ACADEMY_CONFERENCES or "
            "AGENT_ACADEMY_TARGETS turns it on).",
        ),
    ] = None,
    since: Annotated[
        str | None,
        typer.Option(
            "--since", help="Only MT matches on or after this date (YYYY-MM-DD)."
        ),
    ] = None,
    only: Annotated[
        str | None,
        typer.Option(
            "--only",
            help="Comma-separated: score,swap,status,redate,voided,mt-only. "
            "A narrowed run reports only what was asked. Default: all.",
        ),
    ] = None,
    env: Annotated[
        str, typer.Option("--env", help="Environment name (local, prod)")
    ] = "local",
    submit: Annotated[
        bool,
        typer.Option(
            "--submit", help="Publish to the queue. Without it this is a dry run."
        ),
    ] = False,
    max_changes: Annotated[
        int,
        typer.Option(
            "--max-changes",
            min=0,
            help="Refuse to publish anything when more corrections than this are due.",
        ),
    ] = 100,
) -> None:
    """Correct past MT matches that disagree with the official feed (SB-1787).

    Reads the official feed and every past MT match of the season, joined on
    match id, and lists each one whose score, home/away, status or date
    differs. With --submit the feed's fixture is published through the
    normal ingest path for each, a JSON change log is written and Telegram
    hears about it. Nothing is ever deleted, and some differences are only
    reported: a locked score, a forfeit with a different score, a result on
    the placeholder date, and a match MT counts as played that the feed does
    not.

    Without --submit nothing is published and nothing is alerted.

    Exit codes: 0 nothing differs; 10 ran, with findings; 1 could not run —
    a feed or MT could not be read, the broker is unreachable, the publish
    target does not match the MT that was read, every send failed, or (with
    --submit only) more than --max-changes corrections are due. A dry run
    over --max-changes warns and exits 10.
    """
    import asyncio
    import json
    from datetime import date, datetime, timedelta
    from zoneinfo import ZoneInfo

    from telegram_notify import escape

    from src.orchestrator import completeness
    from src.orchestrator.completeness import (
        CLASSES,
        FEEDS,
        api_host,
        classify,
        mt_only,
        publish_mismatch,
        totals,
    )
    from src.orchestrator.logger import configure_logging
    from src.orchestrator.report import build_reconcile_report
    from src.orchestrator.settings import AgentSettings, env_file_path
    from src.orchestrator.tools import SEASON_START, _current_season
    from src.scraper.assist_client import AssistClient

    settings = AgentSettings(_env_file=env_file_path(env))
    configure_logging(json_output=settings.json_logs)

    # Academy is opt-in, exactly as it is for the scrape (_target_config): a
    # conference MT does not scrape has no rows worth correcting.
    conferences = settings.academy_conference_set()
    academy_on = settings.academy_targets or bool(conferences)
    default = [league for league in FEEDS if league != "Academy" or academy_on]
    chosen = list(dict.fromkeys(leagues or default))
    unknown = [league for league in chosen if league not in FEEDS]
    if unknown:
        typer.echo(
            f"Unknown league(s) {', '.join(unknown)}. Valid: {', '.join(FEEDS)}",
            err=True,
        )
        raise typer.Exit(code=1)
    if "Academy" in chosen and not academy_on:
        typer.echo(
            "Academy is not scraped here: set AGENT_ACADEMY_CONFERENCES "
            "(or AGENT_ACADEMY_TARGETS) to reconcile it.",
            err=True,
        )
        raise typer.Exit(code=1)

    valid = [*CLASSES, "mt-only"]
    classes = [c.strip() for c in (only or "").split(",") if c.strip()] or valid
    bad = [c for c in classes if c not in valid]
    if bad:
        typer.echo(
            f"Unknown class(es) {', '.join(bad)}. Valid: {', '.join(valid)}",
            err=True,
        )
        raise typer.Exit(code=1)

    # The day MT means, not the pod's: the pod runs in UTC.
    today = datetime.now(ZoneInfo("America/New_York")).date()
    try:
        start = date.fromisoformat(since) if since else SEASON_START
    except ValueError as exc:
        typer.echo(f"Invalid date: {exc}. Use YYYY-MM-DD.", err=True)
        raise typer.Exit(code=1) from None
    end = today - timedelta(days=1)
    if start > end:
        typer.echo(f"--since {start} is not before today ({today}).", err=True)
        raise typer.Exit(code=1)

    # Where this reads and where it would write, before anything happens.
    mode = "SUBMIT" if submit else "DRY RUN, nothing is published"
    typer.echo(f"Reconcile {', '.join(chosen)}, {start} to {end} — {mode}")
    typer.echo(f"MT API: {api_host(settings.missing_table_api_url)}")
    typer.echo(f"Publish target: {_broker_target(settings)}")
    if "Academy" in chosen:
        scope = (
            "every conference"
            if settings.academy_targets
            else (", ".join(sorted(conferences)))
        )
        typer.echo(f"Academy conferences: {scope}")

    def fail(reason: str) -> NoReturn:
        typer.echo(reason, err=True)
        if submit:
            _send_telegram_message(
                settings,
                escape(f"⚠️ Reconcile could not run: {reason}"),
                subject="[match-scraper-agent] Reconcile failed",
            )
        raise typer.Exit(code=1)

    queue_client = None
    if submit:
        mismatch = publish_mismatch(
            settings.missing_table_api_url, settings.queue_name, settings.exchange_name
        )
        if mismatch:
            # Not alerted: a misconfigured manual run is the operator's to fix,
            # and the operator is reading this.
            typer.echo(f"Refusing to publish: {mismatch}. Nothing fetched.", err=True)
            raise typer.Exit(code=1)
        from src.celery.queue_client import MatchQueueClient

        queue_client = MatchQueueClient(**_queue_client_kwargs(settings))
        if not queue_client.check_connection():
            fail("broker unreachable: nothing fetched or published")

    async def _feed():
        async with AssistClient() as client:
            return await completeness.read_feed(client, chosen)

    try:
        feed = asyncio.run(_feed())
    except Exception as exc:
        fail(f"could not read the official feed: {exc}")

    events = [
        e
        for e in feed.events
        if e.league != "Academy"
        or settings.academy_targets
        or e.division in conferences
    ]

    # Every page before anything is sent: a re-dated match moves between them.
    try:
        rows = completeness.read_season(
            settings.missing_table_api_url,
            settings.missing_table_api_key,
            season=_current_season(),
            leagues=chosen,
            start=start,
            end=end,
        )
    except Exception as exc:
        fail(f"could not read missing-table, nothing sent: {exc}")

    changes = [
        c
        for c in classify(events, rows, today=today, leagues=chosen, since=start)
        if c.klass in classes
    ]
    unknown_to_feed = (
        mt_only(rows, feed.game_keys, today=today, leagues=chosen, since=start)
        if "mt-only" in classes
        else []
    )
    to_send = [c for c in changes if c.action == "send"]
    reports = [c for c in changes if c.action == "report"]
    tally = totals(changes)

    typer.echo(f"\nFeed fixtures: {len(events)}, MT rows read: {len(rows)}")
    for change in changes:
        typer.echo(f"  {change.line()}")
    person = [c for c in to_send if c.overrides_person]
    if person:
        typer.echo(
            f"Overrides a person's score (scraped wins on results): {len(person)}"
        )
        for change in person:
            typer.echo(f"  {change.line()}")
    if unknown_to_feed:
        typer.echo(
            f"MT results the feed does not have (never deleted): {len(unknown_to_feed)}"
        )
        for row in unknown_to_feed:
            typer.echo(
                f"  {row.match_id} | mt {row.id} | {row.match_date} "
                f"{row.home_team_name} v {row.away_team_name} {row.score()}"
            )
    typer.echo("\nTotals:")
    for klass, counts_ in tally.items():
        typer.echo(
            f"  {klass:<7} {counts_['send']:>4} to send  {counts_['report']:>4} report only"
        )

    if not changes and not unknown_to_feed:
        typer.echo("\nNothing differs.")
        raise typer.Exit(code=0)

    report_only: dict[str, list[str]] = {}
    for change in reports:
        report_only.setdefault(change.reason, []).append(change.game_key)

    run_id = f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
    log_path = Path(settings.reconcile_log_dir) / f"{run_id}.json"

    def write_log(outcome: dict[str, Any]) -> str:
        """The change log, on the agent-state PVC. Returns its path, or ''."""
        record = {
            "run_id": run_id,
            "env": env,
            "generated_at": datetime.now(UTC).isoformat(),
            "mt_api": api_host(settings.missing_table_api_url),
            "publish_target": _broker_target(settings),
            "leagues": chosen,
            "since": start.isoformat(),
            "classes": classes,
            "totals": tally,
            **outcome,
            "changes": [
                c.model_dump(mode="json")
                | {"sent": c.game_key in outcome.get("sent", [])}
                for c in changes
            ],
            "mt_only": [r.model_dump(mode="json") for r in unknown_to_feed],
        }
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(json.dumps(record, indent=2, sort_keys=True))
        except OSError as exc:
            typer.echo(f"warning: could not write the change log: {exc}", err=True)
            return ""
        typer.echo(f"Change log: {log_path}")
        return str(log_path)

    def alert(**fields: Any) -> None:
        _send_telegram_message(
            settings,
            build_reconcile_report(
                env=env,
                totals=tally,
                report_only=report_only,
                overrides_person=[c.game_key for c in person],
                mt_only=[r.match_id or str(r.id) for r in unknown_to_feed],
                **fields,
            ),
            subject="[match-scraper-agent] MT matches disagree with the feed",
        )

    if len(to_send) > max_changes:
        refused = (
            f"{len(to_send)} corrections to send, more than --max-changes "
            f"{max_changes}; nothing published"
        )
        if not submit:
            typer.echo(f"\nDry run: warning: --submit would refuse: {refused}.")
            raise typer.Exit(code=10)
        typer.echo(f"\nRefusing: {refused}.", err=True)
        path = write_log({"refused": refused, "sent": [], "send_failed": []})
        alert(sent=[], send_failed=[], refused=refused, log_path=path)
        raise typer.Exit(code=1)

    if queue_client is None:
        typer.echo(f"\nDry run: {len(to_send)} would be sent with --submit.")
        raise typer.Exit(code=10)

    sent: list[str] = []
    send_failed: list[str] = []
    for change in to_send:
        try:
            queue_client.submit_match(change.payload())
            sent.append(change.game_key)
        except Exception as exc:
            send_failed.append(change.game_key)
            typer.echo(f"  {change.game_key}  send failed: {exc}", err=True)
    typer.echo(
        f"\nSubmitted {len(sent)} corrections to queue ({len(send_failed)} failed)."
    )

    path = write_log({"refused": "", "sent": sent, "send_failed": send_failed})
    alert(sent=sent, send_failed=send_failed, log_path=path)

    if send_failed and not sent:
        raise typer.Exit(code=1)
    raise typer.Exit(code=10)


# Stands in for the tournament id on a dry run that was not given one, so
# every message is still built and validated. It never reaches the queue:
# the context built from it is flagged stand_in, and _publish_event refuses
# a flagged context whatever the caller believes.
_DRY_RUN_TOURNAMENT_ID = 1

_EVENT_SOURCES = ("modular11", "assist")


def _event_source(
    source: str,
    event: str,
    *,
    delay: float,
    save_raw: Path | None,
    timezone_name: str,
) -> TournamentSource:
    """The adapter for ``--source``. The one place a source is chosen."""
    if source == "assist":
        from src.scraper.tournament.assist_event import AssistEventSource

        return AssistEventSource(event, timezone_name=timezone_name, save_raw=save_raw)
    from src.scraper.tournament.modular11_event import Modular11EventSource

    return Modular11EventSource(event, delay=delay, save_raw=save_raw)


def _event_context(tournament_id: int | None, timezone_name: str) -> TournamentContext:
    """The run's context: the real tournament, or a flagged stand-in.

    Only ``None`` gets the stand-in. Any other value must be a real id — 0 or
    a negative one is refused by the model rather than quietly replaced.
    """
    from src.models.tournament import TournamentContext

    if tournament_id is None:
        return TournamentContext(
            tournament_id=_DRY_RUN_TOURNAMENT_ID,
            timezone=timezone_name,
            stand_in=True,
        )
    return TournamentContext(tournament_id=tournament_id, timezone=timezone_name)


def _broker_target(settings: AgentSettings) -> str:
    """Where a publish goes, for the operator: host and queue, no credentials."""
    from urllib.parse import urlsplit

    try:
        parts = urlsplit(settings.rabbitmq_url)
        host = parts.hostname or "(unknown host)"
        if parts.port:
            host = f"{host}:{parts.port}"
    except ValueError:
        host = "(unreadable broker URL)"
    if settings.queue_name:
        return f"broker {host}, queue '{settings.queue_name}'"
    return f"broker {host}, exchange '{settings.exchange_name}'"


def _publish_event(
    queue_client: Any, context: TournamentContext, messages: list[MatchData]
) -> tuple[int, int]:
    """Publish the messages. Returns ``(submitted, errors)``.

    Refuses a stand-in context: its tournament id is not a tournament, and a
    message carrying it would be filed on whichever one has that id.
    """
    if context.stand_in:
        raise RuntimeError(
            "refusing to publish: the tournament id is a dry-run stand-in"
        )
    submitted = errors = 0
    for message in messages:
        if message.tournament_id != context.tournament_id:
            raise RuntimeError("refusing to publish: message built for another id")
        try:
            queue_client.submit_match(message.model_dump(mode="json"))
            submitted += 1
        except Exception as exc:
            errors += 1
            typer.echo(
                f"warning: match {message.external_match_id} not published: {exc}",
                err=True,
            )
    return submitted, errors


def _event_summary(
    matches: list[TournamentMatch], messages: list[MatchData]
) -> dict[str, Any]:
    """What a scrape-event run found, as counts."""
    from collections import Counter

    unmapped: Counter[str] = Counter()
    for match in matches:
        unmapped.update(match.mapped().unmapped)
    teams = {m.home_team for m in matches} | {m.away_team for m in matches}
    return {
        "matches": len(matches),
        "by_age_group": dict(sorted(Counter(m.age_group for m in matches).items())),
        "by_round": dict(
            Counter(m.tournament_round or "(no round)" for m in messages).most_common()
        ),
        "by_status": dict(Counter(str(m.match_status) for m in messages).most_common()),
        "penalties": sum(1 for m in messages if m.home_penalty_score is not None),
        "teams": len(teams),
        # missing-table resolves a team name with no league hint only when
        # exactly one team has that name.
        "no_league": dict(
            Counter(
                m.competition or "(no competition)" for m in messages if not m.league
            ).most_common()
        ),
        "unmapped": dict(sorted(unmapped.items())),
    }


@app.command(name="scrape-event")
def scrape_event(
    source: Annotated[
        str | None,
        typer.Option(
            "--source",
            help="Where the event is published: modular11 or assist. "
            "Defaults to AGENT_EVENT_SOURCE, else modular11.",
        ),
    ] = None,
    event: Annotated[
        str | None,
        typer.Option(
            "--event",
            help="modular11 event id (75 = MLS NEXT Fest 2025) or assist feed "
            "key. Defaults to AGENT_EVENT_ID.",
        ),
    ] = None,
    tournament_id: Annotated[
        int | None,
        typer.Option(
            "--tournament-id",
            min=1,
            help="missing-table tournament id. Defaults to "
            "AGENT_EVENT_TOURNAMENT_ID; required with --submit.",
        ),
    ] = None,
    age_groups: Annotated[
        list[str] | None,
        typer.Option(
            "--age-group", "-a", help="Age group; repeat for several. Default: all six."
        ),
    ] = None,
    from_date: Annotated[
        str | None,
        typer.Option("--from", help="Start date (YYYY-MM-DD). Default: season start."),
    ] = None,
    to_date: Annotated[
        str | None,
        typer.Option("--to", help="End date (YYYY-MM-DD). Default: season end."),
    ] = None,
    env: Annotated[
        str, typer.Option("--env", help="Environment name (local, prod)")
    ] = "local",
    submit: Annotated[
        bool,
        typer.Option(
            "--submit", help="Publish to the queue. Without it this is a dry run."
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print the messages as JSON (summary to stderr)"),
    ] = False,
    delay: Annotated[
        float,
        typer.Option(
            "--delay", help="Seconds between requests (modular11), plus jitter"
        ),
    ] = 1.0,
    save_raw: Annotated[
        Path | None,
        typer.Option("--save-raw", help="Directory to keep every fetched page in"),
    ] = None,
) -> None:
    """Scrape a tournament event for every age group and send it to missing-table.

    One command, any source: the same messages come out whether the event is
    a modular11 event page or an assist feed. Each match carries its
    competition, group, round and penalty score, and an id that is stable
    across runs, so re-running updates scores and creates nothing twice.

    Without --submit nothing is published: it prints matches per age group and
    per round, how many distinct team names the event uses, and every
    competition, division or round label the mapping does not know.

    Exit codes: 0 clean; 10 ran, with findings (an age group failed, a match
    could not be built or published, rows could not be read, or the feed
    carried values the mapping does not know); 1 could not run — bad
    arguments, nothing could be fetched, the broker is unreachable, or
    nothing could be published.
    """
    import asyncio
    from datetime import date, datetime

    from pydantic import ValidationError

    from src.orchestrator.logger import configure_logging
    from src.orchestrator.settings import AgentSettings, env_file_path
    from src.scraper.modular11 import AGE_GROUP_IDS, current_season_year, season_window

    configure_logging(json_output=False)
    settings = AgentSettings(_env_file=env_file_path(env))

    source = source or settings.event_source or "modular11"
    event = event or settings.event_id
    # The setting is shared with every agent command and is deliberately
    # lenient there; here is where a bad value matters. `is None`, not `or`.
    setting_raw = settings.event_tournament_id
    # warn=False: reported below on stderr, where it cannot land in the
    # middle of --json output (the structured logger prints to stdout).
    setting_id = settings.event_tournament_id_or_none(warn=False)
    bad_setting = bool(setting_raw) and setting_id is None
    if bad_setting and not submit:
        typer.echo(
            f"warning: AGENT_EVENT_TOURNAMENT_ID is {setting_raw!r}, not a "
            "tournament id (1 or more); treated as unset.",
            err=True,
        )
    if tournament_id is None:
        tournament_id = setting_id
    ages = list(age_groups or AGE_GROUP_IDS)

    if source not in _EVENT_SOURCES:
        typer.echo(
            f"Unknown source '{source}'. Valid sources: {', '.join(_EVENT_SOURCES)}",
            err=True,
        )
        raise typer.Exit(code=1)
    if not event:
        typer.echo("No event: pass --event or set AGENT_EVENT_ID.", err=True)
        raise typer.Exit(code=1)
    if submit and (not isinstance(tournament_id, int) or tournament_id < 1):
        if bad_setting:
            typer.echo(
                f"--submit needs a tournament id of 1 or more, and "
                f"AGENT_EVENT_TOURNAMENT_ID is {setting_raw!r}. Nothing fetched "
                "or published. Fix the setting or pass --tournament-id.",
                err=True,
            )
        else:
            typer.echo(
                "--submit needs a tournament: pass --tournament-id or set "
                "AGENT_EVENT_TOURNAMENT_ID.",
                err=True,
            )
        raise typer.Exit(code=1)
    unknown_ages = [age for age in ages if age not in AGE_GROUP_IDS]
    if unknown_ages:
        typer.echo(
            f"Unknown age group(s) {', '.join(unknown_ages)}. "
            f"Valid: {', '.join(AGE_GROUP_IDS)}",
            err=True,
        )
        raise typer.Exit(code=1)

    season_start, season_end = season_window(current_season_year())
    try:
        start = date.fromisoformat(from_date) if from_date else season_start
        end = date.fromisoformat(to_date) if to_date else season_end
        context = _event_context(tournament_id, settings.event_timezone)
    except ValueError as exc:
        typer.echo(f"Invalid date, timezone or tournament id: {exc}", err=True)
        raise typer.Exit(code=1) from None
    if start > end:
        typer.echo(f"--from {start} is later than --to {end}.", err=True)
        raise typer.Exit(code=1)

    # The summary goes to stderr under --json so stdout stays parseable.
    def say(text: str = "") -> None:
        typer.echo(text, err=json_output)

    mode = "SUBMIT" if submit else "DRY RUN, nothing is published"
    say(f"Event {event} via {source}, {start} to {end} — {mode}")

    queue_client = None
    if submit:
        from src.celery.queue_client import MatchQueueClient

        # Where the messages are going, before any goes. --env only picks an
        # env file; the queue is whatever the settings resolve to.
        say(
            f"Publishing to {_broker_target(settings)}, "
            f"tournament id {context.tournament_id}"
        )
        queue_client = MatchQueueClient(**_queue_client_kwargs(settings))
        # Once, up front: a broker that is down fails here rather than on
        # every one of a few thousand messages, and before the feed is asked
        # for anything.
        if not queue_client.check_connection():
            typer.echo("Broker unreachable: nothing fetched or published.", err=True)
            raise typer.Exit(code=1)

    event_source = _event_source(
        source,
        event,
        delay=delay,
        save_raw=save_raw,
        timezone_name=settings.event_timezone,
    )
    matches = asyncio.run(event_source.fetch(ages, start, end))
    fetched = len(matches)
    # Both sources are asked for the window; a source that ignores it must not
    # widen what is sent.
    matches = [m for m in matches if start <= m.kickoff_local.date() <= end]
    # A fixture listed before its teams are decided names a team "TBD", and
    # missing-table has a real team row called TBD: sent, it would be filed
    # on that row. It is skipped, and sent once the feed names the teams.
    placeholders = sum(1 for m in matches if not m.teams_known())
    matches = [m for m in matches if m.teams_known()]
    context = context.model_copy(update={"id_prefix": event_source.id_prefix})

    now = datetime.now(UTC)
    messages: list[MatchData] = []
    invalid = 0
    for match in matches:
        try:
            messages.append(match.to_message(context, now=now))
        except ValidationError as exc:
            invalid += 1
            # stderr, not the structured logger: that prints to stdout, into
            # the middle of --json.
            typer.echo(
                f"warning: match {match.source_match_id} could not be built: "
                f"{exc.errors()[0]['msg']}",
                err=True,
            )

    summary = _event_summary(matches, messages)
    for what, count in event_source.unmapped.items():
        summary["unmapped"][what] = summary["unmapped"].get(what, 0) + count

    if json_output:
        import json

        dumped = [message.model_dump(mode="json") for message in messages]
        if tournament_id is None:
            for item in dumped:
                item["tournament_id"] = None
        print(json.dumps(dumped, indent=2))

    say(f"\nMatches: {summary['matches']}")
    for age, count in summary["by_age_group"].items():
        say(f"  {age:<5}{count:>6}")
    say("Rounds:")
    for round_key, count in summary["by_round"].items():
        say(f"  {round_key:<18}{count:>6}")
    say("Status:")
    for status, count in summary["by_status"].items():
        say(f"  {status:<18}{count:>6}")
    say(f"Decided on penalties: {summary['penalties']}")
    say(f"Distinct team names: {summary['teams']}")
    if summary["no_league"]:
        say(f"Sent with no league hint: {sum(summary['no_league'].values())}")
        for competition, count in summary["no_league"].items():
            say(f"  {count:>5}  {competition}")
    if summary["unmapped"]:
        say("Unmapped values (matches carrying each):")
        for what, count in summary["unmapped"].items():
            say(f"  {count:>5}  {what}")
    else:
        say("Unmapped values: none")
    if placeholders:
        say(f"skipped: opponent not decided: {placeholders}")
    if invalid:
        say(f"Matches that could not be built: {invalid}")
    for age, reason in event_source.failures.items():
        say(f"FAILED {age}: {reason}")
    if tournament_id is None:
        say("No tournament id set: messages cannot be submitted yet.")

    submitted = errors = 0
    if queue_client is not None:
        submitted, errors = _publish_event(queue_client, context, messages)
        say(f"\nSubmitted {submitted} matches to queue ({errors} errors).")

    # An outage is not a finding: nothing read, or nothing published, is
    # "could not run", so a scheduled job that shrugs at 10 still fails.
    if event_source.failures and not fetched:
        raise typer.Exit(code=1)
    if errors and not submitted:
        raise typer.Exit(code=1)
    if event_source.failures or invalid or errors or summary["unmapped"]:
        raise typer.Exit(code=10)


def _send_telegram_processor_report(
    settings: AgentSettings,
    result: Any,
    env: str,
) -> None:
    """Send processor summary report to Telegram. Silently skips if not configured."""
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.debug("telegram.skipped", reason="not configured")
        return

    from telegram_notify import TelegramClient

    from src.orchestrator.audit.report import build_processor_report

    report = build_processor_report(result=result, env=env)
    try:
        client = TelegramClient(
            bot_token=settings.telegram_bot_token,
            chat_id=settings.telegram_chat_id,
        )
        client.send(report)
        logger.info("telegram.sent", chat_id=settings.telegram_chat_id)
    except Exception as exc:
        logger.warning("telegram.failed", error=str(exc))
        _send_email_alert(
            settings,
            subject="[match-scraper-agent] Telegram failed — processor report",
            body=f"Telegram notification failed: {exc}\n\n{report}",
        )


@app.command()
def audit(
    env: Annotated[
        str, typer.Option("--env", help="Environment name (local, prod)")
    ] = "local",
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Skip mutating operations")
    ] = False,
    json_logs: Annotated[
        bool, typer.Option("--json-logs", help="Output JSON log lines")
    ] = False,
    team: Annotated[
        str | None,
        typer.Option(
            "--team",
            help="Audit a specific team (skips rotation). Requires --age-group.",
        ),
    ] = None,
    age_group: Annotated[
        str | None,
        typer.Option("--age-group", help="Age group for --team override (e.g. U14)"),
    ] = None,
    count: Annotated[
        int,
        typer.Option(
            "--count", help="Max teams to audit per run (rotation). Default: 1."
        ),
    ] = 1,
) -> None:
    """Audit teams against mlssoccer.com source of truth."""
    import asyncio
    from datetime import date

    from src.orchestrator.audit.runner import run_one_team_audit
    from src.orchestrator.logger import configure_logging
    from src.orchestrator.settings import AgentSettings, env_file_path

    settings = AgentSettings(_env_file=env_file_path(env))
    configure_logging(
        json_output=json_logs or settings.json_logs, log_level=settings.log_level
    )

    run_id = uuid.uuid4().hex[:12]
    structlog.contextvars.bind_contextvars(run_id=run_id, env=env)

    try:
        season_start = date.fromisoformat(settings.audit_season_start)
    except ValueError:
        typer.echo(
            f"Invalid AGENT_AUDIT_SEASON_START: {settings.audit_season_start}", err=True
        )
        raise typer.Exit(code=1) from None

    from src.orchestrator.tools import SEASON_END

    if bool(team) != bool(age_group):
        typer.echo("--team and --age-group must be used together", err=True)
        raise typer.Exit(code=1)

    # When a specific team is requested, ignore --count and run exactly once
    max_iterations = 1 if (team and age_group) else count

    audited = 0
    for _ in range(max_iterations):
        try:
            result = asyncio.run(
                run_one_team_audit(
                    settings=settings,
                    dry_run=dry_run,
                    season_start=season_start,
                    season_end=SEASON_END,
                    team_override=team,
                    age_group_override=age_group,
                )
            )
        except Exception as exc:
            logger.error("audit.failed", error=str(exc), exc_info=exc)
            raise typer.Exit(code=1) from None

        if result is None:
            logger.info("audit.all_teams_current")
            typer.echo("All teams are up-to-date. Nothing to audit.")
            break

        audited += 1
        logger.info(
            "audit.completed",
            team=result.team,
            age_group=result.age_group,
            scraped=result.scraped_count,
            mt=result.mt_count,
            findings=len(result.findings),
        )
        typer.echo(
            f"Audited {result.team} {result.age_group}: "
            f"{result.scraped_count} scraped, {result.mt_count} in MT, "
            f"{len(result.findings)} findings"
        )
        # Findings are not sent to Telegram: audit-process corrects them half
        # an hour later, and only what it cannot correct needs a person (SB-1679).

    if audited > 1:
        logger.info("audit.batch_done", audited=audited)

    structlog.contextvars.unbind_contextvars("run_id", "env")


@app.command(name="audit-process")
def audit_process(
    env: Annotated[
        str, typer.Option("--env", help="Environment name (local, prod)")
    ] = "local",
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Skip mutating operations")
    ] = False,
    json_logs: Annotated[
        bool, typer.Option("--json-logs", help="Output JSON log lines")
    ] = False,
) -> None:
    """Process pending audit findings — resubmit corrections to RabbitMQ."""
    import asyncio

    from src.celery.queue_client import MatchQueueClient
    from src.orchestrator.audit.processor import process_pending_events
    from src.orchestrator.logger import configure_logging
    from src.orchestrator.settings import AgentSettings, env_file_path

    settings = AgentSettings(_env_file=env_file_path(env))
    configure_logging(
        json_output=json_logs or settings.json_logs, log_level=settings.log_level
    )

    run_id = uuid.uuid4().hex[:12]
    structlog.contextvars.bind_contextvars(run_id=run_id, env=env)

    queue_client = MatchQueueClient(**_queue_client_kwargs(settings))

    try:
        result = asyncio.run(
            process_pending_events(
                settings=settings,
                queue_client=queue_client,
                dry_run=dry_run,
            )
        )
    except Exception as exc:
        logger.error("audit_process.failed", error=str(exc), exc_info=exc)
        raise typer.Exit(code=1) from None

    logger.info(
        "audit_process.completed",
        events_processed=result.events_processed,
        matches_resubmitted=result.matches_resubmitted,
        extra_in_mt_skipped=result.extra_in_mt_skipped,
        errors=result.errors,
    )

    # Corrections are routine. Only a match in MT that the feed no longer has
    # needs a person to look before anything is cancelled (SB-1679).
    if result.extra_in_mt_skipped:
        _send_telegram_processor_report(settings=settings, result=result, env=env)

    structlog.contextvars.unbind_contextvars("run_id", "env")


@app.command(name="audit-report")
def audit_report(
    env: Annotated[
        str, typer.Option("--env", help="Environment name (local, prod)")
    ] = "local",
) -> None:
    """Show audit coverage for all HG Northeast teams across all age groups."""
    import asyncio
    from datetime import date, datetime

    from src.orchestrator.audit.client import fetch_audit_team_status
    from src.orchestrator.settings import AgentSettings, env_file_path
    from src.orchestrator.tools import _current_season

    settings = AgentSettings(_env_file=env_file_path(env))
    season = _current_season()
    today = date.today()

    age_groups = ["U13", "U14", "U15", "U16"]
    league = "Homegrown"
    division = "Northeast"
    overdue_days = 7

    teams = asyncio.run(
        fetch_audit_team_status(
            api_url=settings.missing_table_api_url,
            api_key=settings.missing_table_api_key or "",
            season=season,
            league=league,
            division=division,
        )
    )

    by_ag: dict[str, list] = {ag: [] for ag in age_groups}
    for t in teams:
        if t.age_group in by_ag:
            by_ag[t.age_group].append(t)

    typer.echo(f"\nAudit Progress — HG {division} — {season}")
    typer.echo(f"Generated: {today}  |  Overdue threshold: >{overdue_days} days\n")

    col_ag = 10
    col_team = 34
    col_date = 13
    col_days = 6
    col_findings = 10
    header = (
        f"{'AGE GRP':<{col_ag}}{'TEAM':<{col_team}}"
        f"{'LAST AUDITED':<{col_date}}{'DAYS':>{col_days}}"
        f"{'FINDINGS':>{col_findings}}  STATUS"
    )
    separator = "-" * len(header)
    typer.echo(header)
    typer.echo(separator)

    total = audited_week = overdue_count = never_count = 0

    for ag in age_groups:
        for t in sorted(by_ag[ag], key=lambda x: x.team):
            total += 1
            if t.last_audited_at:
                dt = datetime.fromisoformat(t.last_audited_at).replace(tzinfo=UTC)
                days_ago = (today - dt.date()).days
                date_str = dt.date().isoformat()
                days_str = str(days_ago)
                findings_str = str(t.findings_count) if t.findings_count else "-"
                if days_ago <= overdue_days:
                    status = "OK"
                    audited_week += 1
                else:
                    status = "OVERDUE"
                    overdue_count += 1
            else:
                date_str = "never"
                days_str = "-"
                findings_str = "-"
                status = "PENDING"
                never_count += 1

            typer.echo(
                f"{ag:<{col_ag}}{t.team:<{col_team}}"
                f"{date_str:<{col_date}}{days_str:>{col_days}}"
                f"{findings_str:>{col_findings}}  {status}"
            )

    typer.echo(separator)
    typer.echo(
        f"\nTotal: {total}  |  Audited this week: {audited_week}"
        f"  |  Overdue: {overdue_count}  |  Pending: {never_count}\n"
    )


def _send_telegram_message(
    settings: AgentSettings, message: str, *, subject: str
) -> bool:
    """
    Send one MarkdownV2 message, falling back to email if Telegram fails.

    Mirrors _send_telegram_report but takes a prebuilt message, since the
    release watcher has nothing to do with run summaries. Returns whether
    Telegram itself accepted the message.
    """
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.debug("telegram.skipped", reason="not configured")
        return False

    from telegram_notify import TelegramClient

    try:
        client = TelegramClient(
            bot_token=settings.telegram_bot_token,
            chat_id=settings.telegram_chat_id,
        )
        client.send(message)
        logger.info("telegram.sent", chat_id=settings.telegram_chat_id)
        return True
    except Exception as exc:
        logger.warning("telegram.failed", error=str(exc))
        _send_email_alert(
            settings,
            subject=subject,
            body=f"Telegram notification failed: {exc}\n\n{message}",
        )
        return False


def _send_slack_message(settings: AgentSettings, text: str) -> bool:
    """
    Post one message to the Slack alert channel. No-op without a bot token.

    Only the Fest release uses this (SB-1774): routine alerts stay on Telegram,
    and ops alerts reach #sb-alerts through Grafana. Never raises — a Slack
    outage must not cost the Telegram message or the saved state.
    """
    if not settings.slack_bot_token:
        logger.debug("slack.skipped", reason="slack_bot_token not configured")
        return False

    import httpx

    try:
        response = httpx.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {settings.slack_bot_token}"},
            json={"channel": settings.slack_alert_channel, "text": text},
            timeout=10.0,
        )
        response.raise_for_status()
        body = response.json()
        if not body.get("ok"):
            raise RuntimeError(f"slack error: {body.get('error', 'unknown')}")
        logger.info("slack.sent", channel=settings.slack_alert_channel)
        return True
    except Exception as exc:
        logger.warning("slack.failed", error=str(exc))
        return False


@app.command()
def watchdog(
    env: Annotated[
        str, typer.Option("--env", help="Environment name (local, prod)")
    ] = "local",
    max_age_hours: Annotated[
        float,
        typer.Option(
            "--max-age-hours",
            help="Alert when the last successful run is older than this.",
        ),
    ] = 8.0,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Report the finding but send nothing."),
    ] = False,
) -> None:
    """
    Alert when no run has succeeded recently.

    Covers the failures nothing inside the agent can report, because in all of
    them the agent never runs: a pod that could not start (ImagePullBackOff,
    OOMKilled), a CronJob suspended or deleted, or a sleeping node — this
    cluster is a Mac (SB-1062).

    Reads the run journal, which a successful run writes and a failed one does
    not, so journal age is a direct measure of "when did this last work".

    Exit codes are outcomes, not crashes, matching the release watcher and the
    score canary: 0 healthy, 10 stale or missing. A non-zero exit that
    Kubernetes read as a failed Job would retry it and bury the signal.
    """
    from datetime import UTC, datetime

    from src.orchestrator.journal import read_journal
    from src.orchestrator.logger import configure_logging
    from src.orchestrator.report import build_watchdog_report
    from src.orchestrator.settings import AgentSettings, env_file_path

    settings = AgentSettings(_env_file=env_file_path(env))
    configure_logging(json_output=settings.json_logs)

    journal = read_journal(
        settings.journal_s3_bucket,
        settings.journal_s3_key,
        settings.journal_path,
    )

    now = datetime.now(tz=UTC)
    last_run_at: str | None = None
    age_hours: float | None = None

    if journal is None:
        reason = "No run journal could be read"
    else:
        last_run_at = journal.timestamp
        try:
            age_hours = (
                now - datetime.fromisoformat(journal.timestamp)
            ).total_seconds() / 3600
        except ValueError:
            reason = f"Run journal has an unreadable timestamp: {journal.timestamp}"
            age_hours = None
        else:
            if age_hours <= max_age_hours:
                logger.info(
                    "watchdog.healthy",
                    last_run_at=last_run_at,
                    age_hours=round(age_hours, 2),
                    max_age_hours=max_age_hours,
                )
                typer.echo(
                    f"watchdog: last successful run {age_hours:.1f}h ago — healthy"
                )
                return
            reason = f"The last successful run was {age_hours:.1f}h ago"

    logger.error(
        "watchdog.stale",
        last_run_at=last_run_at,
        age_hours=None if age_hours is None else round(age_hours, 2),
        max_age_hours=max_age_hours,
        reason=reason,
    )
    typer.echo(f"watchdog: STALE — {reason}")

    if not dry_run:
        _send_telegram_message(
            settings,
            build_watchdog_report(
                env=env,
                last_run_at=last_run_at,
                age_hours=age_hours,
                max_age_hours=max_age_hours,
                reason=reason,
                now=now,
            ),
            subject="[match-scraper-agent] No successful run in too long",
        )

    raise typer.Exit(code=10)


@app.command()
def digest(
    env: Annotated[
        str, typer.Option("--env", help="Environment name (local, prod)")
    ] = "local",
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Print the digest but send nothing."),
    ] = False,
) -> None:
    """
    Send the daily scores digest: today's matches scored, and matches played
    but still waiting for a score (SB-1679).

    The one scheduled message left. Run reports only go out when something
    needs a person, so this is where "are the scores coming in" gets answered.
    """
    from datetime import UTC, date, datetime, timedelta
    from zoneinfo import ZoneInfo

    from telegram_notify import escape

    from src.orchestrator.digest import (
        LOOKBACK_DAYS,
        build_digest_report,
        fetch_recent_matches,
        summarize,
    )
    from src.orchestrator.logger import configure_logging
    from src.orchestrator.settings import AgentSettings, env_file_path

    settings = AgentSettings(_env_file=env_file_path(env))
    configure_logging(json_output=settings.json_logs)

    now = datetime.now(tz=UTC)
    today = now.astimezone(ZoneInfo("America/New_York")).date()
    try:
        matches = fetch_recent_matches(
            settings.missing_table_api_url,
            settings.missing_table_api_key,
            start=today - timedelta(days=LOOKBACK_DAYS),
            end=today,
        )
    except Exception as exc:
        logger.error("digest.fetch_failed", error=str(exc))
        if not dry_run:
            _send_telegram_message(
                settings,
                escape(f"⚠️ Scores digest failed: could not read missing-table ({exc})"),
                subject="[match-scraper-agent] Scores digest failed",
            )
        raise typer.Exit(code=1) from None

    summary = summarize(matches, now)
    logger.info("digest.summary", **summary.model_dump(mode="json"))
    # The completeness backfill's last word on results absent from MT
    # (SB-1786). No record — the job has never run here — leaves the line out.
    from src.orchestrator.alert_state import read_gap_state

    gap_state = read_gap_state(settings.completeness_state_path)
    not_in_mt = as_of = None
    if "still_missing" in gap_state:
        not_in_mt = len(gap_state["still_missing"])
        try:
            as_of = date.fromisoformat(gap_state.get("day", ""))
        except ValueError:
            as_of = None
    message = build_digest_report(summary, not_in_mt=not_in_mt, not_in_mt_as_of=as_of)
    typer.echo(message)

    if not dry_run:
        _send_telegram_message(
            settings, message, subject="[match-scraper-agent] Scores digest"
        )


@app.command()
def notify(
    text: Annotated[str, typer.Option("--text", help="Message body to send.")],
    env: Annotated[
        str, typer.Option("--env", help="Environment name (local, prod)")
    ] = "local",
    title: Annotated[
        str, typer.Option("--title", help="Bold first line.")
    ] = "match-scraper",
    icon: Annotated[str, typer.Option("--icon", help="Leading emoji.")] = "⚠️",
) -> None:
    """
    Send one plain Telegram message.

    For manifests that reach a finding in shell and had nowhere to put it — the
    score canary echoed "FIXTURES PLAYED AND NONE SCORED" to container stdout
    and exited 0, where nobody would ever read it (SB-1062). Text is escaped
    here so a caller does not have to know MarkdownV2.
    """
    from telegram_notify import escape

    from src.orchestrator.logger import configure_logging
    from src.orchestrator.settings import AgentSettings, env_file_path

    settings = AgentSettings(_env_file=env_file_path(env))
    configure_logging(json_output=settings.json_logs)

    message = "\n".join([f"{icon} *{escape(title)}*", "", escape(text)])
    _send_telegram_message(settings, message, subject=f"[match-scraper-agent] {title}")


@app.command(name="watch-release")
def watch_release(
    env: Annotated[
        str, typer.Option("--env", help="Environment name (local, prod)")
    ] = "local",
    age_groups: Annotated[
        list[str] | None,
        typer.Option(
            "--age-group", "-a", help="Age group to check; repeat for several."
        ),
    ] = None,
    divisions: Annotated[
        list[str] | None,
        typer.Option("--division", "-d", help="Division to check; repeat for several."),
    ] = None,
    full_season: Annotated[
        bool,
        typer.Option(
            "--full-season", help="Search the whole season, not just the fall."
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Probe and report, but send and save nothing."),
    ] = False,
    fest: Annotated[
        bool | None,
        typer.Option(
            "--fest/--no-fest",
            help="Also watch the MLS NEXT Fest pages (default: AGENT_RELEASE_WATCH_FEST).",
        ),
    ] = None,
) -> None:
    """
    Watch for the MLS Next schedule being published, and announce it once.

    Also watches the MLS NEXT Fest pages, and announces the Fest schedule on
    Telegram, Slack and email at once (SB-1774).

    Designed to run unattended on a CronJob. Sends Telegram on the first
    detection of each target and on a sustained probe outage; stays silent
    otherwise, because "still not published" is the expected state for weeks.

    Notify-only by design — it never scrapes. A new season's page format is
    unverified until a human looks at it, and publishing bad data to
    missing-table unattended is worse than waiting.
    """
    from src.orchestrator.logger import configure_logging
    from src.orchestrator.release_watch import read_state, write_state
    from src.orchestrator.report import (
        build_release_failure_report,
        build_release_report,
    )
    from src.orchestrator.settings import AgentSettings, env_file_path
    from src.scraper.release_detector import (
        ReleaseDetectorError,
        ScheduleReleaseDetector,
    )

    settings = AgentSettings(_env_file=env_file_path(env))
    configure_logging(json_output=settings.json_logs)

    try:
        detector = ScheduleReleaseDetector(
            age_groups=age_groups or None,
            divisions=divisions or None,
            fall_only=not full_season,
        )
    except ReleaseDetectorError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    import asyncio

    probe = asyncio.run(detector.probe())

    # S3 when a bucket is configured, otherwise a file on the mounted PVC.
    # Either way the state must survive the pod, or every run re-announces.
    bucket = settings.journal_s3_bucket
    state_path = settings.release_watch_state_path
    persist = bool(bucket or state_path) and not dry_run

    if persist:
        state = read_state(bucket, settings.release_watch_s3_key, state_path)
    else:
        from src.orchestrator.release_watch import ReleaseWatchState

        state = ReleaseWatchState()

    state.reset_for_season(probe.season)

    live_labels = [r.label for r in probe.live]
    newly_live = state.newly_live(live_labels)

    typer.echo(probe.summary())

    if probe.all_failed:
        state.consecutive_failures += 1
        threshold = settings.release_watch_failure_threshold
        logger.warning(
            "release_watch.all_failed",
            consecutive=state.consecutive_failures,
            threshold=threshold,
        )
        if state.consecutive_failures >= threshold and not state.failure_alert_sent:
            sample = probe.errors[0].error if probe.errors else "unknown"
            if not dry_run:
                _send_telegram_message(
                    settings,
                    build_release_failure_report(
                        season=probe.season,
                        consecutive_failures=state.consecutive_failures,
                        total_targets=len(probe.results),
                        sample_error=sample or "unknown",
                    ),
                    subject="[match-scraper-agent] Schedule watch failing",
                )
            state.failure_alert_sent = True
    else:
        state.consecutive_failures = 0
        state.failure_alert_sent = False

    if newly_live:
        logger.info("release_watch.released", targets=newly_live)
        if not dry_run:
            _send_telegram_message(
                settings,
                build_release_report(
                    season=probe.season,
                    newly_live=newly_live,
                    window_start=probe.window_start.isoformat(),
                    window_end=probe.window_end.isoformat(),
                    total_targets=len(probe.results),
                ),
                subject="[match-scraper-agent] MLS Next schedule published",
            )
        state.record_live(newly_live)

    fest_released = False
    if settings.release_watch_fest if fest is None else fest:
        fest_released = _watch_fest(settings, state, dry_run=dry_run)

    state.touch()

    if persist:
        write_state(bucket, settings.release_watch_s3_key, state, state_path)

    if probe.all_failed:
        raise typer.Exit(code=20)
    if newly_live or fest_released:
        raise typer.Exit(code=10)


def _watch_fest(
    settings: AgentSettings, state: ReleaseWatchState, *, dry_run: bool
) -> bool:
    """
    Probe the Fest pages and announce a release once, loudly (SB-1774).

    Returns whether a release was seen on this run. Mutates ``state``; the
    caller saves it. Stops probing once announced: after Fest the pages will
    change or vanish, and that must not turn into failure alerts.
    """
    import asyncio

    from src.orchestrator.report import build_fest_failure_report
    from src.scraper.fest_watch import FestWatcher

    if state.fest_announced:
        typer.echo(f"fest: already announced ({state.fest_link})")
        return False

    try:
        probe = asyncio.run(FestWatcher().probe())
    except Exception as exc:  # never let Fest break the league watch
        logger.warning("fest_watch.crashed", error=str(exc))
        probe = None

    if probe is None or probe.all_failed:
        typer.echo(probe.summary() if probe else "fest: probe crashed")
        state.fest_consecutive_failures += 1
        threshold = settings.release_watch_failure_threshold
        if (
            state.fest_consecutive_failures >= threshold
            and not state.fest_failure_alert_sent
        ):
            sample = probe.errors[0].detail if probe else "probe crashed"
            if not dry_run:
                _send_telegram_message(
                    settings,
                    build_fest_failure_report(
                        consecutive_failures=state.fest_consecutive_failures,
                        total_pages=len(probe.results) if probe else 0,
                        sample_error=sample,
                    ),
                    subject="[match-scraper-agent] Fest schedule watch failing",
                )
            state.fest_failure_alert_sent = True
        return False

    typer.echo(probe.summary())
    state.fest_consecutive_failures = 0
    state.fest_failure_alert_sent = False

    if not probe.released:
        return False

    released = [(r.name, r.detail) for r in probe.released]
    logger.info("fest_watch.released", pages=released)
    if dry_run:
        return True

    if _announce_fest_release(settings, released):
        state.fest_announced = True
        state.fest_link = released[0][1]
    else:
        # Nothing got through: leave it unannounced so the next run retries.
        logger.error("fest_watch.announce_undelivered", pages=released)
    return True


def _announce_fest_release(
    settings: AgentSettings, released: list[tuple[str, str]]
) -> bool:
    """Send the Fest release everywhere at once. True if any channel took it."""
    from src.orchestrator.report import (
        build_fest_release_report,
        build_fest_release_text,
    )

    text = build_fest_release_text(released)
    subject = "🚨 MLS NEXT Fest schedule is published"
    delivered = [
        _send_telegram_message(
            settings, build_fest_release_report(released), subject=subject
        ),
        _send_slack_message(settings, f"<!channel> :rotating_light: {text}"),
        _send_email_alert(settings, subject=subject, body=text),
    ]
    return any(delivered)
