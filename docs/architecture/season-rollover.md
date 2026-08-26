# Season rollover

What breaks when MLS Next starts a new season, and why. Written after the
2025-2026 → 2026-2027 rollover (observed 2026-08-02, SB-499).

## 2026-08-24: MLS Next left modular11 (SB-818)

**Everything below about modular11 now describes 2025-2026 and earlier only.**

MLS Next replaced the schedule iframe with a Kitman "assist" SPA that reads two
static JSON documents per competition season. There is no division dropdown any
more, no calendar widget and no HTML fragment to parse:

```
https://mls-assist.theintelligenceplatform.com/data/schedule/<key>.json
https://mls-assist.theintelligenceplatform.com/data/standings/<key>.json
```

| Key | Competition | Events (2026-2027) |
|-----|-------------|--------------------|
| `mls-next-league-26-27` | Homegrown — League + Pro Player Pathway | 7,763 |
| `mls-next-flex-26-27` | MLS NEXT Flex | 3,160 |
| `mls-next-2-academy-division-26-27` | Academy Division | 13,705 |

The 2026-2027 season is published **only** there — modular11 answers `No data
available.` for every 26/27 target while still serving 2025-2026. Prior seasons
are the mirror image: no `*-25-26` key exists on the new platform (the request
returns the SPA's HTML shell with a 200, not a 404).

### Where the division filter went

The schedule feed's `division` field is useless for Homegrown — every event
reports `MLS Next`. Conference structure lives in the **standings** feed, whose
`competition_brackets` are one per conference x age group, each listing its
teams by `squad_id`. Those IDs appear on every schedule event, so the join is
exact and needs no name matching:

```
standings.competition_brackets[].standings[].team.squad_id
    -> schedule.events[].home_squad_id / away_squad_id
```

`AssistIndex` in `src/scraper/assist_client.py` does this. Membership is asked
per bracket rather than resolved per squad, because a club can sit in two
brackets at once — FC Dallas U17 is in both `Frontier` and `Southeast (Pro
Player Pathway)` for 2026-2027.

**This retires the hand-maintained ID tables.** `AGE_GROUP_IDS` and
`DIVISION_GROUP_IDS` no longer need to be re-read off a live `<select>` each
season; the feed carries its own structure. The ID-drift table below is kept as
the record of what that cost.

### Choosing a source

`ScrapingConfig.source` (env `MATCH_SOURCE`) selects it, and every caller of
`MLSScraper.scrape_matches()` picks it up:

| Value | Path | Use for |
|-------|------|---------|
| `assist` (default) | HTTP, two JSON reads, ~300 ms | 2026-2027 onwards |
| `playwright` | Browser + modular11 | 2025-2026 backfill |

### What still needs verifying

Every 2026-2027 fixture is `completed: false` with null scores — the season had
not started when this was written (first Homegrown match 2026-09-05). The
score-sync path cannot be exercised until then.

Note also that MLS publishes placeholder kick-offs: 157 of 273 Northeast U14
fixtures carry venue `TBD` and 10:00 UTC. The site itself renders those as
"6:00 AM EDT", so reproducing them is correct behaviour, not a timezone bug.

## What the 2026-2027 rollover did *on modular11*

The MLS Next schedule page embeds a modular11 iframe. On rollover:

- The iframe URL gained a new season token: `modular11.com/schedule?year=21`.
- The **calendar widget stopped accepting prior-season dates**. Scraping
  2025-09-05 through Playwright now fails with `Failed to navigate to start
  date month` after four attempts.
- The QoP standings endpoint began answering `There are no teams.` for every
  age group — so the weekly QoP CronJob silently produced nothing.
- Fixtures for the new season were not published for weeks after the rollover.
  The page was up; it was simply empty.

Two things did **not** change: the age-group IDs, and the tournament ID (`12`).

## The three ID spaces, and why they must stay apart

It is easy to treat these as one table. They are not.

| Space | Lives in | Changes when |
|-------|----------|--------------|
| modular11 **age** IDs | `src/scraper/modular11.py` | MLS Next reorganises age groups |
| modular11 **group** IDs (divisions) | `src/scraper/modular11.py` | MLS Next reorganises divisions — **it did in 2026-2027** |
| missing-table **division** IDs | `src/utils/division_lookup.py` | Only when *our* database changes |

For 2026-2027 the site renumbered several divisions:

| Division | 2025-2026 | 2026-2027 |
|----------|-----------|-----------|
| Southeast | 37 | **45** |
| Southwest | 36 | **52** |
| Northwest | 38 | **57** |
| Great Lakes / Texas / California | 39 / 40 / 42 | *removed* |
| West / Frontier / Mid-America / MLS Academy | — | 33 / 66 / 67 / 225 |

Northeast (41), Florida (46), Mid-Atlantic (68), Central (34) and East (35)
were unchanged, which is why the divisions we scrape kept working.

**`division_lookup.DIVISION_ID_MAP` was seeded from the site's IDs and still
carries the old values.** That is deliberate: those integers are posted to
missing-table as `division_id`, so changing them to match the site would point
at divisions missing-table does not have. Before scraping Southeast, Southwest
or Northwest, reconcile the two maps explicitly — do not copy one into the
other.

## Derive season boundaries, never pin them

Three constants were pinned to literal years and all three went stale at once:

- `division_discovery.SEASON_START/SEASON_END` (2025-09-01 → 2026-06-30)
- `cli.main.build_match_dict`'s `"season": "2024-25"` — two seasons behind
- `match-scraper-agent`'s `SEASON_END = date(2026, 6, 30)`

All season maths now comes from `src/scraper/modular11.py`:

```python
current_season_year(date(2027, 3, 1))  # 2026 — March belongs to 2026-2027
season_label(2026)                     # '2026-2027'
season_window(2026)                    # (2026-08-01, 2027-07-15)
fall_segment_window(2026)              # (2026-08-01, 2026-12-31)
```

The season starts in August and ends mid-July; those bounds mirror the default
`start_date`/`end_date` the modular11 iframe sends for itself.

Season labels use the four-four form (`2026-2027`), matching what
match-scraper-agent posts. The old `2024-25` form in this repo was a
divergence, not a second supported format.

## The HTTP endpoint behind the iframe

The iframe fetches fixtures from a plain GET endpoint — no browser required:

```
GET https://www.modular11.com/public_schedule/league/get_matches
    ?tournament=12&age[]=33&groups[]=41&status=all&match_type=2
    &start_date=2026-08-01 00:00:00&end_date=2027-07-15 23:59:59
    &open_page=0&academy=0&gender=0&brackets=&group=&match_number=0
    &schedule=0&teamPlayer=0&location=0&as_referee=0&report_status=0
```

Notes learned the hard way:

- `status` must be one of `all`, `scheduled`, `pending`. Anything else returns
  a red error fragment, not an HTTP error.
- Results paginate at 25 rows. Counting rows answers "are there fixtures?",
  not "how many?".
- Pre-release the response is `No data available.` in about 70 bytes.
- **Prior-season data is still served here** even though the calendar UI
  refuses those dates. The Playwright block is a UI limitation, not a data one,
  so a backfill path still exists via this endpoint.

`src/scraper/release_detector.py` uses this to answer "has the schedule been
published?" in about a second across 18 targets. See
[`cli-usage.md`](../guides/cli-usage.md) for the `poll-release` command.

## Rollover checklist

When the season turns over:

1. Run `mls-scraper poll-release` — confirms whether fixtures exist yet.
2. Re-read `select[js-groups]` on `modular11.com/schedule?year=<token>` and
   diff against `DIVISION_GROUP_IDS`.
3. Check `select[js-age]` against `AGE_GROUP_IDS`.
4. Confirm the QoP endpoint returns teams again before trusting the QoP
   CronJob's output.
5. Run `discover` + `enrich` for any division whose clubs are not yet in
   missing-table.
