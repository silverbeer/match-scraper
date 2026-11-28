# Tournament events (MLS NEXT Fest)

`match-scraper-agent scrape-event` reads every match of a tournament, for all
six age groups, and sends each to missing-table (MT) as a **tournament match**:
filed on an MT tournament instead of in a league division, with its
competition, group, round and penalty score (SB-1746).

MLS NEXT Fest 2026 is 2-13 December in Mesa, Arizona. Its schedule was not
published when this was built, and neither was where it will be published, so
the source is swappable and the modular11 one is proven on the 2025 event
(modular11 event `75`, 2,458 matches).

## Knowing when the schedule is out

`watch-release` (the `schedule-release-watch` CronJob, every 30 minutes) also
watches the Fest pages and announces the release once, on Telegram, Slack
`#sb-alerts` (`@channel`) and email at the same time (SB-1774). Plain HTTP, no
browser. While waiting, the pages look like this:

| Page | Waiting | Released |
|---|---|---|
| `matchcenter.mlsnextpro.com/mlsnext/tournaments/fest/` | "Fest Schedule & Standings" (`#mlsnext-fest-schedule-standings`) links to `/fest/temp` | the link points anywhere else, and the message carries that link |
| `www.mlssoccer.com/mlsnext/tournaments/fest/` | same page, same promo | same |
| `www.mlssoccer.com/mlsnext/tournaments/fest/temp` | the body says "Coming Soon" | the text is gone |

It also asks modular11 whether any of events `76`-`90` holds U15 matches on
2026-12-02..13 (SB-1830), because the schedule may land there before the MLS
pages link to it. Fest 2025 was event `75`; the 2026 id is unknown. An event
with matches is a release, and the message names it (`modular11-<id>`) with
its schedule page, `https://www.modular11.com/events/event/iframe/schedule/<id>`.
modular11's "No data available." is waiting. The ids and dates are constants
in `src/scraper/fest_watch.py` (`M11_EVENT_IDS`, `FEST_START`, `FEST_END`).

A non-200, a redirect, a page without the Fest title or without the promo is
an error, never a release. One page failing is fine; every check failing for
three runs in a row alerts once. Check by hand without sending or saving:

```bash
uv run match-scraper-agent watch-release --dry-run
# ...
# fest: matchcenter=waiting, mlssoccer=waiting, fest-temp=waiting, modular11-76=waiting, ...
```

`--no-fest` (or `AGENT_RELEASE_WATCH_FEST=false`) turns it off. After the
announcement the state file remembers it (`fest_announced`) and the pages are
not probed again this season.

## The command

```bash
# Dry run (the default): fetch, build every message, publish nothing
uv run match-scraper-agent scrape-event --event 75 --from 2025-12-01 --to 2025-12-31

# One age group, as JSON messages on stdout (the summary goes to stderr)
uv run match-scraper-agent scrape-event --event 75 -a U15 \
  --from 2025-12-01 --to 2025-12-31 --json

# Publish. Needs MT's tournament id for the environment
uv run match-scraper-agent scrape-event --env prod --event <id> --tournament-id <id> --submit
```

| Option | Default | |
|---|---|---|
| `--source` | `AGENT_EVENT_SOURCE`, else `modular11` | `modular11` or `assist` |
| `--event` | `AGENT_EVENT_ID` | modular11 event id, or assist feed key |
| `--tournament-id` | `AGENT_EVENT_TOURNAMENT_ID` | MT `tournaments.id`, 1 or more. **Required with `--submit`** (see "A bad tournament id" below) |
| `--age-group`, `-a` | all six | repeat for several |
| `--from`, `--to` | the current season | `YYYY-MM-DD`, the venue's dates. `--from` after `--to` is refused |
| `--env` | `local` | which `envs/.env.<env>` to load — **and nothing else** (see below) |
| `--submit` | off | publish to the queue; without it, a dry run |
| `--json` | off | print the messages |
| `--delay` | `1.0` | seconds between requests (modular11), plus up to 0.5s jitter |
| `--save-raw DIR` | off | keep every fetched page |

`--from`/`--to` default to the season containing *today*, so reading the 2025
event from a later season needs both, as in the examples.

### A bad tournament id

`AGENT_EVENT_TOURNAMENT_ID` lives in the ConfigMap every agent CronJob loads,
so the setting itself accepts anything: a value that is blank, `0`, negative
or not a number never fails another command — league scraping, the watchdog
and the rest read it as unset and carry on. `scrape-event` is where it
matters:

