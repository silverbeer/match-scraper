"""`match-scraper-agent backfill`, with a fake feed, MT and queue (SB-1786)."""

from __future__ import annotations

import json
from datetime import date, datetime

import pytest
from freezegun import freeze_time
from typer.testing import CliRunner

from src.orchestrator import cli
from src.orchestrator.completeness import FeedEvent, FeedRead, MtReadError, MtRow
from src.scraper.models import Match

pytestmark = pytest.mark.usefixtures("no_network")

runner = CliRunner()

PLACEHOLDER = date(2027, 6, 8)


def _event(
    game_key: str,
    *,
    league="Flex",
    division="Southeast",
    completed=True,
    day=date(2026, 9, 13),
    on_placeholder=False,
):
    match = Match(
        match_id=game_key,
        match_datetime=datetime(day.year, day.month, day.day, 10, 0),
        home_team="Queen City Mutiny FC",
        away_team="Nashville United Soccer Academy (NUSA Next)",
        home_score=1 if completed else None,
        away_score=1 if completed else None,
        home_penalty_score=4 if completed else None,
        away_penalty_score=2 if completed else None,
        postponed=on_placeholder,
    )
    return FeedEvent(
        game_key=game_key,
        league=league,
        match_type="Flex" if league == "Flex" else "League",
        division=division,
        age_group="U16",
        match_date=day,
        completed=completed,
        on_placeholder=on_placeholder,
        match=match,
    )


def _row(match_id: str, mt_id: int = 1) -> MtRow:
    return MtRow(
        id=mt_id,
        match_id=match_id,
        match_date=date(2026, 9, 13),
        match_status="completed",
        match_type_name="Flex",
        league_name="Flex",
    )


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
        # The worker "lands" it, so the confirming re-read finds it.
        World.landed.add(match_data["external_match_id"])
        return "task-id"


class World:
    """What the fake feed and the fake MT hold."""

    events: list[FeedEvent] = []
    rows: list[MtRow] = []
    landed: set[str] = set()
    land_on_submit = True
    alerts: list[str] = []
    mt_reads = 0
    # Raise on these reads (1-based): an MT outage.
    fail_reads: set[int] = set()


def _fake_read_feed(client, leagues):
    async def run():
        events = [e for e in World.events if e.league in leagues]
        return FeedRead(
            events=events,
            placeholders=frozenset({PLACEHOLDER}),
            game_keys=frozenset(e.game_key for e in events),
        )

    return run()


def _fake_fetch(api_url, api_key, pages, expect_days=(), client=None):
    World.mt_reads += 1
    if World.mt_reads in World.fail_reads:
        raise MtReadError("/api/matches returned no rows")
    landed = World.landed if World.land_on_submit else set()
    return World.rows + [_row(key, 1000 + i) for i, key in enumerate(sorted(landed))]


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    World.events, World.rows, World.landed = [], [], set()
    World.land_on_submit, World.alerts, World.mt_reads = True, [], 0
    World.fail_reads = set()
    FakeQueue.instances, FakeQueue.reachable, FakeQueue.fail_on = [], True, set()
    monkeypatch.setenv(
        "AGENT_RABBITMQ_URL", "amqp://u:s3cret-pw@mq.example.test:5672//"
    )
    monkeypatch.setenv("AGENT_QUEUE_NAME", "matches.prod")
    monkeypatch.setenv("AGENT_MISSING_TABLE_API_URL", "https://api.missingtable.com")
    monkeypatch.setenv("AGENT_COMPLETENESS_STATE_PATH", str(tmp_path / "gaps.json"))
    monkeypatch.delenv("AGENT_EXCHANGE_NAME", raising=False)
    monkeypatch.setattr("src.celery.queue_client.MatchQueueClient", FakeQueue)
    monkeypatch.setattr("src.orchestrator.completeness.read_feed", _fake_read_feed)
    monkeypatch.setattr("src.orchestrator.completeness.fetch_mt_rows", _fake_fetch)
    # The season, pinned, so the default window does not move with the clock.
    monkeypatch.setattr("src.orchestrator.tools.SEASON_START", date(2026, 8, 1))
    monkeypatch.setattr(
        cli,
        "_send_telegram_message",
        lambda settings, message, subject: World.alerts.append(message) or True,
    )
    with freeze_time("2026-11-26 12:00:00"):
        yield


def _run(*args):
    """The default, full-scope run — the one the CronJob makes."""
    return runner.invoke(cli.app, ["backfill", *args])


