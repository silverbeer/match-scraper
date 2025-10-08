# Observability Configuration Review - Grafana Cloud Loki Integration

## Executive Summary

Your observability setup has **3 critical issues** preventing logs from reaching Grafana Cloud Loki:

1. ❌ **Logs not written to files** - Application logs to stdout, but Promtail reads from `/var/log/scraper/*.log`
2. ❌ **Wrong auth format** - Promtail uses deprecated `bearer_token` field instead of `headers`
3. ⚠️ **Missing env expansion flag** - Environment variables not expanded in Promtail config

## Architecture Overview

```
┌─────────────────────┐
│  mls-scraper pod    │
│                     │
│  ┌──────────────┐   │     ┌──────────────────┐
│  │ mls-scraper  │───┼────▶│ /var/log/scraper │
│  │  container   │   │     │    (shared vol)  │
│  └──────────────┘   │     └────────┬─────────┘
│                     │              │
│  ┌──────────────┐   │              │
│  │  promtail    │◀──┼──────────────┘
│  │  sidecar     │   │
│  └──────┬───────┘   │
│         │           │
└─────────┼───────────┘
          │
          ▼
   Grafana Cloud Loki
 logs-prod-036.grafana.net
```

## Issues Found

### 1. Application Logs Not Written to Files

**Problem:**
- Your Python app uses AWS Lambda Powertools Logger
- This writes to **stdout/stderr** only (no file handlers)
- Promtail is configured to read `/var/log/scraper/*.log`
- **Logs never reach Promtail**

**Evidence:**
```python
# src/utils/logger.py:31-36
self._logger = Logger(
    service=service_name,
    level=os.getenv("LOG_LEVEL", "INFO"),
    use_datetime_directive=True,
    json_serializer=self._custom_serializer,
)
# ↑ No file handlers - only stdout
```

**Solution Applied:**
Modified cronjob.yaml to redirect stdout/stderr to log file:
```yaml
command: ["/bin/sh", "-c"]
args:
  - |
    python -m src.cli.main scrape 2>&1 | tee -a /var/log/scraper/app.log
```

### 2. Wrong Promtail Authentication Format

**Problem:**
```yaml
# promtail-config.yaml (OLD)
clients:
  - url: ${LOKI_ENDPOINT}
    bearer_token: ${GRAFANA_CLOUD_API_TOKEN}  # ❌ This field doesn't exist
```

**Solution Applied:**
```yaml
# promtail-config.yaml (NEW)
clients:
  - url: ${LOKI_ENDPOINT}
    tenant_id: 1
    headers:
      Authorization: Bearer ${GRAFANA_CLOUD_API_TOKEN}  # ✅ Correct format
```

### 3. Missing Environment Variable Expansion

**Problem:**
- Promtail doesn't expand `${VARIABLE}` by default
- Variables remain literal strings: `url: "${LOKI_ENDPOINT}"`

**Solution Applied:**
Added `-config.expand-env=true` flag:
```yaml
args:
  - -config.file=/etc/promtail/promtail.yaml
  - -config.expand-env=true  # ✅ Enable variable expansion
```

## Configuration Details

### Endpoints
```
Loki Push Endpoint: https://logs-prod-036.grafana.net/loki/api/v1/push
OTLP Metrics:       https://otlp-gateway-prod-us-east-2.grafana.net/otlp/v1/metrics
```

### Secrets (Base64 Encoded)
- `GRAFANA_CLOUD_API_TOKEN`: `glc_*` token (valid format ✅)
- `OTEL_EXPORTER_OTLP_HEADERS`: Base64-encoded Basic auth for metrics

### Log Pipeline
```yaml
pipeline_stages:
  - json:           # Parse JSON logs from Lambda Powertools
  - timestamp:      # Extract timestamp field
  - labels:         # Add level, service as labels
  - output:         # Output message field
```

## Testing Your Setup

### 1. Deploy Updated Configuration

```bash
# Apply changes
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/promtail-config.yaml
kubectl apply -f k8s/cronjob.yaml
```

### 2. Trigger Test Scrape

```bash
# Run and watch logs
./scripts/trigger-scrape.sh

# Check promtail logs if needed
SHOW_PROMTAIL_LOGS=true ./scripts/trigger-scrape.sh
```

### 3. Verify Logs in Grafana

