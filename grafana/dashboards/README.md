# Grafana Dashboards (not deployed)

These dashboard JSON files are **not deployed anywhere**. The metrics they query
(`src/utils/metrics.py`) are created but not exported, so the panels would show
no data today.

They are kept only as source material. They will move to the new
`sb-observability` repo when metrics are re-wired through Grafana Alloy
(SB-1698, Linear project "OBS — Observability as code").

| File | What it was |
|---|---|
| `scraper-overview.json` | run counts, matches scraped/scored, durations, API latency, browser ops |
| `scraper-errors.json` | errors by type, failed API calls, browser failures, error log stream |
| `scraper-test.json` | scratch dashboard |

The deploy paths that used to live here (GitHub Actions workflow, Grizzly,
Terraform, `scripts/deploy-grafana-dashboards.sh`) were removed in SB-1687. See
[`docs/observability/README.md`](../../docs/observability/README.md) for what is
actually running.
