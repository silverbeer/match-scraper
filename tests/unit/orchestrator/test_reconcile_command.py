"""`match-scraper-agent reconcile`, with a fake feed, MT and queue (SB-1787)."""

from __future__ import annotations

import json
from datetime import date, datetime

import pytest
from freezegun import freeze_time
from typer.testing import CliRunner

from src.orchestrator import cli
from src.orchestrator.completeness import FeedEvent, FeedRead, MtReadError, SeasonRow
from src.scraper.models import Match

pytestmark = pytest.mark.usefixtures("no_network")

runner = CliRunner()

PLAYED = date(2026, 10, 4)
HOME = "Miami Futbol Academy Rush"
AWAY = "Sol SC Florida"


def _event(game_key: str, *, score=(3, 1), league="Homegrown", division="Florida"):
    match = Match(
        match_id=game_key,
        match_datetime=datetime(PLAYED.year, PLAYED.month, PLAYED.day, 10, 0),
        home_team=HOME,
        away_team=AWAY,
        home_score=score[0],
        away_score=score[1],
    )
    return FeedEvent(
        game_key=game_key,
        league=league,
        match_type="Flex" if league == "Flex" else "League",
        division=division,
        age_group="U15",
        match_date=PLAYED,
        completed=True,
        match=match,
    )


def _row(match_id: str, mt_id: int = 1, *, league="Homegrown", **overrides):
    fields = {
        "id": mt_id,
        "match_id": match_id,
        "match_date": PLAYED,
        "match_status": "completed",
        "home_team_name": HOME,
        "away_team_name": AWAY,
        "home_score": 2,
        "away_score": 1,
        "league": league,
        "match_type": "Flex" if league == "Flex" else "League",
    }
    fields.update(overrides)
    return SeasonRow(**fields)


class FakeQueue:
    instances: list[FakeQueue] = []
    reachable = True
    fail_on: set[str] = set()

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.submitted: list[dict] = []
        FakeQueue.instances.append(self)

    def check_connection(self):
        return FakeQueue.reachable

    def submit_match(self, match_data):
        if match_data["external_match_id"] in FakeQueue.fail_on:
            raise RuntimeError("broker said no")
        self.submitted.append(match_data)
        return "task-id"


class World:
    events: list[FeedEvent] = []
    rows: list[SeasonRow] = []
    alerts: list[str] = []
    mt_reads: list[dict] = []
    mt_fails = False
    feed_leagues: list[list[str]] = []


def _fake_read_feed(client, leagues):
    async def run():
        World.feed_leagues.append(list(leagues))
        events = [e for e in World.events if e.league in leagues]
        return FeedRead(events=events, game_keys=frozenset(e.game_key for e in events))

    return run()


def _fake_read_season(api_url, api_key, **kwargs):
    World.mt_reads.append(kwargs)
    if World.mt_fails:
        raise MtReadError("/api/agent/season-matches: 500")
    return [r for r in World.rows if r.league in kwargs["leagues"]]


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    World.events, World.rows, World.alerts = [], [], []
    World.mt_reads, World.mt_fails, World.feed_leagues = [], False, []
    FakeQueue.instances, FakeQueue.reachable, FakeQueue.fail_on = [], True, set()
    monkeypatch.setenv(
        "AGENT_RABBITMQ_URL", "amqp://u:s3cret-pw@mq.example.test:5672//"
    )
    monkeypatch.setenv("AGENT_QUEUE_NAME", "matches.prod")
    monkeypatch.setenv("AGENT_MISSING_TABLE_API_URL", "https://api.missingtable.com")
    monkeypatch.setenv("AGENT_RECONCILE_LOG_DIR", str(tmp_path / "reconcile"))
    monkeypatch.setenv("AGENT_ACADEMY_CONFERENCES", "New England")
    monkeypatch.delenv("AGENT_ACADEMY_TARGETS", raising=False)
    monkeypatch.delenv("AGENT_EXCHANGE_NAME", raising=False)
    monkeypatch.setattr("src.celery.queue_client.MatchQueueClient", FakeQueue)
    monkeypatch.setattr("src.orchestrator.completeness.read_feed", _fake_read_feed)
    monkeypatch.setattr("src.orchestrator.completeness.read_season", _fake_read_season)
    monkeypatch.setattr("src.orchestrator.tools.SEASON_START", date(2026, 8, 1))
    monkeypatch.setattr(
        cli,
        "_send_telegram_message",
        lambda settings, message, subject: World.alerts.append(message) or True,
    )
    with freeze_time("2026-11-26 12:00:00"):
        yield