1. Go to Grafana Cloud: https://grafana.com
2. Open **Explore** → Select **Loki** data source
3. Query: `{job="mls-match-scraper"}`
4. Should see logs with labels:
   - `job=mls-match-scraper`
   - `service=mls-scraper`
   - `environment=production`
   - `level=INFO|DEBUG|ERROR`

### 4. Debug Promtail Issues

```bash
# Get pod name
POD=$(kubectl get pods -n match-scraper -l job-name=<job-name> -o name)

# Check if log file exists
kubectl exec -n match-scraper $POD -c mls-scraper -- ls -lh /var/log/scraper/

# View log file contents
kubectl exec -n match-scraper $POD -c mls-scraper -- tail -f /var/log/scraper/app.log

# Check Promtail is reading the file
kubectl logs -n match-scraper $POD -c promtail | grep -i "file\|error"
```

## Expected Log Format

Your application produces JSON logs like:
```json
{
  "timestamp": "2025-10-06T12:34:56.789Z",
  "level": "INFO",
  "message": "Starting MLS match scraping operation",
  "service": "mls-match-scraper",
  "operation": "scraping_start",
  "config": {...}
}
```

In Loki, this appears as:
```
Labels: {job="mls-match-scraper", level="INFO", service="mls-match-scraper"}
Message: "Starting MLS match scraping operation"
Timestamp: 2025-10-06T12:34:56.789Z
```

## Common Issues & Solutions

### Logs Not Appearing in Loki

1. **Check Promtail is running:**
   ```bash
   kubectl get pods -n match-scraper
   # Should show 2/2 containers running
   ```

2. **Check Promtail can reach Loki:**
   ```bash
   kubectl logs -n match-scraper <pod> -c promtail | grep -i "error\|connection"
   ```

3. **Verify authentication:**
   ```bash
   # Decode token to verify format
   kubectl get secret mls-scraper-secrets -n match-scraper -o jsonpath='{.data.GRAFANA_CLOUD_API_TOKEN}' | base64 -d
   # Should start with "glc_"
   ```

4. **Check log file exists:**
   ```bash
   kubectl exec -n match-scraper <pod> -c promtail -- cat /var/log/scraper/app.log
   ```

### Promtail Shows "No Targets" Error

- Verify shared volume is mounted in both containers
- Check file path in `__path__` matches actual log location
- Ensure log file has read permissions for promtail user

### Logs Delayed in Loki

- Normal: Promtail batches logs (1s batchwait, 1MB batchsize)
- Check `batchwait` and `batchsize` in promtail config
- For testing, reduce to: `batchwait: 100ms` and `batchsize: 102400`

## Next Steps

1. ✅ **Apply the fixes** (already done in this review)
2. 🧪 **Test the setup:**
   ```bash
   ./scripts/trigger-scrape.sh
   ```
3. 📊 **Verify in Grafana Cloud:**
   - Check logs appear in Explore
   - Verify labels are correct
   - Confirm timestamps are accurate
4. 📈 **Create dashboards:**
   - Scraping success rate
   - Error rates by level
   - Match extraction metrics
5. 🚨 **Set up alerts:**
   - High error rate
   - No logs received in X minutes
   - Specific error patterns

## Additional Improvements

### 1. Add Structured Logging Context

Add more labels to make querying easier:

```python
# In logger.py, add pod/node info
import os

logger.append_keys(
    pod_name=os.getenv("HOSTNAME", "unknown"),
    namespace=os.getenv("K8S_NAMESPACE", "unknown"),
)
```

### 2. Add Log Sampling for High-Volume Logs

If you have very verbose DEBUG logs:

```yaml
# In promtail pipeline_stages
- match:
    selector: '{level="DEBUG"}'
    action: drop
    drop_counter_reason: debug_logs_dropped
```

### 3. Enable Multiline Log Support

For stack traces:

```yaml
pipeline_stages:
  - multiline:
      firstline: '^\d{4}-\d{2}-\d{2}'
      max_wait_time: 3s
```

## Files Changed

- ✅ `k8s/promtail-config.yaml` - Fixed auth format
- ✅ `k8s/cronjob.yaml` - Added log redirection and env expansion
- ✅ `scripts/trigger-scrape.sh` - Added promtail log viewing

## Resources

- [Promtail Configuration Docs](https://grafana.com/docs/loki/latest/send-data/promtail/configuration/)
- [Grafana Cloud Loki Setup](https://grafana.com/docs/grafana-cloud/send-data/logs/logs-loki/)
- [AWS Lambda Powertools Logger](https://docs.powertools.aws.dev/lambda/python/latest/core/logger/)