| `AGENT_EVENT_TOURNAMENT_ID` | Dry run | `--submit` |
|---|---|---|
| blank / not set | runs; "No tournament id set" | exit `1`, nothing fetched or published |
| `0`, `-3`, `abc` | runs, with a warning on stderr naming the variable and the value | exit `1`, naming the value it received; nothing fetched or published |
| `12` | runs with tournament 12 | publishes to tournament 12 |

`--tournament-id` overrides the setting and must be 1 or more (`0` or a
negative is a usage error, exit `2`). A dry run with no usable id builds its
messages against a stand-in id so they are still validated; that stand-in can
never be published — the publish step refuses it.

### Where `--submit` publishes

`--env` only selects an env file. It does not choose a queue: the queue is
`AGENT_QUEUE_NAME`, and its default is **`matches.prod` whatever `--env`
says** — true of every `match-scraper-agent` command, not just this one. So
`--env local --submit` with no `AGENT_QUEUE_NAME` in `envs/.env.local`
publishes to the production queue of whichever broker `AGENT_RABBITMQ_URL`
names.

A submit therefore says where it is going before anything is fetched or sent —
broker host and queue, never credentials — and checks the broker once up
front, so a broker that is down stops the run instead of failing every message:

```
Event 75 via modular11, 2026-12-04 to 2026-12-06 — SUBMIT
Publishing to broker messaging-rabbitmq.match-scraper.svc.cluster.local:5672, queue 'matches.prod', tournament id 12
```

A dry run of event 75, whole event:

```
Event 75 via modular11, 2025-08-01 to 2026-07-15 — DRY RUN, nothing is published

Matches: 2452
  U13     356
  U14     376
  U15     371
  U16     416
  U17     464
  U19     469
Rounds:
  showcase            1568
  group_stage          556
  consolation          220
  placement_final       46
  round_of_32           32
  round_of_16           16
  quarterfinal           8
  semifinal              4
  final                  2
Status:
  completed           2451
  tbd                    1
Decided on penalties: 154
Distinct team names: 271
Sent with no league hint: 248
    152  GA Cup Qualifier
     90  Pro Player Pathway
      6  Best Of
Unmapped values: none
skipped: opponent not decided: 6
No tournament id set: messages cannot be submitted yet.
```

The event has 2,458 rows (U13 356, U14 376, U15 371, U16 417, U17 464, U19
474). Six of them have `TBD` for a team — a fixture listed before its teams
were decided — and are not sent. MT has a real team row named `TBD`, so a
message naming it would be filed on that row rather than rejected. They are
sent on the first run after the feed names the teams.

### Matches sent with no league hint

248 of the 2,452 messages carry no `league`: the competitions that are neither
`HD` nor `AD` (GA Cup Qualifier 152, Pro Player Pathway 90, Best Of 6). No
league is invented for them. It matters because MT resolves an unhinted team
name only when exactly one team has that name — for a club with both a
Homegrown and an Academy team under one name, MT cannot tell which is meant.
The dry run prints the count by competition so the size of that exposure is
known before submitting.

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Clean |
| `10` | Ran, with findings: **some** age groups failed, **some** matches could not be built or published, rows or score cells could not be read, or the feed carried a competition, division or round label the mapping does not know |
| `1` | Could not run: no event, unknown source or age group, bad or reversed dates, `--submit` without a tournament id of 1 or more — **or an outage**: no age group could be fetched, the broker is unreachable, or no message could be published |
| `2` | Bad command line (an option out of range, such as `--tournament-id 0`) |

`10` is an outcome, not a crash — the same convention as `score-canary` and
`watch-release`. A failed age group does not stop the others. An outage is
deliberately *not* `10`: the half-hourly CronJob treats `10` as fine, and a
run that read nothing or sent nothing must fail it.

An empty read is never reported as clean. From modular11, only a 2xx is a
page; a body that is neither match rows nor `No data available.` (a block or
login page) fails the age group, and so does a full page of 25 with no
paginator. Rows the parser cannot read, and score cells that are neither a
score nor `TBD`, are counted under "Unmapped values".

## Re-running

Re-running is the design, not an accident. Every match keeps the same
`external_match_id` on every run, and MT upserts on it: a new score updates
the row, an unchanged match is skipped, and nothing is created twice.

| Source | `external_match_id` | Why |
|---|---|---|
| modular11 | `m11-<event>-<match id>`, e.g. `m11-75-16423` | Event match ids are bare numbers in the same range as league match ids, and MT's `matches.match_id` is unique across everything |
| assist | the bare `game_key` | What the league path already sends |