def _run(*args):
    return runner.invoke(cli.app, ["reconcile", *args])


def _submit(*args):
    return _run("--submit", *args)


def _published() -> list[dict]:
    return [m for q in FakeQueue.instances for m in q.submitted]


def _logs(tmp_path) -> list[dict]:
    folder = tmp_path / "reconcile"
    if not folder.exists():
        return []
    return [json.loads(p.read_text()) for p in sorted(folder.glob("*.json"))]


class TestDryRun:
    def test_never_publishes_never_alerts_never_logs(self, tmp_path):
        World.events = [_event("1")]
        World.rows = [_row("1")]

        result = _run()

        assert result.exit_code == 10, result.output
        assert FakeQueue.instances == []
        assert World.alerts == []
        assert _logs(tmp_path) == []
        assert "DRY RUN" in result.output
        assert "Dry run: 1 would be sent with --submit." in result.output

    def test_prints_the_banner_one_line_per_change_and_totals(self):
        World.events = [_event("1"), _event("2")]
        World.rows = [_row("1", 1), _row("2", 2, score_locked=True)]

        result = _run()

        assert "MT API: api.missingtable.com" in result.output
        assert "broker mq.example.test:5672, queue 'matches.prod'" in result.output
        assert "s3cret-pw" not in result.output
        assert "1 | score | score: 2-1 -> 3-1 | -" in result.output
        assert "2 | score | score: 2-1 -> 3-1 | locked" in result.output
        assert "score      1 to send     1 report only" in result.output

    def test_nothing_differs_exits_clean(self):
        World.events = [_event("1", score=(2, 1))]
        World.rows = [_row("1")]

        result = _run()

        assert result.exit_code == 0, result.output
        assert "Nothing differs." in result.output

    def test_over_max_changes_warns(self):
        World.events = [_event(str(i)) for i in range(3)]
        World.rows = [_row(str(i), i) for i in range(3)]

        result = _run("--max-changes", "2")

        assert result.exit_code == 10
        assert "--submit would refuse" in result.output
        assert FakeQueue.instances == []

    def test_reads_every_league_scraped(self):
        _run()
        assert World.feed_leagues == [["Homegrown", "Flex", "Academy"]]

    def test_academy_is_left_out_when_no_conference_is_scraped(self, monkeypatch):
        monkeypatch.setenv("AGENT_ACADEMY_CONFERENCES", "")
        _run()
        assert World.feed_leagues == [["Homegrown", "Flex"]]

    def test_academy_asked_for_but_not_scraped_is_refused(self, monkeypatch):
        monkeypatch.setenv("AGENT_ACADEMY_CONFERENCES", "")
        result = _run("--league", "Academy")
        assert result.exit_code == 1

    def test_only_the_conferences_mt_scrapes_are_reconciled(self):
        World.events = [
            _event("1", league="Academy", division="New England"),
            _event("2", league="Academy", division="Mid-Atlantic"),
        ]
        World.rows = [_row("1", 1, league="Academy"), _row("2", 2, league="Academy")]

        result = _run("--league", "Academy")

        assert "1 | score" in result.output
        assert "2 | score" not in result.output

    def test_only(self):
        World.events = [_event("1")]
        World.rows = [_row("1")]

        result = _run("--only", "redate,status")

        assert result.exit_code == 0, result.output
        assert "1 | score" not in result.output

    def test_only_also_narrows_voided_and_mt_only(self):
        World.events = [
            _event("1"),
            _event("2").model_copy(update={"completed": False}),
        ]
        World.rows = [_row("1", 1), _row("2", 2), _row("9", 9)]

        narrowed = _run("--only", "score")
        assert "1 | score" in narrowed.output
        assert "2 | voided" not in narrowed.output
        assert "MT results the feed does not have" not in narrowed.output

        full = _run()
        assert "2 | voided" in full.output
        assert "MT results the feed does not have (never deleted): 1" in full.output

        asked = _run("--only", "voided,mt-only")
        assert "1 | score" not in asked.output
        assert "2 | voided" in asked.output
        assert "MT results the feed does not have (never deleted): 1" in asked.output

    def test_an_unknown_class_is_refused(self):
        assert _run("--only", "everything").exit_code == 1

    def test_an_unknown_league_is_refused(self):
        assert _run("--league", "Pathway").exit_code == 1


