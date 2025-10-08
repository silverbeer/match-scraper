# Observability Guide - Grafana Cloud Integration

This guide covers the observability setup for the MLS Match Scraper using Grafana Cloud.

## Overview

The match-scraper implements comprehensive observability using:
- **Metrics**: OpenTelemetry (OTLP) → Grafana Cloud Prometheus/Mimir
- **Logs**: Promtail sidecar → Grafana Loki
- **Infrastructure**: GKE (Google Kubernetes Engine)

## Architecture

```
┌─────────────────┐
│  MLS Scraper    │
│   (Main Pod)    │
│                 │
│  ┌───────────┐  │
│  │ App Code  │──┼──[OTLP]──→ Grafana Cloud Metrics (Mimir)
│  └───────────┘  │
│       │         │
│  [JSON Logs]    │
│       ↓         │
│  /var/log/      │
│       │         │
│  ┌───────────┐  │
│  │ Promtail  │──┼──[HTTP]──→ Grafana Loki
│  │ (Sidecar) │  │
│  └───────────┘  │
└─────────────────┘
```

## Prerequisites

### 1. Grafana Cloud Account
- Sign up at https://grafana.com/auth/sign-up/create-user
- Create a stack (e.g., `missing-table-stack`)
- Note your:
  - Stack name/slug
  - Instance ID
  - Zone (e.g., `prod-us-central-0`)

### 2. API Tokens

#### For Metrics (OTLP)
1. Go to your Grafana Cloud portal
2. Navigate to **Connections** → **Add new connection** → **OpenTelemetry (OTLP)**
3. Create a new API token with `MetricsPublisher` role
4. Note the:
   - Instance ID (e.g., `123456`)
   - Zone (e.g., `prod-us-central-0`)
   - Token value

#### For Logs (Loki)
1. Navigate to **Connections** → **Grafana Loki**
2. Get your Loki endpoint URL (e.g., `https://logs-prod-us-central-0.grafana.net/loki/api/v1/push`)
3. Create an API token with `logs:write` permission
4. Note the token value

## Configuration

### Step 1: Update ConfigMap

Edit `k8s/configmap.yaml`:

```yaml
# Replace placeholders with your actual values
OTEL_EXPORTER_OTLP_ENDPOINT: "https://otlp-gateway-prod-us-central-0.grafana.net/otlp/v1/metrics"
LOKI_ENDPOINT: "https://logs-prod-us-central-0.grafana.net/loki/api/v1/push"
```

**Example values**:
- Zone: `prod-us-central-0` (US Central)
- Zone: `prod-eu-west-0` (EU West)
- Zone: `prod-ap-southeast-0` (APAC)

### Step 2: Update Secret

Edit `k8s/secret.yaml`:

#### Encode OTLP Headers
```bash
# Format: instanceID:token
# Example: 123456:glc_eyJrIjoiYWJjZGVm...
echo -n "YOUR_INSTANCE_ID:YOUR_GRAFANA_TOKEN" | base64

# Then wrap in Authorization header
echo -n "Authorization=Basic YOUR_BASE64_FROM_ABOVE" | base64
```

Update the secret:
```yaml
OTEL_EXPORTER_OTLP_HEADERS: "YOUR_FINAL_BASE64_HERE"
```

#### Encode Loki Token
```bash
echo -n "YOUR_GRAFANA_LOKI_TOKEN" | base64
```

Update the secret:
```yaml
GRAFANA_CLOUD_API_TOKEN: "YOUR_BASE64_LOKI_TOKEN"
```

### Step 3: Deploy

```bash
# Apply updated configurations
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/promtail-config.yaml
kubectl apply -f k8s/cronjob.yaml

# Verify deployment
kubectl get cronjob -n match-scraper
kubectl describe cronjob mls-scraper-cronjob -n match-scraper
```

### Step 4: Test

```bash
# Trigger a manual run
kubectl create job --from=cronjob/mls-scraper-cronjob test-observability -n match-scraper

# Check pod status
kubectl get pods -n match-scraper

# View logs from both containers
kubectl logs -n match-scraper POD_NAME -c mls-scraper
kubectl logs -n match-scraper POD_NAME -c promtail

# Cleanup test job
kubectl delete job test-observability -n match-scraper
```

## Available Metrics

