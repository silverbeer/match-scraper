# Observability

What is actually running today, and what is not.

## Alerts: Telegram

The only live signal is Telegram. The deployed CronJobs send a message only when
something needs a person (plus one daily scores digest). The full list of
messages and when each fires is in [`k3s/README.md`, "What reaches Telegram"](../../k3s/README.md#what-reaches-telegram).

Logs are whatever `kubectl logs` shows for the CronJob pods. Nothing ships them
anywhere.

## Metrics: created, not exported

`src/utils/metrics.py` defines OpenTelemetry counters and histograms (via the
`grafana-otel-py` dependency), and the scraper records to them. But no deployed
manifest sets `OTEL_*` or `LOKI_*` (the deployed set is listed in
[`k3s/README.md`](../../k3s/README.md)), so nothing is exported. The Promtail
sidecar and its manifests were removed in SB-558.

The code and dependency are kept on purpose: they get re-wired, not rewritten.

## Dashboards: not deployed

`grafana/dashboards/*.json` are kept as source material only. Nothing deploys
them. See [`grafana/dashboards/README.md`](../../grafana/dashboards/README.md).

## Plan

Linear project **"OBS — Observability as code"**: metrics re-wired through
Grafana Alloy, and dashboards moved into a new `sb-observability` repo
(SB-1698). The earlier Grafana Cloud setup docs, the dashboard deploy workflow,
Grizzly config and Terraform were removed in SB-1687 because they described a
setup that was not running; they are in git history.