**Pick one source per event and never change it after the first `--submit`.**
The two sources give the same match different ids, and MT only adopts an
existing row when that row has no source id. Switching from modular11 to
assist (or back) mid-event therefore files the whole tournament a second time,
as new rows beside the old ones. If the source must change, the first source's
rows have to be removed from MT first.

## What is sent

One message per match, built in one place (`TournamentMatch.to_message` in
`src/models/tournament.py`) whichever source the match came from.

| Field | Value |
|---|---|
| `match_type` | `Tournament` |
| `tournament_id` | `--tournament-id` |
| `division`, `division_id` | never sent — MT rejects a tournament message that has one |
| `home_team`, `away_team` | exactly as the feed has them. No name mapping |
| `match_date`, `match_time` | the venue's wall clock |
| `scheduled_kickoff` | the same instant in UTC. modular11 prints times with no zone, so they are read in `AGENT_EVENT_TIMEZONE` (default `America/Phoenix`) |
| `match_status` | scored → `completed`; unscored and still to come → `scheduled`; unscored and past → `tbd`. Never `live` |
| `home_penalty_score`, `away_penalty_score` | only when regulation ended level, and never `0`-`0` |
| `league` | `Homegrown` for a competition starting `HD `, `Academy` for `AD `, otherwise omitted. Exactly the names league matches are sent with: MT rejects a message whose league it does not know |
| `competition` | the feed's competition, raw (`HD Group Play`) |
| `tournament_group` | the feed's division when it is a real group: one or two capitals (`A`), or `NEXT Pro`. Never sent for a row with no competition — MT namespaces a group by its competition, so HD group `A` and AD group `A` would merge; such a row is reported instead |
| `tournament_round` | an MT round key, from the table below |
| `tournament_round_order` | not sent by the modular11 source (see below) |
| `source` | `match-scraper-agent` |

A time of midnight is the feed's "not set": the date is sent without
`match_time` or `scheduled_kickoff`.

League messages are untouched: `MatchData` emits the five tournament keys only
when `tournament_id` is set, so a league message is byte-for-byte what it was.

### Rounds

The feed gives three strings per match — competition, division, round label —
and `src/scraper/tournament/mapping.py` turns them into a round key. First
rule that matches:

| # | When | Round |
|---|---|---|
| 1 | label `Final (Child Group of NEXT Pro)` | `placement_final` |
| 2 | division `NEXT Pro` | `group_stage` |
| 3 | label `Round of 32` / `Round of 16` / `QuarterFinal` / `Semi-Final` | `round_of_32` / `round_of_16` / `quarterfinal` / `semifinal` |
| 4 | label or division `Consolation` | `consolation` |
| 5 | label `Final`, competition ending `Group Play` | `placement_final` |
| 6 | label `Final`, any other competition | `final` |
| 7 | label `Group Play`, or a single-letter division | `group_stage` |
| 8 | label `Showcase` / `Best Of` / `League (Pro Player Pathway)`, or competition ending `Showcase` | `showcase` |
| 9 | competition `Pro Player Pathway` or `Best Of` | `showcase` |

The label is matched at the **end** of its text after collapsing whitespace,
which drops a street address printed in front of it.

A **blank label** uses only what competition and division say (rules 2, 4, 7,
8, 9, and `Group Play` + division `Playoff`/`Playoffs`/`Finals` →
`placement_final`). If that is not enough, **no round is sent** — a knockout
round is never guessed. A label nobody has seen is sent as a slug
(`Third Place Match` → `third_place_match`), which MT files with a warning.
Both are listed under "Unmapped values" and make the run exit `10`.

Three things the 2025 event settled:

- **The NEXT Pro final is a placement final.** Five NEXT Pro clubs played a
  round robin (division `NEXT Pro`, label `Group Play`); its top two then met
  in a single match labelled `Final (Child Group of NEXT Pro)`, in division
  `Finals`. That is the same thing as the U13/U14 `Playoffs` final, so it is
  `placement_final`. Calling it `final` would give U15 `GA Cup Qualifier` two
  finals: MT files every non-group round under its competition and ignores
  the group there, so nothing could tell it from the knockout final.
- **No round order.** modular11's `js-match-game` looks like a bracket slot
  and is not one: the round of 32 has sixteen matches numbered 0-7 twice, once
  per half of the draw, and nothing on the row says which half.
- **Group-stage draws go to penalties.** 97 of the 154 shootouts were in group
  play.