def _submit(*args):
    return _run("--submit", "--confirm-wait", "0", *args)


def _published() -> list[dict]:
    return [m for q in FakeQueue.instances for m in q.submitted]


def _state(tmp_path) -> dict:
    return json.loads((tmp_path / "gaps.json").read_text())


class TestDryRun:
    def test_never_publishes_and_never_alerts(self, tmp_path):
        World.events = [_event("26329"), _event("26330")]

        result = _run()

        assert result.exit_code == 10, result.output
        assert FakeQueue.instances == []
        assert World.alerts == []
        assert not (tmp_path / "gaps.json").exists()
        assert "DRY RUN" in result.output

    def test_prints_the_target_counts_and_one_line_per_gap(self):
        World.events = [_event("26329"), _event("26330"), _event("1", completed=False)]
        World.rows = [_row("26330")]

        result = _run()

        assert "MT API: api.missingtable.com" in result.output
        assert "broker mq.example.test:5672, queue 'matches.prod'" in result.output
        assert "s3cret-pw" not in result.output
        assert "Official results not in MT: 1" in result.output
        assert "1  Flex Southeast U16" in result.output
        assert "26329  2026-09-13  Flex Southeast U16" in result.output
        assert "1-1 (p 4-2)  action=create" in result.output
        assert "26330  2026" not in result.output

    def test_nothing_missing_exits_clean(self):
        World.events = [_event("26329")]
        World.rows = [_row("26329")]

        result = _run()

        assert result.exit_code == 0, result.output
        assert "Nothing missing." in result.output

    def test_league_filter(self):
        World.events = [_event("26329"), _event("30000", league="Homegrown")]

        result = _run("--league", "Homegrown")

        assert "30000" in result.output
        assert "26329" not in result.output

    def test_an_unknown_league_is_refused(self):
        result = _run("--league", "Academy")
        assert result.exit_code == 1


class TestPublishGuard:
    def test_a_prod_queue_with_a_local_api_is_refused_before_anything(
        self, monkeypatch
    ):
        monkeypatch.setenv("AGENT_MISSING_TABLE_API_URL", "http://localhost:8000")
        World.events = [_event("26329")]

        result = _run("--submit")

        assert result.exit_code == 1
        assert "Refusing to publish" in result.output
        assert FakeQueue.instances == []
        assert World.mt_reads == 0

    def test_a_prod_api_with_a_local_queue_is_refused(self, monkeypatch):
        monkeypatch.setenv("AGENT_QUEUE_NAME", "matches.local")

        result = _run("--submit")

        assert result.exit_code == 1
        assert FakeQueue.instances == []

    def test_an_unreachable_broker_stops_the_run(self):
        FakeQueue.reachable = False

        result = _submit()

        assert result.exit_code == 1
        assert World.mt_reads == 0


class TestSubmit:
    def test_sends_each_gap_through_the_shared_builder(self):
        World.events = [_event("26329"), _event("26330")]
        World.rows = [_row("26330")]

        result = _submit()

        assert result.exit_code == 10, result.output
        (sent,) = _published()
        assert sent["external_match_id"] == "26329"
        assert sent["match_type"] == "Flex"
        assert sent["league"] == "Flex"
        assert sent["division"] == "Southeast"
        assert (sent["home_penalty_score"], sent["away_penalty_score"]) == (4, 2)
        assert "Sent but still not in MT: 0" in result.output

    def test_alerts_with_counts_and_game_keys(self):
        World.events = [_event("26329")]

        _submit()

        (alert,) = World.alerts
        assert "were not in MT" in alert
        assert "26329" in alert
        assert "Southeast U16: 1" in alert

    def test_records_state_for_the_next_run_and_the_digest(self, tmp_path):
        World.events = [_event("26329")]
        World.land_on_submit = False

        _submit()

        state = json.loads((tmp_path / "gaps.json").read_text())
        assert state["found"] == ["26329"]
        assert state["still_missing"] == ["26329"]

    def test_a_gap_missing_on_two_runs_in_a_row_is_louder(self):
        World.events = [_event("26329")]
        World.land_on_submit = False

        _submit()
        _submit()

        first, second = World.alerts
        assert "still not in MT after a backfill" not in first
        assert "still not in MT after a backfill" in second

    def test_a_clean_run_clears_the_state(self, tmp_path):
        World.events = [_event("26329")]
        World.rows = [_row("26329")]

        result = _submit()

        assert result.exit_code == 0
        assert World.alerts == []
        state = json.loads((tmp_path / "gaps.json").read_text())
        assert state["still_missing"] == []

    def test_an_mt_only_result_is_listed_never_deleted(self):
        World.events = [_event("26329")]
        World.rows = [_row("26329"), _row("77777", mt_id=2)]

        result = _submit()

        assert "MT results the feed does not have (never deleted): 1" in result.output
        assert "77777" in result.output
        assert _published() == []