class TestRefusals:
    def test_mt_read_failure_sends_nothing_and_alerts(self, tmp_path):
        World.events = [_event("1")]
        World.mt_fails = True

        result = _submit()

        assert result.exit_code == 1
        assert _published() == []
        assert len(World.alerts) == 1
        assert "could not run" in World.alerts[0]

    def test_mt_read_failure_on_a_dry_run_does_not_alert(self):
        World.mt_fails = True
        result = _run()
        assert result.exit_code == 1
        assert World.alerts == []

    def test_max_changes_refuses_the_whole_batch(self, tmp_path):
        World.events = [_event(str(i)) for i in range(3)]
        World.rows = [_row(str(i), i) for i in range(3)]

        result = _submit("--max-changes", "2")

        assert result.exit_code == 1
        assert _published() == []
        assert len(World.alerts) == 1
        (log,) = _logs(tmp_path)
        assert "more than --max-changes 2" in log["refused"]
        assert all(not c["sent"] for c in log["changes"])

    def test_a_publish_guard_mismatch_reads_nothing(self, monkeypatch):
        monkeypatch.setenv("AGENT_MISSING_TABLE_API_URL", "http://localhost:8000")
        result = _submit()
        assert result.exit_code == 1
        assert "Refusing to publish" in result.output
        assert World.mt_reads == []

    def test_an_unreachable_broker_stops_the_run(self):
        FakeQueue.reachable = False
        result = _submit()
        assert result.exit_code == 1
        assert World.mt_reads == []


class TestSubmit:
    def test_sends_logs_and_alerts(self, tmp_path):
        World.events = [_event("1"), _event("2")]
        World.rows = [
            _row("1", 1, entered_by_person=True),
            _row("2", 2, score_locked=True),
        ]

        result = _submit()

        assert result.exit_code == 10, result.output
        (sent,) = _published()
        assert sent["external_match_id"] == "1"
        assert (sent["home_score"], sent["away_score"]) == (3, 1)
        assert sent["match_status"] == "completed"
        assert "Overrides a person's score" in result.output

        (log,) = _logs(tmp_path)
        assert log["sent"] == ["1"]
        assert {c["game_key"]: c["sent"] for c in log["changes"]} == {
            "1": True,
            "2": False,
        }
        assert "s3cret-pw" not in json.dumps(log)

        (alert,) = World.alerts
        assert "Overrides a person" in alert

    def test_reads_mt_from_since_to_yesterday(self):
        World.events = [_event("1")]
        World.rows = [_row("1")]

        _submit("--since", "2026-09-01")

        (read,) = World.mt_reads
        assert read["start"] == date(2026, 9, 1)
        assert read["end"] == date(2026, 11, 25)
        assert read["season"] == "2026-2027"

    def test_report_only_findings_still_alert(self, tmp_path):
        World.events = [_event("1")]
        World.rows = [_row("1", score_locked=True)]

        result = _submit()

        assert result.exit_code == 10
        assert _published() == []
        assert len(World.alerts) == 1
        assert len(_logs(tmp_path)) == 1

    def test_every_send_failing_exits_1(self):
        World.events = [_event("1")]
        World.rows = [_row("1")]
        FakeQueue.fail_on = {"1"}

        result = _submit()

        assert result.exit_code == 1
