# K3s manifests

These deploy the scraper pipeline to **`rancher-desktop`, namespace `match-scraper`**, which is production for match data — it writes to prod Supabase. Moved here from match-scraper-agent in SB-570, when the two repos consolidated.

## What is deployed

| Manifest | Resource | Schedule |
|---|---|---|
| `agent/cronjob.yaml` | `match-scraper-agent` | `0 2,8,14,20 * * *` (America/New_York) |
| `agent/cronjob-weekend.yaml` | `match-scraper-agent-weekend-sat` | `0 15-19,21-23 * * 6` (America/New_York) |
| `agent/cronjob-weekend.yaml` | `match-scraper-agent-weekend-sun` | `0 0-1,3-7,9-13,15-19 * * 0` (America/New_York) |
| `release-watch/cronjob.yaml` | `schedule-release-watch` | `*/30 * * * *` |
| `match-scraper/cleanup-cronjob.yaml` | `cleanup-completed-jobs` | `0 2 * * *` |
| `score-canary/cronjob.yaml` | `score-canary` | `0 12 * * 1` |
| `watchdog/cronjob.yaml` | `match-scraper-watchdog` | `30 * * * *` (America/New_York) |
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

Thirty slots in that window: 25 from the weekend CronJobs, 5 already covered by
the base CronJob at 20:00 Sat and 02:00/08:00/14:00/20:00 Sun. Those hours are
excluded from the weekend schedules on purpose, because `concurrencyPolicy:
Forbid` does not span CronJobs and two agents scraping the same targets at the
same moment would double-publish to the `matches-fanout` exchange.

### Every schedule here is America/New_York

Including the base CronJob, whose comment claimed UTC for months and was wrong.
**A schedule with no `timeZone` is interpreted in the kube-controller-manager's
local zone**, and on rancher-desktop that is `America/New_York`. So
`0 2,8,14,20` had always fired at 02:00/08:00/14:00/20:00 ET — 06:00/12:00/
18:00/00:00 UTC — and the cluster bore that out: `score-canary` (`0 12 * * 1`,
no zone) fired Mondays at 16:00Z, while `cleanup-completed-jobs` (`0 2 * * *`,
`timeZone: UTC`) fired at 02:00Z exactly as written.

SB-1056 did the collision arithmetic in UTC and got five collisions and four
holes for it (SB-1060). The zone is now named on every CronJob rather than
inherited. Naming it changed no fire time — it stops the next reader repeating
the mistake, and it means both jobs cross into EST together in November with
the exclusions still aligned.

Frequency alone does not buy fresher scores: MT counts a match toward
`needs_score` only once its date is strictly before the server's UTC date, so
every target SKIPs until 20:00 ET. Until SB-1058 lands, the extra Saturday
afternoon runs find nothing to do.

Both scraper CronJobs run `ghcr.io/silverbeer/match-scraper:latest`, built by `.github/workflows/test-and-publish.yml` on every push to `main`, with `imagePullPolicy: Always`. **Merging to main is a deploy** on the next tick.

## How you hear about a failure

Three layers, because no single one can see every way this breaks (SB-1062).
Before them there was only the run report, which is sent on success, so silence
meant either "quiet weekend, nothing to scrape" or "dead since yesterday" — and
on a day when every target correctly SKIPs, healthy looks like silence too. Four
consecutive runs died unnoticed on 2026-09-11/12 because of it.

| Layer | Catches | Misses |
|---|---|---|
| The run itself | anything that happens while it is alive — MT down, Playwright crash, broker unreachable | anything that stops it existing |
| `match-scraper-watchdog` | a pod that never started, a suspended or deleted CronJob, a sleeping node | nothing, but it reports late by up to an hour |
| `score-canary` | a feed that has quietly stopped carrying results | anything MT-side; on 2026-09-12 the feed was fine and MT was broken |

The watchdog reads the run journal off the `agent-state` PVC. A successful run
writes it and a failed one does not, so its age measures "when did this last
work" rather than "when did a pod last exist". Hourly at :30, alerting past 8h —
the widest gap in the base schedule is 6h, so 8h clears one missed slot without
crying wolf.

All three exit 10 for "this is the finding", never non-zero for a crash. A
finding Kubernetes reads as a failed Job gets retried, and the signal disappears
into a restart loop.

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
kubectl apply -f k3s/watchdog/cronjob.yaml
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