class TestMaxChanges:
    def test_over_the_limit_publishes_nothing(self):
        World.events = [_event(str(26000 + i)) for i in range(3)]

        result = _submit("--max-changes", "2")

        assert result.exit_code == 1
        assert _published() == []
        assert "more than --max-changes 2" in result.output
        (alert,) = World.alerts
        assert "Not sent" in alert

    def test_at_the_limit_publishes(self):
        World.events = [_event(str(26000 + i)) for i in range(2)]

        result = _submit("--max-changes", "2")

        assert result.exit_code == 10, result.output
        assert len(_published()) == 2

    def test_a_dry_run_says_submit_would_refuse(self):
        World.events = [_event(str(26000 + i)) for i in range(3)]

        result = _run("--max-changes", "2")

        assert result.exit_code == 10
        assert "--submit would refuse" in result.output
        assert FakeQueue.instances == []


class TestNeedsAPerson:
    def test_a_placeholder_result_is_listed_not_sent(self, tmp_path):
        World.events = [
            _event("26329"),
            _event("28249", day=PLACEHOLDER, on_placeholder=True),
        ]

        result = _submit()

        assert [m["external_match_id"] for m in _published()] == ["26329"]
        assert "needs a person: result on placeholder date" in result.output
        (alert,) = World.alerts
        assert "Needs a person, result on placeholder date" in alert
        assert "28249" in alert
        state = _state(tmp_path)
        assert state["submitted"] == ["26329"]
        assert state["still_missing"] == ["28249"]

    def test_a_placeholder_result_is_listed_in_the_dry_run(self):
        World.events = [_event("28249", day=PLACEHOLDER, on_placeholder=True)]

        result = _run()

        assert "Needs a person: result on placeholder date: 1" in result.output
        assert "Dry run: 0 would be sent" in result.output

    def test_a_result_with_no_bracket_is_listed_not_sent(self, tmp_path):
        World.events = [_event("26329", division=None)]

        result = _submit()

        assert _published() == []
        assert "not sendable: no bracket" in result.output
        (alert,) = World.alerts
        assert "Not sendable, no bracket" in alert
        assert _state(tmp_path)["submitted"] == []


class TestRepeats:
    def test_only_what_was_sent_last_run_can_repeat(self):
        # Never sent (no bracket), so missing again is not "a send that did
        # not land".
        World.events = [_event("26329", division=None)]

        _submit()
        _submit()

        assert all("after a backfill" not in alert for alert in World.alerts)

    def test_a_failed_send_is_reported_and_does_not_repeat(self, tmp_path):
        World.events = [_event("26329"), _event("26330")]
        FakeQueue.fail_on = {"26330"}

        result = _submit()

        assert "26330  send failed" in result.output
        (alert,) = World.alerts
        assert "Send failed" in alert
        state = _state(tmp_path)
        assert state["submitted"] == ["26329"]
        assert state["still_missing"] == ["26330"]

        _submit()
        assert "after a backfill" not in World.alerts[1]

    def test_a_narrowed_run_writes_no_state(self, tmp_path):
        World.events = [_event("26329")]
        World.land_on_submit = False

        _submit("--league", "Flex")
        _submit("--from", "2026-09-01")

        assert not (tmp_path / "gaps.json").exists()
        assert len(_published()) == 2


class TestMtOutage:
    def test_a_failed_read_sends_nothing_and_alerts(self):
        World.events = [_event("26329")]
        World.fail_reads = {1}

        result = _submit()

        assert result.exit_code == 1
        assert _published() == []
        (alert,) = World.alerts
        assert "could not read missing" in alert

    def test_a_failed_confirm_is_not_everything_missing(self, tmp_path):
        World.events = [_event("26329")]
        World.fail_reads = {2}

        result = _submit()

        assert "Could not re-read missing-table to confirm" in result.output
        (alert,) = World.alerts
        assert "Could not re" in alert
        assert "still not in MT" not in alert

    def test_a_confirm_that_recovers_is_used(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda seconds: None)
        World.events = [_event("26329")]
        World.fail_reads = {2}

        result = _submit("--confirm-wait", "60")

        assert "Sent but still not in MT: 0" in result.output
