# Midweek Fixtures, Reschedules and Missing Results (SB-1348, SB-1786)

## What went wrong

Two RBNY v TSF fixtures played on Wednesday 2026-10-14 never reached MT:

| Game | Bracket | Feed | MT before the fix |
|------|---------|------|-------------------|
| 28612 | U13 Homegrown Northeast | 2026-10-14, 4-0, completed | 2026-10-14, scheduled, no score |
| 28630 | U15 Flex Turnpike | moved 10-17 → 10-14, 1-3, completed | 2026-10-17, scheduled, last updated 2026-08-26 |

There were two separate gaps:

1. **`needs_score` only looked at Saturday and Sunday.** The planner asked MT's
   match-summary endpoint about last weekend's Saturday and Sunday. MT
   reported `needs_score: 0` all week for anything played on a Friday night or
   midweek, so the target SKIPped.
2. **MT can't see a reschedule.** Game 28630 was still dated in the future in
   MT, so nothing was ever due and the target was never re-read.

## What the planner does now

- **`needs_score` uses the score-sync window.** `_score_window(today)` is
  `_match_weekend_window(today)` capped at today: Friday to Monday at the
  weekend, last Friday to next Monday on Tuesday–Friday. MT gets asked about
  the same days a SCORE_SYNC scrapes.
- **Quiet targets get a RECONCILE on Tuesday–Friday.** A target that would
  have SKIPped is scraped over last Friday to next Monday. The feed is cached
  HTTP, so a pass over every target only costs filtering in memory.

| Day | Target with `needs_score > 0` | Target with nothing due |
|-----|-------------------------------|-------------------------|
| Sat, Sun, Mon | SCORE_SYNC, Fri–Mon | SKIP |
| Tue–Fri | SCORE_SYNC, last Fri – next Mon | RECONCILE, last Fri – next Mon |

## What a RECONCILE submits

`engine._filter_reconcile`:

| Scraped fixture | Sent? | Why |
|-----------------|-------|-----|
| Scored | yes | The score MT never counted as due |
| Postponed | yes | Same rule as SCORE_SYNC ([postponed matches](postponed-matches.md)) |
| Unscored, dated after today | yes | A new date or kick-off reaches MT this way, and nothing can be live-scored before it kicks off |
| Unscored, dated today or earlier | **no** | MT may hold a live score the feed has not caught up with |

The MT worker updates `match_date` when the fixture arrives with a new date
(`match_tasks._incoming_date`), so a reschedule only needs the fixture to be
submitted.

The Telegram report shows reconciles as one count line (`🔁 N reconciled
midweek`) rather than one line per target, which keeps it under Telegram's
4096-character limit.

## Results that never got a row (SB-1786)

### What went wrong

The SB-1779 audit (2026-11-26) found **121 completed Flex results that were
never in MT**, dated 2026-09-06 to 2026-10-04 (one was parked on the
2027-06-08 placeholder). Every completed League and Pathway result was present.
They were not ingest failures: no row was ever sent.

The cause is inferred from how the planner decides, not from a log:

1. **A target is scraped only when MT says it is due.** The planner asks MT
   for a bracket's state and picks FULL_SYNC only when MT holds nothing for
   it (`total == 0`), SCORE_SYNC when MT has a played match with no score
   (`needs_score`) or a fixture with no kick-off (`needs_kickoff`), and SKIP
   otherwise. `engine.all_scored_skip` turns a SCORE_SYNC into a SKIP when the
   previous run found nothing missing a score, and a SCORE_SYNC does not send
   unscored fixtures.
2. **A fixture MT has never seen cannot make its target due.** Each Flex
   bracket got its one FULL_SYNC early, when its first fixtures appeared.
   Fixtures published into the feed *after* that never got a row, so
   `needs_score` never counted them, so the bracket kept SKIPping — and the
   results were played, scored and missing.
3. **The midweek RECONCILE closed the hole going forward, not backward.**
   Since commit `823bfd9` (2026-10-16) every quiet target is scraped over last
   Friday to next Monday on Tuesday–Friday, which picks up a new fixture as
   soon as it is near. Its window started covering from 2026-10-09; nothing
   ever re-read the weeks before.

### The completeness guard

`match-scraper-agent backfill` (`src/orchestrator/completeness.py`) asks the
question the other way round. Instead of starting from MT's state, it starts
from the official feed:

| Feed says | MT has the game key | Result |
|-----------|---------------------|--------|
| completed, with a score | no (under any league or type) | `create` — sent through the normal queue |
| completed, on the postponement placeholder, or with no bracket | no | listed for a person, never sent |
| completed, with a score | yes | nothing |
| not completed | — | nothing; the ordinary scrape owns unplayed fixtures |
| not in the feed at all | yes, counted as played | `report` — listed, **never deleted** |

`k3s/completeness/cronjob.yaml` runs it with `--submit` daily at 22:40 ET,
before the 23:30 digest. After sending it re-reads MT to confirm the results
landed and records the gaps on the agent-state PVC. Telegram gets the counts
per league/division/age group and the game keys whenever there is a gap; a
game key that was already missing on the previous run gets a louder alert,
because sending it did not work. Only the default full-scope run records
state, and an empty MT page over played results is an outage: nothing is sent. The digest carries one line,
"N official results not in MT".

It refuses to publish when the MT it read and the queue it would write do not
match (`matches.prod` with anything but `api.missingtable.com`, or the
reverse), and when more than `--max-changes` (200) results are missing — a gap
that large is an outage and wants a person, not a bulk send.

Usage: [CLI guide, `backfill`](../guides/cli-usage.md).
