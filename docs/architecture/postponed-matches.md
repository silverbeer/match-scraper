# Postponed matches

How a postponement on mlssoccer.com reaches missing-table (SB-1135, SB-1136).

## How MLS NEXT marks a postponement

The assist schedule feed has no status field. A postponed fixture keeps its
`game_key` and is moved to a **placeholder date**. For 2026-2027 that is
Tuesday **2027-06-08**. On 2026-09-28 it held 103 fixtures (64 league, 39 Flex),
against no more than six on any other June date.

13 of those 103 carry a result (2-0 and 3-0 among them, which reads as
forfeits). Only **unscored** fixtures on the placeholder are treated as
postponed.

## Detection (match-scraper)

`AssistSchedule.placeholder_dates()` recognises the placeholder by shape rather
than pinning the date:

- a Tuesday, Wednesday or Thursday, and
- at least `PLACEHOLDER_MIN_FIXTURES` (20) fixtures in one feed that day.

`AssistClient.get_matches()` then:

1. returns unscored fixtures on a placeholder date **whatever the scrape
   window**. A postponed fixture has left the weekend it was due on, so no
   window would otherwise find it again.
2. flags them `Match.postponed`, so `match_status` is `postponed`.

`get_events()` (used by the release probe) is unchanged unless it is passed
`also_on`.

A SCORE_SYNC normally withholds unscored matches to protect live-scored MT
rows. It lets `postponed` through, because the postponement is the news the
score sync was waiting for.

## Applying it (missing-table worker)

`MatchSubmissionTask` in `backend/celery_tasks/match_tasks.py`:

| Row in MT | Incoming | Result |
|---|---|---|
| scheduled / tbd | postponed | status → postponed, **date kept** |
| postponed / cancelled | tbd or scheduled, same date | unchanged (a person's call stands) |
| postponed | postponed (placeholder date) | unchanged |
| cancelled | postponed | unchanged |
| completed / forfeit | postponed | unchanged |
| postponed / cancelled | real score | completed |
| postponed / cancelled | new real date | date and status updated (rescheduled) |

The placeholder date is never copied onto a row. Doing so would stack every
postponement on one fake Tuesday and lose the date each match was due.

MT's `needs_score` counts only `scheduled` and `tbd`, so a postponed match stops
driving SCORE_SYNC runs.

## When the new date is published

MLS NEXT gives the fixture a real date and it leaves the placeholder. The next
scrape whose window covers that date sends it as `scheduled`, and the worker
reschedules it. The midweek window looks ahead to the coming Monday, so a new
date is picked up at most about a week and a half before the match.
