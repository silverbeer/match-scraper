"""`match-scraper-agent scrape-event`, with a fake source and a fake queue (SB-1746)."""

import json
from datetime import date, datetime

import pytest
from freezegun import freeze_time
from typer.testing import CliRunner

from src.models.tournament import TournamentContext, TournamentMatch
from src.orchestrator import cli

pytestmark = pytest.mark.usefixtures("no_network")

runner = CliRunner()


def _match(match_id="16416", **overrides) -> TournamentMatch:
    fields = {
        "source_match_id": match_id,
        "age_group": "U15",
        "home_team": "Miami Futbol Academy Rush",
        "away_team": "The Football Academy",
        "kickoff_local": datetime(2026, 12, 5, 18, 0),
        "competition": "GA Cup Qualifier",
        "source_division": "Playoff",
        "source_round_label": "Round of 16",
    }
    fields.update(overrides)
    return TournamentMatch(**fields)


def _group_match(match_id="16044", **overrides) -> TournamentMatch:
    fields = {
        "age_group": "U13",
        "home_team": "Sacramento United",
        "away_team": "Alexandria SA",
        "kickoff_local": datetime(2026, 12, 4, 7, 30),
        "competition": "HD Group Play",
        "source_division": "E",
        "source_round_label": "Group Play",
    }
    fields.update(overrides)
    return _match(match_id, **fields)


class FakeSource:
    name = "fake"
    id_prefix = "m11-75-"

    def __init__(self, matches, failures=None, unmapped=None):
        self.matches = matches
        self.failures = failures or {}
        self.unmapped = unmapped or {}
        self.asked: tuple | None = None

    async def fetch(self, age_groups, start, end):
        self.asked = (list(age_groups), start, end)
        return list(self.matches)


class FakeQueue:
    """Stands in for MatchQueueClient: records, never connects."""

    instances: list["FakeQueue"] = []
    fail_on: set[str] = set()
    fail_all = False
    reachable = True

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.submitted: list[dict] = []
        FakeQueue.instances.append(self)

    def check_connection(self):
        return FakeQueue.reachable

    def submit_match(self, match_data):
        if FakeQueue.fail_all or match_data["external_match_id"] in FakeQueue.fail_on:
            raise RuntimeError("broker unreachable")
        self.submitted.append(match_data)
        return "task-id"


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    for name in (
        "AGENT_EVENT_SOURCE",
        "AGENT_EVENT_ID",
        "AGENT_EVENT_TOURNAMENT_ID",
        "AGENT_EVENT_TIMEZONE",
    ):
        monkeypatch.delenv(name, raising=False)
    FakeQueue.instances = []
    FakeQueue.fail_on = set()
    FakeQueue.fail_all = False
    FakeQueue.reachable = True
    # A broker with credentials in it, so a leak would show.
    monkeypatch.setenv(
        "AGENT_RABBITMQ_URL", "amqp://fest-user:s3cret-pw@mq.example.test:5672//"
    )
    monkeypatch.delenv("AGENT_QUEUE_NAME", raising=False)
    monkeypatch.delenv("AGENT_EXCHANGE_NAME", raising=False)
    monkeypatch.setattr("src.celery.queue_client.MatchQueueClient", FakeQueue)


@pytest.fixture
def use_source(monkeypatch):
    built: list[dict] = []

    def install(source: FakeSource) -> list[dict]:
        def factory(name, event, **kwargs):
            built.append({"source": name, "event": event, **kwargs})
            return source

        monkeypatch.setattr(cli, "_event_source", factory)
        return built

    return install


def _run(*args):
    return runner.invoke(cli.app, ["scrape-event", *args])


def _published() -> list[dict]:
    return [m for queue in FakeQueue.instances for m in queue.submitted]


