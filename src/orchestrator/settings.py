"""Environment-based configuration for match-scraper-agent."""

from __future__ import annotations

import re
from pathlib import Path

import structlog
from pydantic import field_validator
from pydantic_settings import BaseSettings

from src.celery.queue_client import DEFAULT_QUEUE

ENVS_DIR = Path(__file__).resolve().parents[2] / "envs"

_POSITIVE_INT = re.compile(r"[0-9]+")


def env_file_path(env: str) -> Path | None:
    """Resolve the dotenv file for a given environment name.

    Args:
        env: Environment name (e.g. "local", "prod").

    Returns:
        Path to envs/.env.<env>, or None if it doesn't exist (e.g. in a
        container where settings come from environment variables).
    """
    path = ENVS_DIR / f".env.{env}"
    if not path.is_file():
        return None
    return path


class AgentSettings(BaseSettings):
    """Agent configuration loaded from a dotenv file + environment variables.

    Precedence: env vars > dotenv file > defaults.
    Pass _env_file to the constructor to select which env file to load.
    """

    model_config = {"env_prefix": "AGENT_", "extra": "ignore"}

    # Academy targets are off by default. The Academy feed declares 120
    # brackets and 271 clubs, 155 of which missing-table does not have; a
    # target whose teams cannot be resolved drops its matches and files a name
    # failure for each one, so this waits on the club onboarding (SB-1018).
    academy_targets: bool = False
    # Or name the Academy conferences to scrape, comma-separated, e.g.
    # "New England". Lets Academy roll out one conference at a time as its
    # clubs get Academy team rows in missing-table (SB-1653, SB-1654). Empty
    # means none, unless academy_targets turns on every conference.
    academy_conferences: str = ""

    def academy_conference_set(self) -> frozenset[str]:
        """The Academy conferences named in academy_conferences."""
        return frozenset(
            c.strip() for c in self.academy_conferences.split(",") if c.strip()
        )

    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    # Publish to one named queue. The fanout default was removed in
    # SB-854: it was bound to matches.local, which had no consumer, so
    # every publish silently left a duplicate there. Set exchange_name
    # only if you deliberately want a fan-out.
    exchange_name: str = ""
    queue_name: str = DEFAULT_QUEUE
    league: str = "Homegrown"
    age_group: str = "U14"
    division: str = "Northeast"
    # Tournament event scrape (scrape-event, SB-1746). The source is swappable
    # because where MLS NEXT publishes a tournament is not known in advance:
    # "modular11" reads an event page, "assist" the Kitman feeds. event_id is
    # the modular11 event id or the assist feed key. The tournament id is
    # missing-table's and differs per environment, so it is configuration.
    event_source: str = "modular11"
    event_id: str = ""
    # Kept raw, as text. Every agent CronJob loads these settings from one
    # ConfigMap, so a bad value here (blank, 0, -3, "abc") must never fail
    # validation for the commands that do not look at it — league scraping
    # among them. Only scrape-event reads it, through
    # event_tournament_id_or_none(), and it is scrape-event that refuses to
    # publish without a real id.
    event_tournament_id: str = ""
    # Venue zone: modular11 prints wall-clock times with no zone.
    event_timezone: str = "America/Phoenix"

    @field_validator("event_tournament_id", mode="before")
    @classmethod
    def tournament_id_is_kept_as_text(cls, value: object) -> str:
        """Accept anything; never raise."""
        return "" if value is None else str(value).strip()

    def event_tournament_id_or_none(self, *, warn: bool = True) -> int | None:
        """The tournament id when it is a positive whole number, else None.

        Blank is simply unset. Anything else that is not a positive whole
        number is discarded with a warning that names the variable — unless
        the caller says it will report the value itself (``warn=False``).
        """
        raw = self.event_tournament_id
        if not raw:
            return None
        if _POSITIVE_INT.fullmatch(raw) and int(raw) >= 1:
            return int(raw)
        if not warn:
            return None
        structlog.get_logger().warning(
            "settings.event_tournament_id_ignored",
            variable="AGENT_EVENT_TOURNAMENT_ID",
            value=raw,
            reason="not a positive whole number; treated as unset",
        )
        return None

    missing_table_api_url: str = "http://localhost:8000"
    missing_table_api_key: str = ""
    dry_run: bool = False
    headless: bool = True
    json_logs: bool = False
    log_level: str = "info"

    # Run journal (cross-run memory) — S3 when a bucket is set, otherwise a
    # file. The cluster has no bucket and no AWS credentials, so the path is
    # the deployed backend; it points into the agent-state PVC that the agent
    # CronJob already mounts at /data/agent-state.
    journal_s3_bucket: str = ""
    journal_s3_key: str = "journal/latest.json"
    journal_path: str = "/data/agent-state/journal.json"

    # Schedule release watcher — shares the journal bucket. State must outlive
    # the pod because CronJob pods are ephemeral, and state that does not
    # survive would make the watcher re-announce a release on every single run.
    release_watch_s3_key: str = "release-watch/state.json"
    # Used when no journal bucket is configured. The cluster has no bucket and
    # no AWS credentials, so this is the deployed path — it points into the
    # agent-state PVC, mounted by the release-watch CronJob at /data/agent-state.
    release_watch_state_path: str = "/data/agent-state/release-watch.json"
    # Consecutive all-targets-failed runs before alerting. One failed run
    # against someone else's server is noise, not news.
    release_watch_failure_threshold: int = 3

    # Also watch the MLS NEXT Fest pages for the schedule (SB-1774). Probing
    # stops by itself once the release is announced.
    release_watch_fest: bool = True

    # Slack, for the one alert loud enough to go everywhere: the Fest schedule
    # release. Optional — blank token means Telegram and email only. The
    # channel is #sb-alerts, where the sbagent bot already posts.
    slack_bot_token: str = ""
    slack_alert_channel: str = "C0CDUDR6N6N"

    # Telegram notifications (run alerts and the daily digest)
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    # Names already alerted today, so an unresolved team name is reported once
    # a day rather than on every run until someone fixes it (SB-1679). On the
    # agent-state PVC, which every agent CronJob mounts read-write.
    alert_state_path: str = "/data/agent-state/alerts-sent.json"
    # The backfill's last findings: which official results were missing from
    # missing-table, and which it could not close (SB-1786). Read by the next
    # backfill, to escalate a gap that survived its own fix, and by the digest.
    completeness_state_path: str = "/data/agent-state/completeness.json"
    # One JSON change log per submitting reconcile run, <run>.json, so every
    # correction sent to MT can be traced afterwards (SB-1787).
    reconcile_log_dir: str = "/data/agent-state/reconcile"

    # Resend email fallback (used when Telegram fails)
    resend_api_key: str = ""
    # contact.missingtable.com, not the apex: Resend verifies an exact
    # domain, and only the subdomain is verified. Sending from
    # contact@missingtable.com was refused every time, so no alert email has
    # ever arrived (SB-1127).
    alert_email_from: str = "alerts@contact.missingtable.com"
    alert_email_to: str = "silverbeer.io@gmail.com"

    # Audit settings
    audit_season_start: str = "2026-02-01"  # Spring segment start date

    # Database (missing-table Supabase — used by trigger.sh post-run verification)
    db_host: str = "127.0.0.1"
    db_port: int = 54332
    db_user: str = "postgres"
    db_password: str = "postgres"
    db_name: str = "postgres"
