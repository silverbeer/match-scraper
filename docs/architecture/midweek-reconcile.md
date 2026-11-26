# Midweek Fixtures, Reschedules and Missing Results (SB-1348, SB-1786, SB-1787)

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

## Past matches that disagree with the feed (SB-1787)

### What went wrong

Nothing re-checked a match after its first scrape. Once a row was scored, or
dated in the past, no target counted it as due again, so a later change in the
feed never reached MT. The SB-1779 audit (2026-11-26) found:

| Finding | Count |
|---------|-------|
| Wrong score (18 League, 17 Flex; 7 the exact reverse of the feed's) | 35 |
| Completed officially, still `scheduled` in MT | 14 |
| Re-dated to 2027 officially, on the old date in MT | 42 |
| Completed in MT, postponed officially (28249–28252) | 4 |

Plus SB-1783: Academy 42362, postponed, kept its old date.

### The reconcile

`match-scraper-agent reconcile` (`classify` in
`src/orchestrator/completeness.py`) reads the official feed and every MT match
of the season from `/api/agent/season-matches`, and compares each past League
or Flex row with its fixture, joined on `match_id` = `game_key`:

| Class | Condition | Action |
|-------|-----------|--------|
| `score` | feed completed; score or shootout differs, same orientation | send the feed's fixture |
| `swap` | feed completed; its home/away is MT's away/home | send the feed's fixture |
| `status` | feed completed; MT `scheduled`/`tbd`/`postponed` | send (MT `cancelled`: report only) |
| `redate` | feed not completed, not on the placeholder, new date in the future | send with status `scheduled` |
| `voided` | MT completed/forfeit; feed not completed or on the placeholder | report only |

Sending the feed's fixture is enough because the MT worker already does the
rest: it handles a home/away reversal on the normal path (both names resolve
to team ids), holds score, status and sides on a `score_locked` row and records
the conflict, records `scraped_overrode_manual` when the feed replaces a
person's score, and refuses completed → postponed. So the reconcile:

- **never sends a locked row** — it lists it as "locked, differs";
- **sends a person's row** (scraped data wins on results) and lists it under
  "Overrides a person's score";
- treats **forfeit as completed**: a forfeit with the feed's score is no
  change, and one with a different score is for a person;
- never sends a result dated on the **placeholder**, nor an **unscored
  fixture for a date that is not in the future**;
- lifts a **postponed** row the feed has played (the worker accepts a real
  score over a held status, `_incoming_status`), but only reports a
  **cancelled** one: a person cancelled it;
- reports a past `scheduled`/`tbd` row the feed has moved to the placeholder:
  postponed, with no real date to send;
- never deletes; an MT result the feed does not have is listed only.

Home and away are compared by name, punctuation and case ignored, after the
same normalisation the payload uses. One side agreeing settles the
orientation; when neither does the scores are compared as they stand and the
change carries a `names differ` flag.

MT is read in full before anything is sent: a correction that re-dates a match
moves it between pages. Any failed page is an outage, not an empty season —
exit 1, alert, nothing sent.

`k3s/reconcile/cronjob.yaml` runs it with `--submit` every Monday at 05:00 ET.
Each submitting run with a finding writes a JSON change log to the agent-state
PVC (`/data/agent-state/reconcile/<run>.json`) and a Telegram summary. More
than `--max-changes` (100) corrections refuses the whole batch.

Against the live feed and the SB-1779 prod export (2026-11-26) it finds 35
`score`, 14 `status` (2 of them results on the placeholder, report only), 64
`redate` (the audit's 42 `scheduled` rows, and 22 `postponed` rows the feed has
since given a real date), 4 `voided` and 1 `swap` (on the placeholder, report
only). 42362 is not among them: the feed still has it on the placeholder, so
there is no new date to send.

Usage: [CLI guide, `reconcile`](../guides/cli-usage.md).