class TestDryRun:
    def test_nothing_is_published(self, use_source):
        use_source(FakeSource([_match(), _group_match()]))

        result = _run("--event", "75", "--tournament-id", "12")

        assert result.exit_code == 0, result.output
        assert FakeQueue.instances == []
        assert "DRY RUN" in result.output

    def test_the_summary(self, use_source):
        use_source(
            FakeSource(
                [
                    _match(
                        home_score=1,
                        away_score=1,
                        home_penalty_score=4,
                        away_penalty_score=3,
                    ),
                    _group_match(),
                    _group_match("16045", home_team="Alexandria SA", away_team="X FC"),
                ]
            )
        )

        result = _run("--event", "75")

        assert result.exit_code == 0, result.output
        lines = [" ".join(line.split()) for line in result.output.splitlines()]
        assert "Matches: 3" in lines
        assert "U13 2" in lines
        assert "U15 1" in lines
        assert "group_stage 2" in lines
        assert "round_of_16 1" in lines
        assert "Decided on penalties: 1" in lines
        # Sacramento United, Alexandria SA, X FC and the two U15 clubs.
        assert "Distinct team names: 5" in lines
        assert "Unmapped values: none" in lines
        assert "No tournament id set: messages cannot be submitted yet." in lines

    def test_all_six_age_groups_and_the_season_by_default(self, use_source):
        source = FakeSource([])
        use_source(source)

        with freeze_time("2026-11-22"):
            result = _run("--event", "75")

        assert result.exit_code == 0, result.output
        assert source.asked == (
            ["U13", "U14", "U15", "U16", "U17", "U19"],
            date(2026, 8, 1),
            date(2027, 7, 15),
        )

    def test_age_groups_and_window_can_be_narrowed(self, use_source):
        source = FakeSource([])
        use_source(source)

        _run("--event", "75", "-a", "U15", "-a", "U16", "--from", "2026-12-04")

        assert source.asked[0] == ["U15", "U16"]
        assert source.asked[1] == date(2026, 12, 4)

    def test_a_match_outside_the_window_is_not_sent(self, use_source):
        use_source(FakeSource([_match(), _group_match()]))
        result = _run("--event", "75", "--from", "2026-12-05", "--to", "2026-12-05")
        assert "Matches: 1" in result.output

    def test_json_prints_the_messages(self, use_source):
        use_source(FakeSource([_group_match(home_score=0, away_score=2)]))

        result = _run("--event", "75", "--tournament-id", "12", "--json")

        assert result.exit_code == 0, result.output
        (message,) = json.loads(result.stdout)
        assert message["external_match_id"] == "m11-75-16044"
        assert message["tournament_id"] == 12
        assert message["match_type"] == "Tournament"
        assert message["competition"] == "HD Group Play"
        assert message["tournament_group"] == "E"
        assert message["tournament_round"] == "group_stage"
        assert message["league"] == "Homegrown"
        assert message["division"] is None
        assert message["scheduled_kickoff"] == "2026-12-04T14:30:00Z"

    def test_json_without_a_tournament_id_shows_none_not_a_stand_in(self, use_source):
        use_source(FakeSource([_group_match()]))
        result = _run("--event", "75", "--json")
        assert json.loads(result.stdout)[0]["tournament_id"] is None

    def test_placeholder_fixtures_are_skipped_and_counted(self, use_source):
        use_source(
            FakeSource([_group_match(), _match(home_team="TBD", away_team="TBD")])
        )
        result = _run("--event", "75")
        assert result.exit_code == 0, result.output
        assert "Matches: 1" in result.output
        assert "skipped: opponent not decided: 1" in result.output


