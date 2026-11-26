# ⚽ MLS Match Scraper CLI

A beautiful command-line interface for scraping and displaying MLS match data with rich formatting, colors, and interactive features.

## ✨ Features

- 🎨 **Beautiful terminal output** with colors, tables, and emojis
- 🔍 **Multiple display modes** - full tables, upcoming games, statistics
- 🎮 **Interactive mode** for guided configuration
- ⚡ **Fast and flexible** filtering by age group, division, club, competition
- 📊 **Rich statistics** and match analysis
- 🤖 **Script-friendly** quiet mode for automation
- 🎭 **Demo mode** to preview the interface
- 🐛 **Debug mode** for troubleshooting scraper issues
- 🔍 **Inspector mode** for manual page analysis

## 🚀 Quick Start

### Installation
The CLI is automatically available after installing the project:

```bash
# Install dependencies
uv sync

# Test with demo data
uv run mls-scraper demo

# Or use the shortcut script
./scripts/mls demo
```

### Basic Usage

```bash
# Show help
uv run mls-scraper --help

# Basic scrape (U14 Northeast, next 3 days)
uv run mls-scraper scrape

# Specific age group and division
uv run mls-scraper scrape -a U16 -d Southwest

# Show upcoming games only
uv run mls-scraper upcoming

# Interactive mode
uv run mls-scraper interactive
```

## 📋 Commands

### `scrape` - Main scraping command
Scrapes match data and displays in a beautiful table format.

```bash
uv run mls-scraper scrape [OPTIONS]

Options:
  -a, --age-group TEXT     Age group (U13-U19) [default: U14]
  -d, --division TEXT      Division [default: Northeast]
  -n, --days INTEGER       Days to look ahead for upcoming matches [default: 3]
  -c, --club TEXT          Filter by specific club
  --competition TEXT       Filter by specific competition
  -u, --upcoming          Show only upcoming games
  -s, --stats             Show detailed statistics
  -q, --quiet             Minimal output for scripts
  -v, --verbose           Show detailed logs and full error traces
  -l, --limit INTEGER     Maximum number of matches to display [default: 0]
```

**Examples:**
```bash
# Basic scrape (shows all matches found)
uv run mls-scraper scrape

# Show 10 matches from U16 Southwest
uv run mls-scraper scrape -a U16 -d Southwest -l 10

# U16 Southwest, next 14 days with stats, show 5 matches
uv run mls-scraper scrape -a U16 -d Southwest -n 14 --stats -l 5

# Only upcoming U15 games, show 3
uv run mls-scraper scrape -a U15 --upcoming -l 3

# Run in non-headless mode for debugging
uv run mls-scraper scrape --no-headless

# Quiet mode for scripting
uv run mls-scraper scrape --quiet

# Verbose mode for debugging
uv run mls-scraper scrape --verbose
```

### `upcoming` - Quick upcoming games view
Shows upcoming games in a clean, focused format.

```bash
uv run mls-scraper upcoming [OPTIONS]

Options:
  -a, --age-group TEXT     Age group [default: U14]
  -d, --division TEXT      Division [default: Northeast]
  -n, --days INTEGER       Days to look ahead [default: 3]
  -l, --limit INTEGER      Max games to show [default: 10]
```

**Examples:**
```bash
# Next 10 U14 Northeast games
uv run mls-scraper upcoming

# Next 5 U16 Southwest games
uv run mls-scraper upcoming -a U16 -d Southwest -l 5
```

### `interactive` - Guided experience
Interactive mode with prompts for all configuration options.

```bash
uv run mls-scraper interactive
```

### `config` - Configuration management
Comprehensive environment variable and configuration management.

```bash
# Show current configuration status
uv run mls-scraper config show

# Interactive setup of all environment variables
uv run mls-scraper config setup

# Set a specific environment variable
uv run mls-scraper config set MISSING_TABLE_API_TOKEN your-token-here

# Validate current configuration
uv run mls-scraper config validate

# Show available CLI options and examples
uv run mls-scraper config options
```