`tests/unit/fixtures/modular11_event_75/census.json` holds all 126
combinations of age group, competition, division and label in the 2025 event,
and `tests/unit/test_tournament_mapping.py` asserts every one still maps. If
the 2026 format differs, the dry run's "Unmapped values" says how.

## Sources

Both implement `TournamentSource` (`src/scraper/tournament/base.py`) and return
the same `TournamentMatch` rows.

### `modular11` — proven on event 75

`src/scraper/tournament/modular11_event.py`. Plain HTTP against
`events/league/get_matches`, 25 matches a page, no browser.

- One request at a time, `--delay` seconds apart plus jitter; three retries
  with 1/2/4 s backoff; `Retry-After` honoured on 429 and 503.
- `open_page` is 1-based; `0` returns page 1 again.
- The paginator's "N page out of M" ends the loop. A page past the end answers
  `No data available.`; an empty page or one repeating the previous page's ids
  also ends it, and there is a hard cap of 60 pages per age group.
- The whole 2025 event is 101 requests, about four minutes.

### `assist` — built, not yet exercised on a real tournament

`src/scraper/tournament/assist_event.py`, on the existing `AssistClient`.
`--event` is the competition-season key (the `<key>` in
`data/standings/<key>.json`).

What it reads is certain, because the league documents already carry it: match
id (`game_key`), exact kick-off (`start_time` UTC and `local_timezone`), clubs,
venue, score, shootout, competition name, and each fixture's bracket and stage.

What is **not** known is what a tournament's stages and brackets will be
called, because no tournament has been published on that platform. That is one
function, `stage_round_label`: a stage name becomes a round label only if it is
already a label in the table above or is listed in `ASSIST_STAGE_LABELS`
(empty today). Any other stage sends no label and is reported as
`stage '<name>'` under "Unmapped values". Bracket names go through the same
division rules as modular11's.

**To finish it once a real feed exists:** dry-run it, read "Unmapped values",
add each stage name to `ASSIST_STAGE_LABELS`, and — if brackets turn out not to
be bare group letters — extend the division rules in `mapping.py`. The event's
`round_number` is not sent as a round order until it is known to be one.

## Capturing fixtures

`scripts/capture_event_fixtures.py` writes the trimmed pages and the census
under `tests/unit/fixtures/modular11_event_75/`. It is manual and uses the
network; no test imports it. Point it at a `--save-raw` directory to reuse a
dry run's pages rather than fetch them again:

```bash
uv run match-scraper-agent scrape-event --event 75 --from 2025-08-01 --to 2026-07-15 \
  --save-raw /tmp/event75-raw
uv run python scripts/capture_event_fixtures.py --raw /tmp/event75-raw
```

`synthetic_rows.html` in that directory is hand-written, not captured: the 2025
event was read after it finished, so it has no match still to be played and no
address-prefixed label.

## Deployment

`k3s/fest/cronjob.yaml` holds two CronJobs, both America/Phoenix and **both
shipped with `suspend: true`**:

| CronJob | Schedule | Reads |
|---|---|---|
| `fest-scores` | `15,45 8-22 2-13 12 *` | yesterday through tomorrow |
| `fest-sweep` | `0 3 1-15 12 *` | the whole event; sends Telegram on exit `10` |

Exit `10` is logged and the Job succeeds; any other non-zero exit — an outage
is `1` — fails the Job. `fest-scores` also stops, without running the scrape,
if it cannot work out its date window: with no dates the command would read
the whole season.

Nothing in `k3s/` is applied on merge, so merging this starts nothing. To turn
it on for Fest 2026:

1. Find the event (SB-1745), decide the source — once, for the whole event —
   and create the tournament in MT.
2. Dry-run it and read the summary — especially "Unmapped values":
   `uv run match-scraper-agent scrape-event --source <source> --event <id>`
3. Set `AGENT_EVENT_SOURCE`, `AGENT_EVENT_ID` and `AGENT_EVENT_TOURNAMENT_ID`
   in `k3s/agent/configmap.yaml` and apply it. With the event or the
   tournament id blank, `scrape-event --submit` exits `1` without making a
   request.
4. `kubectl apply -f k3s/fest/cronjob.yaml`
5. Un-suspend:
   ```bash
   kubectl -n match-scraper patch cronjob fest-scores -p '{"spec":{"suspend":false}}'
   kubectl -n match-scraper patch cronjob fest-sweep  -p '{"spec":{"suspend":false}}'
   ```
6. Suspend both again when the event is over.

Team names are sent raw. A club MT does not know under the feed's name is
dropped by MT and recorded in its ingest failures (`mt ingest failures`), as
for league matches.