class TestSources:
    def test_modular11_is_the_default(self, use_source):
        built = use_source(FakeSource([]))
        _run("--event", "75", "--delay", "2.5")
        assert built[0]["source"] == "modular11"
        assert built[0]["event"] == "75"
        assert built[0]["delay"] == 2.5
        assert built[0]["timezone_name"] == "America/Phoenix"

    def test_the_source_and_event_can_come_from_settings(self, use_source, monkeypatch):
        monkeypatch.setenv("AGENT_EVENT_SOURCE", "assist")
        monkeypatch.setenv("AGENT_EVENT_ID", "mls-next-fest-26-27")
        built = use_source(FakeSource([]))

        result = _run()

        assert result.exit_code == 0, result.output
        assert built[0]["source"] == "assist"
        assert built[0]["event"] == "mls-next-fest-26-27"

    def test_the_flag_beats_the_setting(self, use_source, monkeypatch):
        monkeypatch.setenv("AGENT_EVENT_SOURCE", "assist")
        built = use_source(FakeSource([]))
        _run("--source", "modular11", "--event", "75")
        assert built[0]["source"] == "modular11"

    def test_the_real_factory_builds_each_adapter(self):
        from src.scraper.tournament.assist_event import AssistEventSource
        from src.scraper.tournament.modular11_event import Modular11EventSource

        kwargs = {"delay": 1.0, "save_raw": None, "timezone_name": "America/Phoenix"}
        assert isinstance(
            cli._event_source("modular11", "75", **kwargs), Modular11EventSource
        )
        assert isinstance(
            cli._event_source("assist", "some-key", **kwargs), AssistEventSource
        )

    def test_an_unknown_source_cannot_run(self, use_source):
        use_source(FakeSource([]))
        result = _run("--source", "gotsport", "--event", "75")
        assert result.exit_code == 1
        assert "Unknown source" in result.output

    def test_no_event_cannot_run(self, use_source):
        use_source(FakeSource([]))
        result = _run()
        assert result.exit_code == 1
        assert "--event" in result.output

    def test_an_unknown_age_group_cannot_run(self, use_source):
        use_source(FakeSource([]))
        assert _run("--event", "75", "-a", "U12").exit_code == 1

    def test_a_bad_date_cannot_run(self, use_source):
        use_source(FakeSource([]))
        assert _run("--event", "75", "--from", "12/04/2026").exit_code == 1

    def test_from_after_to_cannot_run(self, use_source):
        source = FakeSource([])
        use_source(source)
        result = _run("--event", "75", "--from", "2026-12-10", "--to", "2026-12-04")
        assert result.exit_code == 1
        assert "later than" in result.output
        assert source.asked is None

    def test_a_blank_tournament_id_setting_is_unset_not_a_crash(
        self, use_source, monkeypatch
    ):
        # The ConfigMap is shared by every agent CronJob.
        monkeypatch.setenv("AGENT_EVENT_TOURNAMENT_ID", "")
        use_source(FakeSource([]))
        assert _run("--event", "75").exit_code == 0


class TestSubmit:
    def test_submit_without_a_tournament_id_is_refused(self, use_source):
        source = FakeSource([_match()])
        use_source(source)

        result = _run("--event", "75", "--submit")

        assert result.exit_code == 1
        assert "--tournament-id" in result.output
        assert source.asked is None  # refused before anything was fetched
        assert FakeQueue.instances == []

    def test_submit_publishes_every_message(self, use_source):
        use_source(FakeSource([_match(), _group_match()]))

        result = _run("--event", "75", "--tournament-id", "12", "--submit")

        assert result.exit_code == 0, result.output
        assert [m["external_match_id"] for m in _published()] == [
            "m11-75-16416",
            "m11-75-16044",
        ]
        assert {m["tournament_id"] for m in _published()} == {12}
        assert "Submitted 2 matches to queue (0 errors)." in result.output

    def test_the_tournament_id_can_come_from_settings(self, use_source, monkeypatch):
        monkeypatch.setenv("AGENT_EVENT_TOURNAMENT_ID", "31")
        use_source(FakeSource([_match()]))

        result = _run("--event", "75", "--submit")

        assert result.exit_code == 0, result.output
        assert _published()[0]["tournament_id"] == 31

    def test_two_runs_give_identical_ids(self, use_source):
        use_source(FakeSource([_match(), _group_match()]))

        _run("--event", "75", "--tournament-id", "12", "--submit")
        _run("--event", "75", "--tournament-id", "12", "--submit")

        first, second = (queue.submitted for queue in FakeQueue.instances)
        assert first == second
        ids = [m["external_match_id"] for m in first]
        assert len(ids) == len(set(ids))

    def test_a_changed_score_keeps_the_id(self, use_source):
        # What makes a rerun an update on missing-table's side: it upserts on
        # external_match_id.
        use_source(FakeSource([_match()]))
        with freeze_time("2026-12-06T02:00:00Z"):
            _run("--event", "75", "--tournament-id", "12", "--submit")
        use_source(
            FakeSource(
                [
                    _match(
                        home_score=1,
                        away_score=1,
                        home_penalty_score=4,
                        away_penalty_score=3,
                    )
                ]
            )
        )
        with freeze_time("2026-12-06T04:00:00Z"):
            _run("--event", "75", "--tournament-id", "12", "--submit")

        before, after = _published()
        assert before["external_match_id"] == after["external_match_id"]
        assert (before["home_score"], before["match_status"]) == (None, "tbd")
        assert (after["home_score"], after["away_score"]) == (1, 1)
        assert (after["home_penalty_score"], after["away_penalty_score"]) == (4, 3)
        assert after["match_status"] == "completed"

    def test_placeholders_are_not_published(self, use_source):
        use_source(FakeSource([_match(home_team="TBD", away_team="TBD")]))
        result = _run("--event", "75", "--tournament-id", "12", "--submit")
        assert result.exit_code == 0, result.output
        assert _published() == []