### Counters
- `games_scheduled_total` - Total scheduled matches found
- `games_scored_total` - Total matches with scores found
- `api_calls_total` - Total API calls (with labels: endpoint, method, status_code)
- `scraping_errors_total` - Total scraping errors (with label: error_type)
- `browser_operations_total` - Total browser operations (with labels: operation, success)

### Histograms
- `scraping_duration_seconds` - Duration of scraping operations
- `api_call_duration_seconds` - API response time distribution
- `browser_operation_duration_seconds` - Browser operation timing
- `application_execution_duration_seconds` - Overall execution time

### Labels
All metrics include:
- `service.name`: `mls-match-scraper`
- `service.version`: `1.0.0`
- `deployment.environment`: `production`
- `k8s.namespace.name`: `match-scraper`
- `k8s.pod.name`: Pod hostname
- `cloud.provider`: `gcp`
- `cloud.platform`: `gcp_kubernetes_engine`

## Log Format

Logs are structured JSON from AWS Lambda Powertools:

```json
{
  "timestamp": "2025-10-06T10:00:00.123Z",
  "level": "INFO",
  "message": "Starting MLS match scraping operation",
  "service": "mls-match-scraper",
  "operation": "scraping_start",
  "config": {...}
}
```

Promtail extracts and labels:
- `level` - Log level (INFO, WARNING, ERROR)
- `service` - Service name
- `operation` - Operation type
- `job` - Job name (mls-match-scraper)
- `environment` - Deployment environment
- `namespace` - K8s namespace

## Grafana Dashboards

### Creating Dashboards

1. Log into your Grafana Cloud instance
2. Go to **Dashboards** → **New** → **Import**
3. Upload the dashboard JSON files from `grafana/dashboards/`

### Recommended Dashboards

#### 1. Scraper Overview Dashboard
**File**: `grafana/dashboards/scraper-overview.json`

Panels:
- Total matches scraped (time series)
- Success rate (gauge)
- API call latency (heatmap)
- Execution duration (histogram)
- Error rate by type (table)

#### 2. Performance Dashboard
**File**: `grafana/dashboards/scraper-performance.json`

Panels:
- Browser operation timing (time series)
- API response times p50/p95/p99 (graph)
- Memory usage (area chart)
- CPU usage (line chart)

#### 3. Error Tracking Dashboard
**File**: `grafana/dashboards/scraper-errors.json`

Panels:
- Error count by type (bar chart)
- Failed API calls (table)
- Error logs (logs panel)
- Alert status (stat)

## Querying Metrics

### PromQL Examples

**Total matches scraped in last 24h**:
```promql
sum(increase(games_scheduled_total[24h]))
```

**API success rate**:
```promql
sum(rate(api_calls_total{status_class="2xx"}[5m]))
/
sum(rate(api_calls_total[5m])) * 100
```

**p95 API latency**:
```promql
histogram_quantile(0.95,
  sum(rate(api_call_duration_seconds_bucket[5m])) by (le, endpoint)
)
```

**Error rate by type**:
```promql
sum by (error_type) (rate(scraping_errors_total[5m]))
```

## Querying Logs

### LogQL Examples

**All logs from scraper**:
```logql
{job="mls-match-scraper"}
```

**Error logs only**:
```logql
{job="mls-match-scraper"} |= "level" |= "ERROR"
```

**API call logs**:
```logql
{job="mls-match-scraper", operation="api_call"}
```

**Scraping operations with duration**:
```logql
{job="mls-match-scraper"}
| json
| operation="scraping_complete"
| line_format "Duration: {{.metrics.execution_duration_ms}}ms"
```

## Alerting

### Recommended Alerts

#### 1. High Error Rate
```promql
Alert: ScraperHighErrorRate
Expr: (sum(rate(scraping_errors_total[5m])) / sum(rate(api_calls_total[5m]))) > 0.1
For: 5m
Severity: warning
Message: Scraper error rate is above 10%
```

#### 2. API Failures
```promql
Alert: ScraperAPIFailures
Expr: sum(rate(api_calls_total{status_class=~"4xx|5xx"}[5m])) > 0.5
For: 5m
Severity: critical
Message: API is experiencing failures
```

#### 3. CronJob Not Running
```promql
Alert: ScraperCronJobMissed
Expr: time() - max(application_execution_duration_seconds) > 86400
For: 1h
Severity: warning
Message: Scraper CronJob hasn't run in 24+ hours
```