**Environment Variable Management:**
- `show` - Display current environment configuration and status
- `setup` - Interactive guided setup of all required and optional variables
- `set` - Set individual environment variables
- `validate` - Check if all required variables are properly configured
- `options` - Show available age groups, divisions, and usage examples

### `demo` - Preview with sample data
Shows how the CLI looks with sample data (no scraping required).

```bash
uv run mls-scraper demo
```

### `test-quiet` - Test quiet mode
Shows how quiet mode output looks for scripting purposes.

```bash
uv run mls-scraper test-quiet
```

### `debug` - Debug the scraper
Helps diagnose issues with the scraping process by running individual steps.

```bash
# Debug all steps
uv run mls-scraper debug

# Debug specific step
uv run mls-scraper debug --step consent

# Debug with visible browser
uv run mls-scraper debug --no-headless
```

**Available debug steps:**
- `url` - Test URL accessibility
- `browser` - Test browser initialization
- `navigate` - Test navigation to MLS page
- `consent` - Test consent banner handling
- `filters` - Test filter discovery and application
- `extract` - Test match extraction
- `inspect` - Inspect page elements

### `inspect` - Manual page inspection
Opens browser and navigates to MLS page for manual inspection of pop-ups, overlays, or blocking elements.

```bash
# Open browser for manual inspection
uv run mls-scraper inspect

# Inspect with visible browser and extended timeout
uv run mls-scraper inspect --no-headless --timeout 300
```

### `poll-release` - Has the schedule been published yet?

Checks whether MLS Next has published fixtures for a season. Queries the
modular11 fixtures endpoint over plain HTTP — no browser, about a second for the
default 18 targets — so it is cheap enough to run on a poll interval while
waiting for a schedule to drop.

> **Stale for 2026-2027 (SB-818).** MLS Next moved to the Kitman assist feeds in
> August 2026 and modular11 no longer carries the current season, so this command
> reports a released schedule as unpublished. Repointing it is pending; until
> then, check `synced_at` on the assist feed instead. See
> [Season Rollover](../architecture/season-rollover.md).

```bash
# Default: U15-first across Northeast, Florida and Mid-Atlantic, fall segment
uv run mls-scraper poll-release

# One target, whole season
uv run mls-scraper poll-release -a U15 -d Northeast --full-season

# Machine-readable, for a CronJob wrapper
uv run mls-scraper poll-release --json --state-file /data/release-probe.ndjson
```

Expected output before a release:

```
MLS Next schedule — 2026-2027 (2026-08-01 → 2026-12-31)
┏━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━━┓
┃ Age ┃ Division     ┃ State ┃ Fixtures ┃
┡━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━━┩
│ U15 │ Northeast    │ empty │        0 │
│ ... │              │       │          │
└─────┴──────────────┴───────┴──────────┘
No fixtures published yet.
```

**Exit codes** are the notification contract for an unattended caller:

| Code | Meaning |
|------|---------|
| `0`  | Nothing new — no fixtures yet, or fixtures already known |
| `10` | Newly published fixtures for at least one target — notify! |
| `20` | Every target failed to probe — notify if it persists |

`--state-file` is what makes "newly" meaningful. Targets already recorded as
live in that NDJSON file do not re-trigger exit `10`, so a scheduled poll alerts
once on release rather than on every run. A missing or corrupt state file is
treated as "nothing seen yet" — the poller keeps working rather than crashing.

Note that `Fixtures` is a lower bound: the endpoint paginates at 25 rows, so the
count answers "are there fixtures?", not "how many?".

### `scrape-event` - A whole tournament, every age group

Part of the `match-scraper-agent` CLI, not `mls-scraper`. Reads every match of
a tournament event (MLS NEXT Fest) for all six age groups and sends each to
missing-table as a tournament match, with its competition, group, round and
penalty score. Without `--submit` it is a dry run.