# What a stray value in the shared ConfigMap can look like.
BAD_IDS = ["0", "-3", "abc", ""]


class TestTournamentId:
    """Only a real, positive id is ever published (0 once meant "use 1")."""

    @pytest.mark.parametrize("value", BAD_IDS)
    def test_settings_load_whatever_the_value(self, monkeypatch, value):
        from src.orchestrator.settings import AgentSettings

        monkeypatch.setenv("AGENT_EVENT_TOURNAMENT_ID", value)
        settings = AgentSettings()
        assert settings.event_tournament_id == value.strip()
        assert settings.event_tournament_id_or_none() is None

    @pytest.mark.parametrize("value", ["0", "-3", "abc"])
    def test_a_discarded_value_is_warned_about_by_name(self, monkeypatch, value):
        import structlog
        from structlog.testing import capture_logs

        from src.orchestrator.settings import AgentSettings

        monkeypatch.setenv("AGENT_EVENT_TOURNAMENT_ID", value)
        structlog.reset_defaults()
        with capture_logs() as logs:
            assert AgentSettings().event_tournament_id_or_none() is None
        (entry,) = logs
        assert entry["log_level"] == "warning"
        assert entry["variable"] == "AGENT_EVENT_TOURNAMENT_ID"
        assert entry["value"] == value

    def test_blank_is_unset_without_a_warning(self, monkeypatch):
        from structlog.testing import capture_logs

        from src.orchestrator.settings import AgentSettings

        monkeypatch.setenv("AGENT_EVENT_TOURNAMENT_ID", "")
        with capture_logs() as logs:
            assert AgentSettings().event_tournament_id_or_none() is None
        assert logs == []

    @pytest.mark.parametrize("value", ["1", "31", " 12 "])
    def test_a_positive_whole_number_is_the_id(self, monkeypatch, value):
        from src.orchestrator.settings import AgentSettings

        monkeypatch.setenv("AGENT_EVENT_TOURNAMENT_ID", value)
        assert AgentSettings().event_tournament_id_or_none() == int(value)

    @pytest.mark.parametrize("value", BAD_IDS)
    def test_another_agent_command_is_unaffected(self, monkeypatch, value):
        # The ConfigMap is shared: a bad Fest id must not take league
        # scraping, the watchdog or anything else down with it.
        from datetime import UTC, timedelta

        from src.orchestrator.journal import RunJournal

        monkeypatch.setenv("AGENT_EVENT_TOURNAMENT_ID", value)
        fresh = RunJournal(
            timestamp=(datetime.now(tz=UTC) - timedelta(hours=1)).isoformat(),
            run_id="abc123def456",
        )
        monkeypatch.setattr(
            "src.orchestrator.journal.read_journal", lambda *a, **k: fresh
        )
        monkeypatch.setattr(cli, "_send_telegram_message", lambda *a, **k: None)

        result = runner.invoke(cli.app, ["watchdog", "--dry-run"])

        assert result.exit_code == 0, result.output
        assert result.exception is None

    @pytest.mark.parametrize("value", BAD_IDS)
    def test_submit_is_refused_and_nothing_is_published(
        self, use_source, monkeypatch, value
    ):
        monkeypatch.setenv("AGENT_EVENT_TOURNAMENT_ID", value)
        source = FakeSource([_match()])
        use_source(source)

        result = _run("--event", "75", "--submit")

        assert result.exit_code == 1
        assert source.asked is None  # nothing fetched either
        assert FakeQueue.instances == []
        assert _published() == []
        if value.strip():
            # Says what it received.
            assert f"AGENT_EVENT_TOURNAMENT_ID is {value!r}" in result.output
        else:
            assert "--tournament-id" in result.output

    @pytest.mark.parametrize("value", BAD_IDS)
    def test_a_dry_run_still_works(self, use_source, monkeypatch, value):
        monkeypatch.setenv("AGENT_EVENT_TOURNAMENT_ID", value)
        use_source(FakeSource([_match()]))

        result = _run("--event", "75", "--json")

        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)[0]["tournament_id"] is None
        assert "cannot be submitted" in result.stderr
        if value.strip():
            assert f"AGENT_EVENT_TOURNAMENT_ID is {value!r}" in result.stderr

    @pytest.mark.parametrize("value", ["0", "-3", "abc"])
    def test_a_good_option_overrides_a_bad_setting(
        self, use_source, monkeypatch, value
    ):
        monkeypatch.setenv("AGENT_EVENT_TOURNAMENT_ID", value)
        use_source(FakeSource([_match()]))

        result = _run("--event", "75", "--tournament-id", "12", "--submit")

        assert result.exit_code == 0, result.output
        assert {m["tournament_id"] for m in _published()} == {12}

    @pytest.mark.parametrize("value", ["0", "-1"])
    def test_an_option_below_one_cannot_run(self, use_source, value):
        source = FakeSource([_match()])
        use_source(source)

        result = _run("--event", "75", "--tournament-id", value, "--submit")

        assert result.exit_code != 0
        assert result.exit_code != 10
        assert source.asked is None
        assert FakeQueue.instances == []

    def test_only_an_absent_id_gets_the_stand_in(self):
        assert cli._event_context(None, "America/Phoenix").stand_in
        real = cli._event_context(12, "America/Phoenix")
        assert (real.tournament_id, real.stand_in) == (12, False)
        with pytest.raises(ValueError):
            cli._event_context(0, "America/Phoenix")

    def test_a_stand_in_context_cannot_be_published(self):
        queue = FakeQueue()
        context = cli._event_context(None, "America/Phoenix")
        message = _match().to_message(context)

        with pytest.raises(RuntimeError, match="stand-in"):
            cli._publish_event(queue, context, [message])

        assert queue.submitted == []

    def test_a_message_built_for_another_id_cannot_be_published(self):
        queue = FakeQueue()
        message = _match().to_message(TournamentContext(tournament_id=1))
        with pytest.raises(RuntimeError, match="another id"):
            cli._publish_event(queue, TournamentContext(tournament_id=12), [message])
        assert queue.submitted == []