#### 4. Slow Execution
```promql
Alert: ScraperSlowExecution
Expr: histogram_quantile(0.95, sum(rate(application_execution_duration_seconds_bucket[5m])) by (le)) > 300
For: 10m
Severity: warning
Message: Scraper execution is taking longer than 5 minutes (p95)
```

### Setting Up Alerts

1. Go to **Alerting** → **Alert rules** → **New alert rule**
2. Choose **Grafana Mimir** as data source
3. Enter the PromQL query
4. Set evaluation interval and duration
5. Configure notification channels (email, Slack, PagerDuty, etc.)

## Troubleshooting

### No Metrics Appearing

1. **Check OTLP endpoint configuration**:
   ```bash
   kubectl get configmap mls-scraper-config -n match-scraper -o yaml | grep OTEL
   ```

2. **Verify OTLP headers secret**:
   ```bash
   kubectl get secret mls-scraper-secrets -n match-scraper -o yaml
   # Decode to verify
   kubectl get secret mls-scraper-secrets -n match-scraper -o jsonpath='{.data.OTEL_EXPORTER_OTLP_HEADERS}' | base64 -d
   ```

3. **Check scraper logs for OTLP errors**:
   ```bash
   kubectl logs -n match-scraper -l app=mls-scraper --tail=100 | grep -i otel
   ```

4. **Test OTLP endpoint manually**:
   ```bash
   # From inside the cluster
   kubectl run -it --rm debug --image=curlimages/curl --restart=Never -- \
     curl -v https://otlp-gateway-prod-us-central-0.grafana.net/otlp/v1/metrics
   ```

### No Logs in Loki

1. **Check Promtail container logs**:
   ```bash
   kubectl logs -n match-scraper -l app=mls-scraper -c promtail --tail=100
   ```

2. **Verify Loki endpoint**:
   ```bash
   kubectl get configmap mls-scraper-config -n match-scraper -o yaml | grep LOKI
   ```

3. **Check Loki token**:
   ```bash
   kubectl get secret mls-scraper-secrets -n match-scraper -o jsonpath='{.data.GRAFANA_CLOUD_API_TOKEN}' | base64 -d
   ```

4. **Verify Promtail config**:
   ```bash
   kubectl get configmap promtail-config -n match-scraper -o yaml
   ```

### High Cardinality Warning

If you see warnings about high cardinality metrics:
1. Review metric labels in `src/utils/metrics.py`
2. Avoid adding labels with high cardinality (e.g., match IDs, timestamps)
3. Use exemplars for detailed traces instead

### Authentication Errors

**401 Unauthorized**:
- Verify your API token is valid and not expired
- Regenerate token in Grafana Cloud if needed
- Ensure base64 encoding is correct (no trailing newlines)

**403 Forbidden**:
- Check token has correct permissions (`MetricsPublisher` for metrics, `logs:write` for logs)
- Verify instance ID matches your stack

## Cost Optimization

### Metrics
- Default export interval: 10 seconds
- Increase to 30-60s for lower costs: Set `OTEL_METRIC_EXPORT_INTERVAL=30000`
- Use recording rules to pre-aggregate metrics

### Logs
- Promtail batches logs (1MB or 1s interval)
- Consider filtering noisy logs in Promtail config
- Set retention period in Grafana Cloud (default: 30 days)

### Free Tier Limits
Grafana Cloud Free tier includes:
- **Metrics**: 10k series, 14 days retention
- **Logs**: 50GB/month, 14 days retention
- **Dashboards**: Unlimited
- **Alerts**: 5 alert rules

## Resources

- [Grafana Cloud Documentation](https://grafana.com/docs/grafana-cloud/)
- [OpenTelemetry Python SDK](https://opentelemetry-python.readthedocs.io/)
- [Promtail Documentation](https://grafana.com/docs/loki/latest/clients/promtail/)
- [PromQL Guide](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [LogQL Guide](https://grafana.com/docs/loki/latest/logql/)

## Support

For issues or questions:
1. Check pod logs: `kubectl logs -n match-scraper -l app=mls-scraper`
2. Review Grafana Cloud status: https://status.grafana.com/
3. Consult documentation: https://grafana.com/docs/