```bash
# Dry run: MLS NEXT Fest 2025 (modular11 event 75)
uv run match-scraper-agent scrape-event --event 75 --from 2025-12-01 --to 2025-12-31

# One age group, as JSON
uv run match-scraper-agent scrape-event --event 75 -a U15 \
  --from 2025-12-01 --to 2025-12-31 --json

# The same event from the assist feeds instead
uv run match-scraper-agent scrape-event --source assist --event <feed key>

# Publish (needs missing-table's tournament id)
uv run match-scraper-agent scrape-event --env prod --event <id> --tournament-id <id> --submit
```

Expected output (dry run, abridged):

```
Event 75 via modular11, 2025-12-01 to 2025-12-31 — DRY RUN, nothing is published

Matches: 2452
  U13     356
  ...
Rounds:
  showcase            1568
  group_stage          556
  ...
Decided on penalties: 154
Distinct team names: 271
Unmapped values: none
skipped: opponent not decided: 6
```

Exit `0` clean, `10` ran with findings (some age groups failed, some matches
could not be sent, or a feed value the mapping does not know), `1` could not
run — including an outage: nothing fetched, broker unreachable, or nothing
published. `--env` only selects an env file; the queue is `AGENT_QUEUE_NAME`,
default `matches.prod`, and `--submit` prints the broker host and queue first.
Re-running is safe: match ids are stable, so missing-table updates scores and
creates nothing twice.

Full reference — options, the round mapping, the two sources, deployment:
[Tournament Events](tournament-events.md).

### `backfill` - Official results missing from missing-table

Part of the `match-scraper-agent` CLI (SB-1786). Lists every **completed**
League or Flex result in the official feed whose game key is not an MT
`match_id`, and with `--submit` sends them through the normal queue. Without
`--submit` it is a dry run: nothing is published and nothing is alerted.

```bash
# Dry run: both leagues, season start to two days ago
uv run match-scraper-agent backfill

# One league, one window
uv run match-scraper-agent backfill --league Flex --from 2026-09-06 --to 2026-10-04

# Publish (what k3s/completeness/cronjob.yaml runs nightly)
uv run match-scraper-agent backfill --env prod --submit
```

Expected output (dry run, abridged; against the 2026-11-26 prod export from
SB-1779 the diff finds 121 Flex results: 120 to send, and one on the
placeholder date for a person):

```
Backfill Homegrown, Flex, 2026-08-01 to 2026-11-24 — DRY RUN, nothing is published
MT API: api.missingtable.com
Publish target: broker messaging-rabbitmq.match-scraper.svc.cluster.local:5672, queue 'matches.prod'

Feed fixtures: 10917, MT rows read: ... (18 pages)
Official results not in MT: 121
     10  Flex Southeast U15
     ...
  26365  2026-09-06  Flex Southwest (North) U17  Los Angeles Bulls Soccer Club v Ventura County Fusion  3-3 (p 3-4)  action=create
  ...

Needs a person: result on placeholder date: 1
  ...

Dry run: 120 would be sent with --submit.
```

- **Division** is the fixture's own bracket in the feed, falling back to the
  home squad's bracket for the few bracketless fixtures — so a cross-bracket
  Flex fixture is filed where the feed puts it, not where it was scraped from.