class TestWhereItGoes:
    def test_submit_says_the_broker_host_and_queue_first(self, use_source):
        use_source(FakeSource([_match()]))

        result = _run("--event", "75", "--tournament-id", "12", "--submit")

        assert result.exit_code == 0, result.output
        banner = "Publishing to broker mq.example.test:5672, queue 'matches.prod'"
        assert banner in result.output
        assert "tournament id 12" in result.output
        assert result.output.index(banner) < result.output.index("Matches:")

    def test_credentials_are_never_printed(self, use_source):
        use_source(FakeSource([_match()]))
        result = _run("--event", "75", "--tournament-id", "12", "--submit")
        assert "s3cret-pw" not in result.output
        assert "fest-user" not in result.output

    def test_the_queue_named_in_settings_is_the_one_shown(
        self, use_source, monkeypatch
    ):
        monkeypatch.setenv("AGENT_QUEUE_NAME", "matches.local")
        use_source(FakeSource([_match()]))
        result = _run("--event", "75", "--tournament-id", "12", "--submit")
        assert "queue 'matches.local'" in result.output
        assert FakeQueue.instances[0].kwargs["queue_name"] == "matches.local"

    def test_a_dry_run_says_nothing_about_a_broker(self, use_source):
        use_source(FakeSource([_match()]))
        result = _run("--event", "75", "--tournament-id", "12")
        assert "Publishing to" not in result.output

    def test_an_unreachable_broker_stops_before_anything_is_fetched(self, use_source):
        FakeQueue.reachable = False
        source = FakeSource([_match(), _group_match()])
        use_source(source)

        result = _run("--event", "75", "--tournament-id", "12", "--submit")

        assert result.exit_code == 1
        assert "Broker unreachable" in result.output
        assert source.asked is None
        assert _published() == []


