# Manual GKE Job Trigger Script

CLI tool for manually triggering match-scraper jobs on GKE with custom parameters.

## Quick Start

```bash
# Basic usage with defaults (today to +13 days, U14 Northeast)
./scripts/trigger-gke-job.sh

# Custom date range
./scripts/trigger-gke-job.sh --start=0 --end=13

# Last 7 days
./scripts/trigger-gke-job.sh --start=-7 --end=0

# Different age group/division
./scripts/trigger-gke-job.sh --age-group=U16 --division=Southeast
```

## Options

| Option | Description | Default |
|--------|-------------|---------|
| `--start N` | Start date offset (0=today, negative=past) | 0 |
| `--end N` | End date offset | 13 |
| `--age-group GROUP` | Age group to scrape | U14 |
| `--division DIV` | Division to scrape | Northeast |
| `--namespace NS` | Kubernetes namespace | match-scraper |
| `--no-follow` | Don't follow logs (just create job) | false |
| `-h, --help` | Show help message | - |

## Features

✅ **Automatic Job Creation** - Creates Kubernetes job from CronJob template
✅ **Live Log Streaming** - Follows logs in real-time as job runs
✅ **Status Monitoring** - Shows job completion status
✅ **Auto-cleanup** - Jobs auto-delete after 1 hour (TTL)
✅ **Full Observability** - Includes Promtail sidecar for log shipping to Grafana

## Examples

### Scrape Today's Matches
```bash
./scripts/trigger-gke-job.sh --start=0 --end=0
```

### Scrape Upcoming Week
```bash
./scripts/trigger-gke-job.sh --start=0 --end=7
```

### Backfill Last Month
```bash
./scripts/trigger-gke-job.sh --start=-30 --end=0
```

### U16 Southeast Division
```bash
./scripts/trigger-gke-job.sh --age-group=U16 --division=Southeast --start=0 --end=14
```

### Create Job Without Watching Logs
```bash
./scripts/trigger-gke-job.sh --start=0 --end=13 --no-follow
```

## Prerequisites

- `kubectl` installed and configured
- Authenticated to GKE cluster:
  ```bash
  gcloud container clusters get-credentials CLUSTER_NAME --region REGION
  ```
- `match-scraper` namespace exists in cluster
- Docker image pushed to GCR

## Output

The script provides:
- Color-coded status messages
- Configuration summary
- Live log streaming
- Final job status
- Management commands for viewing logs/deleting job

## Troubleshooting

**"Cannot connect to Kubernetes cluster"**
- Authenticate to GKE: `gcloud auth login`
- Get cluster credentials: `gcloud container clusters get-credentials ...`

**"Pod not found"**
- Check namespace exists: `kubectl get ns match-scraper`
- Verify CronJob exists: `kubectl get cronjob -n match-scraper`

**"ImagePullBackOff"**
- Ensure Docker image is pushed: `docker push gcr.io/PROJECT_ID/mls-scraper:latest`
- Check image exists: `gcloud container images list`

## Management

### View Logs After Job Completes
```bash
kubectl logs JOB_POD_NAME -n match-scraper -c scraper
```

### Check Job Status
```bash
kubectl get job JOB_NAME -n match-scraper
```

### Delete Job Manually
```bash
kubectl delete job JOB_NAME -n match-scraper
```

### List All Manual Jobs
```bash
kubectl get jobs -n match-scraper -l trigger=manual
```

## Related Documentation

- [GKE Deployment Guide](../terraform/README.md)
- [Testing Guide](../GKE_TESTING_GUIDE.md)
- [CLI Documentation](../docs/cli.md)
