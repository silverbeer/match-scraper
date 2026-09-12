# K3s manifests

These deploy the scraper pipeline to **`rancher-desktop`, namespace `match-scraper`**, which is production for match data — it writes to prod Supabase. Moved here from match-scraper-agent in SB-570, when the two repos consolidated.

## What is deployed

| Manifest | Resource | Schedule |
|---|---|---|
| `agent/cronjob.yaml` | `match-scraper-agent` | `0 2,8,14,20 * * *` |
| `agent/cronjob-weekend.yaml` | `match-scraper-agent-weekend-sat` | `0 15-21,23 * * 6` (America/New_York) |
| `agent/cronjob-weekend.yaml` | `match-scraper-agent-weekend-sun` | `0 0-3,5-9,11-15,17-20 * * 0` (America/New_York) |
| `release-watch/cronjob.yaml` | `schedule-release-watch` | `*/30 * * * *` |
| `match-scraper/cleanup-cronjob.yaml` | `cleanup-completed-jobs` | `0 2 * * *` |
| `score-canary/cronjob.yaml` | `score-canary` | `0 12 * * 1` |
| `agent/configmap.yaml` | `match-scraper-agent-config` | — |

The canary answers a question fixture counts cannot: it probes the league, Flex
and Academy feeds for the weekend just gone and exits 10 if fixtures were played
and none came back scored. A feed that quietly stops carrying results looks
exactly like a quiet week otherwise.

### The weekend cadence

The base CronJob runs four times a day. On top of it, `agent/cronjob-weekend.yaml`
adds an hourly run from **15:00 Saturday to 20:00 Sunday, America/New_York**
(SB-1056). The window crosses midnight, so it is two CronJobs — one cron
expression cannot express it.

Thirty slots in that window: 26 from the weekend CronJobs, 4 already covered by
the base CronJob at 22:00 Sat and 04:00/10:00/16:00 Sun (EDT). Those four hours
are excluded from the weekend schedules on purpose, because `concurrencyPolicy:
Forbid` does not span CronJobs and two agents scraping the same targets at the
same moment would double-publish to the `matches-fanout` exchange.

The exclusions assume EDT. When the clocks go back on 2026-11-01 the base slots
move to 21:00/03:00/09:00/15:00 ET and stop lining up — either shift the
exclusions or move the base CronJob onto `America/New_York` too.

Frequency alone does not buy fresher scores: MT counts a match toward
`needs_score` only once its date is strictly before the server's UTC date, so
every target SKIPs until 20:00 ET. Until SB-1058 lands, the extra Saturday
afternoon runs find nothing to do.

Both scraper CronJobs run `ghcr.io/silverbeer/match-scraper:latest`, built by `.github/workflows/test-and-publish.yml` on every push to `main`, with `imagePullPolicy: Always`. **Merging to main is a deploy** on the next tick.

## What is NOT deployed, deliberately

| Manifest | Why |
|---|---|
| `qop-rankings/cronjob.yaml` | SB-544 — MLS Next reset standings for 2026-2027, so it would produce nothing, silently |
| `audit/*.yaml` | run by hand when auditing, not on a schedule |

`backfill/` jobs from the agent repo were one-shot and were not carried over; they are in that repo's history.

## Applying

Apply individual manifests. There is no deploy-everything script, on purpose — the agent repo had one and it was a standing hazard, because it also stood up a second RabbitMQ that nothing consumes from.

```bash
kubectl apply -f k3s/agent/configmap.yaml
kubectl apply -f k3s/agent/cronjob.yaml
kubectl apply -f k3s/agent/cronjob-weekend.yaml
kubectl apply -f k3s/release-watch/cronjob.yaml
```

Check a change before applying it — `kubectl diff` is the difference between a config edit and an outage:

```bash
kubectl diff -f k3s/agent/configmap.yaml
```

## State

Both CronJobs mount the `agent-state` PVC at `/data/agent-state`:

* `journal.json` — the previous run's per-target results. Feeds the modifier rules; without it a failed target is never retried (SB-555).
* `release-watch.json` — which targets have already been announced. Without it the watcher re-announces every 30 minutes (SB-554).

Setting `AGENT_JOURNAL_S3_BUCKET` switches both to S3 instead. The cluster has no AWS credentials, so the PVC is the live path.

## The other directories

`rabbitmq/` and `workers/` predate the agent and describe a broker (`rabbitmq-0`) that the Celery workers do **not** consume from — they use `messaging-rabbitmq`, from the messaging-platform Helm release. Treat them as historical until someone verifies otherwise.