class TestNoLeagueHint:
    def test_matches_with_no_league_are_counted_by_competition(self, use_source):
        use_source(
            FakeSource(
                [
                    _match(),
                    _match("16417"),
                    _match(
                        "16992",
                        competition="Pro Player Pathway",
                        source_division="FEST",
                        source_round_label="League (Pro Player Pathway)",
                    ),
                    _group_match(),
                ]
            )
        )

        result = _run("--event", "75")

        assert result.exit_code == 0, result.output
        lines = [" ".join(line.split()) for line in result.output.splitlines()]
        assert "Sent with no league hint: 3" in lines
        assert "2 GA Cup Qualifier" in lines
        assert "1 Pro Player Pathway" in lines

    def test_nothing_is_said_when_every_match_has_one(self, use_source):
        use_source(FakeSource([_group_match()]))
        assert "no league hint" not in _run("--event", "75").output


class TestOutage:
    """Nothing read or nothing published is exit 1, not a finding."""

    def test_every_age_group_failing_is_could_not_run(self, use_source):
        use_source(FakeSource([], failures={"U13": "HTTP 500", "U15": "HTTP 500"}))
        result = _run("--event", "75", "-a", "U13", "-a", "U15")
        assert result.exit_code == 1
        assert "FAILED U13: HTTP 500" in result.output

    def test_some_age_groups_failing_is_a_finding(self, use_source):
        use_source(FakeSource([_match()], failures={"U13": "HTTP 500"}))
        assert _run("--event", "75").exit_code == 10

    def test_every_publish_failing_is_could_not_run(self, use_source):
        FakeQueue.fail_all = True
        use_source(FakeSource([_match(), _group_match()]))

        result = _run("--event", "75", "--tournament-id", "12", "--submit")

        assert result.exit_code == 1
        assert "Submitted 0 matches to queue (2 errors)." in result.output

    def test_an_empty_event_that_read_cleanly_is_clean(self, use_source):
        use_source(FakeSource([]))
        assert _run("--event", "75").exit_code == 0

    def test_a_source_finding_reaches_the_summary_and_the_exit_code(self, use_source):
        use_source(
            FakeSource([_match()], unmapped={"rows that could not be read (U13)": 2})
        )
        result = _run("--event", "75")
        assert result.exit_code == 10
        assert "2  rows that could not be read (U13)" in result.output


class TestFindings:
    """Exit 10: it ran, and there is something to look at."""

    def test_a_failed_age_group_is_reported_and_the_rest_still_sent(self, use_source):
        use_source(FakeSource([_match()], failures={"U13": "HTTP 500"}))

        result = _run("--event", "75", "--tournament-id", "12", "--submit")

        assert result.exit_code == 10
        assert "FAILED U13: HTTP 500" in result.output
        assert len(_published()) == 1

    def test_an_unmapped_label_is_reported(self, use_source):
        use_source(FakeSource([_match(source_round_label="Third Place Match")]))
        result = _run("--event", "75")
        assert result.exit_code == 10
        assert "label 'Third Place Match'" in result.output
        assert "third_place_match" in result.output

    def test_what_the_source_could_not_read_is_reported(self, use_source):
        use_source(FakeSource([_match()], unmapped={"stage 'Knockout Stage'": 4}))
        result = _run("--event", "75")
        assert result.exit_code == 10
        assert "4  stage 'Knockout Stage'" in result.output

    def test_a_publish_error_is_counted(self, use_source):
        FakeQueue.fail_on = {"m11-75-16416"}
        use_source(FakeSource([_match(), _group_match()]))

        result = _run("--event", "75", "--tournament-id", "12", "--submit")

        assert result.exit_code == 10
        assert "Submitted 1 matches to queue (1 errors)." in result.output

    def test_a_match_that_cannot_be_built_is_counted_not_fatal(self, use_source):
        # A row the message model refuses (no home team) costs that match only.
        broken = _match().model_copy(update={"home_team": ""})
        use_source(FakeSource([broken, _group_match()]))
        result = _run("--event", "75")
        assert result.exit_code == 10
        assert "Matches that could not be built: 1" in result.output

    def test_warnings_never_land_in_json_output(self, use_source):
        broken = _match().model_copy(update={"home_team": ""})
        use_source(FakeSource([broken, _group_match()]))

        result = _run("--event", "75", "--json")

        assert result.exit_code == 10
        assert len(json.loads(result.stdout)) == 1
        assert "match 16416 could not be built" in result.stderr