- **MT is read a week at a time** from season start to today, plus the
  postponement placeholder date. `/api/matches` takes no limit or offset, so a
  page cannot be continued, only made smaller: a page of 500 rows or more is
  split in half and re-read, and a page of 1000 (PostgREST's cap) stops the
  run. A truncated read would look like missing results.
- **An empty page is an outage**, not a gap, when the feed has results played
  in it: `/api/matches` answers `200 []` when its database query fails. The run
  exits 1, alerts, and sends nothing. The confirming re-read after a send
  retries on the same error rather than reading everything as missing.
- **Some results need a person and are never sent:** a result dated on the
  postponement placeholder (it would land dated months ahead, where no run
  looks) and one with no bracket. Both are listed in the output and the alert.
- **Nothing is deleted.** MT results the feed does not have are listed as
  `action=report`.
- **Publish guard.** Before anything else it prints the MT API host, broker and
  queue, and `--submit` refuses when they disagree: queue `matches.prod` with an
  API other than `api.missingtable.com`, or the reverse, or a fan-out exchange.
- **`--max-changes`** (default 200): with more results missing than this,
  `--submit` publishes none of them, alerts and exits 1 — that many is an
  outage, not a gap.
- With `--submit` it re-reads MT for up to `--confirm-wait` seconds (default
  600) to confirm what it sent landed, and sends a Telegram alert. A game key
  it **sent** on the previous run that is missing again gets the louder one;
  a send that failed, or a result it never sent, is reported but cannot
  repeat. Only the default full-scope run (no `--league`, `--from` or `--to`)
  records state in `AGENT_COMPLETENESS_STATE_PATH`, which the daily digest
  shows as "N official results not in MT".

Exit `0` nothing missing, `10` ran with findings, `1` could not run (feed or MT
unreadable, broker unreachable, publish guard, `--max-changes`). Re-running is
safe: match ids are stable, so missing-table creates nothing twice.

Why the gap happened: [Midweek Fixtures, Reschedules and Missing Results](../architecture/midweek-reconcile.md).

### `reconcile` - Past MT matches that disagree with the feed

Part of the `match-scraper-agent` CLI (SB-1787). Where `backfill` sends
official results MT has no row for, `reconcile` compares the rows MT **does**
have: every past League or Flex match in Homegrown, Flex and the Academy
conferences MT scrapes, joined on match id with its official fixture. With
`--submit` the feed's fixture is published through the normal queue for each
one that differs. Without `--submit` it is a dry run: nothing is published,
nothing is alerted, no change log is written.

```bash
# Dry run: every league scraped, season start to yesterday
uv run match-scraper-agent reconcile

# One league, one class, from a date
uv run match-scraper-agent reconcile --league Flex --only score --since 2026-10-01

# Publish (what k3s/reconcile/cronjob.yaml runs on Mondays)
uv run match-scraper-agent reconcile --env prod --submit
```

| Class | MT row (dated before today) | Feed | Action |
|-------|-----------------------------|------|--------|
| `score` | completed/forfeit | completed, score or shootout differs | send |
| `swap` | any but postponed/cancelled | completed, home and away the other way round | send (the feed's sides) |
| `status` | scheduled/tbd/postponed | completed | send (cancelled: report only) |
| `redate` | scheduled/tbd/postponed | not completed, a real new date in the future | send, status `scheduled` |
| `voided` | completed/forfeit | not completed, or on the placeholder | **report only** |

Never sent, only listed with the reason:

- a **`score_locked`** row (`locked, differs`) — the worker would hold it anyway;
- a **forfeit** whose score differs — a forfeit with the feed's score is no change;
- a result dated on the **postponement placeholder** — it would land months ahead;
- an **unscored fixture** whose new date is today or earlier;
- a past **scheduled/tbd** row whose fixture the feed has parked on the
  placeholder ("postponed to the placeholder: no real date yet");
- a **cancelled** row the feed has played ("cancelled in MT, played per feed");
- an MT result the feed does not have at all — nothing is deleted.

A row a person entered (`entered_by_person`) is sent — scraped data wins on
results — and is listed again under "Overrides a person's score". MT records
each one as `scraped_overrode_manual`.

Expected output (dry run, abridged; the totals are what the classifier finds
for the live feed against the SB-1779 prod export of 2026-11-26):

```
Reconcile Homegrown, Flex, Academy, 2026-08-01 to 2026-11-25 — DRY RUN, nothing is published
MT API: api.missingtable.com
Publish target: broker messaging-rabbitmq.match-scraper.svc.cluster.local:5672, queue 'matches.prod'
Academy conferences: New England

Feed fixtures: ..., MT rows read: ...
  26044 | score | score: 1-1 -> 1-2 | -
  26839 | status | status: scheduled -> completed 0-1 | -
  30664 | redate | date: 2026-11-21 -> 2027-02-21 | -
  28249 | voided | status: completed 1-0 -> not completed (postponed, 2027-06-08) | placeholder | report only: MT counts it as played and the feed does not; never voided here

Totals:
  score     35 to send     0 report only
  swap       0 to send     1 report only
  status    12 to send     2 report only
  redate    64 to send     0 report only
  voided     0 to send     4 report only

Dry run: warning: --submit would refuse: 111 corrections to send, more than --max-changes 100; nothing published.
```

- **MT is read from `/api/agent/season-matches`**, 500 rows a page, every page
  until the first empty one, before anything is sent. The season and league
  ids are looked up by name. Any failed page stops the run: exit 1, a Telegram
  alert on `--submit`, nothing sent.
- **Academy** is reconciled only when `AGENT_ACADEMY_CONFERENCES` (or
  `AGENT_ACADEMY_TARGETS`) turns it on, and only for those conferences.
- **`--only`** (`score,swap,status,redate,voided,mt-only`) restricts what is
  considered *and* reported: a narrowed run lists only what was asked.
- **`--max-changes`** (default 100): with more corrections due, `--submit`
  publishes none, writes the change log, alerts and exits 1. A dry run warns
  and exits 10.
- **The first prod run is a one-off.** The backlog SB-1779 found is more than
  100 corrections, so the weekly job would refuse it. Run it once by hand with
  a higher cap after checking the dry run; the CronJob keeps the default 100:

  ```bash
  uv run match-scraper-agent reconcile --env prod              # check the list
  uv run match-scraper-agent reconcile --env prod --submit --max-changes 150
  ```
- **Publish guard**, as for `backfill`: the MT API host, broker and queue are
  printed first, and `--submit` refuses when they disagree.
- With `--submit` every run with a finding writes a JSON change log to
  `AGENT_RECONCILE_LOG_DIR/<run>.json` (default `/data/agent-state/reconcile`)
  and sends a Telegram summary. No change is sent silently.

Exit `0` nothing differs, `10` ran with findings, `1` could not run (feed or MT
unreadable, broker unreachable, publish guard, `--max-changes` with `--submit`,
every send failed).

Design: [Midweek Fixtures, Reschedules and Missing Results](../architecture/midweek-reconcile.md#past-matches-that-disagree-with-the-feed-sb-1787).

## 🎯 Available Options

### Age Groups
- U13, U14, U15, U16, U17, U19

### Divisions
As read from the live site for the 2026-2027 season:

- **Scraped today:** Northeast, Florida, Mid-Atlantic
- Also present: Central, East, Frontier, Mid-America, MLS Academy, Northwest,
  Southeast, Southwest, West

Division IDs are not stable across seasons — Southeast, Southwest and Northwest
were all renumbered for 2026-2027, and Great Lakes, Texas and California no
longer exist as groups. `src/scraper/modular11.py` holds the site-side IDs and
is the file to update when they move.

## 🛠️ Shortcut Script

For convenience, use the `./scripts/mls` wrapper:

```bash
# Shortcuts
./scripts/mls games -a U16 -d Southwest    # Same as 'scrape'
./scripts/mls upcoming -l 5                # Show upcoming games
./scripts/mls interactive                  # Interactive mode
./scripts/mls demo                         # Demo mode
./scripts/mls config                       # Show config options
./scripts/mls help                         # Show shortcuts help
```

## 📊 Output Examples

### Full Match Table
```
╭─────────────────────────────────────────────────────────── ⚽ Matches Found (15) ──────────────────────────────────────────────────────────╮
│  Date          Time      Home Team               Away Team               Score/Status  Venue                    │
│  09/18/2025    10:00 AM  Austin FC Academy       San Antonio FC Youth       2 - 1      St. David's Performance  │
│  09/19/2025    1:30 PM   Real Salt Lake Academy  Colorado Rapids Youth     🔄 1 - 0    Zions Bank Training      │
│  09/20/2025    3:00 PM   FC Dallas Youth         Houston Dynamo Academy  ⏰ Scheduled  Toyota Stadium           │
╰─────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

### Statistics Panel
```
╭─────────────────────────────────────────────────────────────── 📊 Statistics ───────────────────────────────────────────────────────────────╮
│  Total Matches    15  100%                                                                                       │
│  📅 Scheduled     8    53%                                                                                       │
│  ✅ Completed     7    47%                                                                                       │
│  ⚽ With Scores   7    47%                                                                                       │
│  🏟️  With Venues   12   80%                                                                                       │
│  👥 Unique Teams  24                                                                                             │
╰───────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

### Upcoming Games
```
🔮 Next 5 Upcoming Games:
1. FC Dallas Youth vs Houston Dynamo Academy
   📅 Saturday, September 20 at 3:00 PM
   🏟️  Toyota Stadium

2. Austin FC Academy vs Real Salt Lake Academy
   📅 Sunday, September 21 at 2:00 PM
   🏟️  St. David's Performance Center
```

## 🔧 Configuration

### Quick Setup
The easiest way to configure your environment variables:

```bash
# Interactive setup - guides you through all required variables
uv run mls-scraper config setup

# Check if everything is configured correctly
uv run mls-scraper config validate

# View current configuration
uv run mls-scraper config show
```

### Manual Environment Variables
If you prefer to set environment variables manually:

```bash
export LOG_LEVEL=WARNING                  # Logging level for CLI
export MISSING_TABLE_API_BASE_URL=...     # API endpoint (if using API)
export MISSING_TABLE_API_TOKEN=...        # API token (if using API)
```

**Required Variables:**
- `MISSING_TABLE_API_BASE_URL` - API endpoint for missing-table service
- `MISSING_TABLE_API_TOKEN` - Your service account (SA) token

**Optional Variables:**
- `LOG_LEVEL` - Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `AGE_GROUP` - Default age group (U13-U19)
- `DIVISION` - Default division
- `LOOK_BACK_DAYS` - Default number of days to look ahead
- `MATCH_SOURCE` - Where fixtures come from: `assist` (default — the Kitman JSON
  feeds, 2026-2027 onwards) or `playwright` (browser + modular11, for 2025-2026
  and earlier). See [Season Rollover](../architecture/season-rollover.md)

### Default Settings
- Age Group: U14
- Division: Northeast
- Days to look ahead: 3
- Log Level: WARNING (quiet for CLI use)

## 🎨 Customization

### Colors and Styling
The CLI uses Rich for formatting with these color schemes:
- **Green**: Home teams, completed matches
- **Red**: Away teams
- **Yellow**: Scores, in-progress matches
- **Cyan**: Dates, configuration labels
- **Blue**: Venues, headers
- **Magenta**: Statistics headers

### Quiet Mode
Use `--quiet` for script-friendly output:
```bash
uv run mls-scraper scrape --quiet
# Output:
✅ 09/18 Austin FC Academy vs San Antonio FC Youth (2 - 1)
🔄 09/19 Real Salt Lake Academy vs Colorado Rapids Youth (1 - 0)
⏰ 09/20 FC Dallas Youth vs Houston Dynamo Academy
```

## 🚀 Advanced Usage

### Configuration Management

**First-time setup:**
```bash
# Quick interactive setup
uv run mls-scraper config setup

# Set your SA token specifically
uv run mls-scraper config set MISSING_TABLE_API_TOKEN your-token-here

# Verify everything is configured
uv run mls-scraper config validate
```

**Check configuration status:**
```bash
# View current config
uv run mls-scraper config show

# Validate config before running scrapes
uv run mls-scraper config validate && uv run mls-scraper scrape
```

### Scripting Examples

**Check for upcoming games:**
```bash
#!/bin/bash
GAMES=$(uv run mls-scraper upcoming -l 3)
if [ -n "$GAMES" ]; then
    echo "Upcoming games found:"
    echo "$GAMES"
else
    echo "No upcoming games"
fi
```

**Daily game check:**
```bash
#!/bin/bash
# Check next 3 days for games
uv run mls-scraper scrape -n 3 --upcoming --quiet | \
    grep "$(date +%m/%d)" || echo "No games in next 3 days"
```

**Multi-division check:**
```bash
#!/bin/bash
for division in Northeast Southwest Central; do
    echo "=== $division ==="
    uv run mls-scraper scrape -d "$division" --upcoming --quiet
    echo
done
```

### Integration with Other Tools

**Send to Slack/Discord:**
```bash
GAMES=$(uv run mls-scraper upcoming -l 5)
curl -X POST -H 'Content-type: application/json' \
    --data "{\"text\":\"Upcoming MLS Games:\n$GAMES\"}" \
    YOUR_WEBHOOK_URL
```

**Save to file:**
```bash
uv run mls-scraper scrape --stats > daily_games_$(date +%Y%m%d).txt
```

## 🐛 Troubleshooting

### Common Issues

**Command not found:**
```bash
# Make sure you're in the project directory and using uv
cd /path/to/mls-match-scraper
uv run mls-scraper --help
```

**Configuration issues:**
```bash
# Check what's missing
uv run mls-scraper config validate

# Quick setup if variables are missing
uv run mls-scraper config setup

# View current status
uv run mls-scraper config show
```

**No matches found:**
- Try different age groups or divisions
- Increase the number of days to look ahead
- Check if the MLS website is accessible
- Use demo mode to verify CLI is working

**Browser errors:**
- Install Playwright browsers: `uv run playwright install`
- Check internet connection
- Try running with different configurations
- Use debug mode: `uv run mls-scraper debug --no-headless`
- Use inspector mode: `uv run mls-scraper inspect --no-headless`

**Connection/metrics errors:**
- Ignore "Connection refused" errors on port 4318 (metrics server not running - this is normal)
- Use `--verbose` flag to see full error details when troubleshooting
- Network errors are shown with user-friendly messages by default
- Use `uv run mls-scraper debug` for step-by-step diagnostics

### Debug Mode
Use the verbose flag for detailed logging and full error traces:
```bash
uv run mls-scraper scrape --verbose
```

Or set environment variable:
```bash
export LOG_LEVEL=DEBUG
uv run mls-scraper scrape
```

## 🎯 Tips & Tricks

1. **Use shortcuts**: `./scripts/mls` is faster than `uv run mls-scraper`
2. **Bookmark common commands**: Create aliases for your favorite configurations
3. **Use quiet mode for scripts**: Perfect for automation and notifications
4. **Try interactive mode**: Great for exploring different options
5. **Check demo first**: Verify the CLI works before running real scrapes
6. **Combine with other tools**: Pipe output to grep, awk, or notification systems

## 🔮 Future Enhancements

Potential future features:
- 📱 **Watch mode**: Continuously monitor for new games
- 🔔 **Notifications**: Desktop/mobile alerts for game updates
- 📈 **Trends**: Historical analysis and team performance
- 🗓️ **Calendar export**: Export to Google Calendar, iCal
- 🎯 **Favorites**: Save favorite teams and get targeted updates
- 🌐 **Web dashboard**: Companion web interface

---

**Enjoy using the MLS Match Scraper CLI!** ⚽✨

Built with [Typer](https://typer.tiangolo.com/) and [Rich](https://rich.readthedocs.io/) for a beautiful command-line experience.

For issues or feature requests, check the project repository or create an issue.
