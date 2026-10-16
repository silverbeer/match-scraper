# Midweek Fixtures and Reschedules (SB-1348)

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
