# ✅ Observability Setup Complete - Grafana Cloud Loki Integration

## Success! 🎉

Your match-scraper logs are now flowing to Grafana Cloud Loki!

## What's Working

✅ Application logs written to `/var/log/scraper/app.log`
✅ Promtail successfully reads log files
✅ Environment variables properly substituted via initContainer
✅ Logs successfully sent to Grafana Cloud Loki (no 401 errors!)
✅ JSON log parsing and labeling configured

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Pod: mls-scraper-cronjob                               │
│                                                          │
│  ┌──────────────────────────────────────────────┐      │
│  │  InitContainer: config-preprocessor          │      │
│  │  - Substitutes ${LOKI_USER_ID}               │      │
│  │  - Substitutes ${LOKI_API_KEY}               │      │
│  │  - Creates /etc/promtail-processed/promtail.yaml │
│  └──────────────────────────────────────────────┘      │
│                                                          │
│  ┌──────────────┐         ┌─────────────────────┐      │
│  │ mls-scraper  │────────▶│ /var/log/scraper/   │      │
│  │  container   │  logs   │     app.log         │      │
│  └──────────────┘         └──────────┬──────────┘      │
│                                       │                  │
│  ┌──────────────┐                    │                  │
│  │  promtail    │◀───────────────────┘                  │
│  │  sidecar     │                                        │
│  └──────┬───────┘                                        │
│         │                                                │
└─────────┼────────────────────────────────────────────────┘
          │
          │ HTTPS + Basic Auth
          │ (User: 1142466)
          ▼
   ┌──────────────────┐
   │ Grafana Cloud    │
   │ Loki             │
   │ logs-prod-036    │
   └──────────────────┘
```

## Key Configuration Changes

### 1. InitContainer for Environment Variable Substitution
Instead of relying on Promtail's `-config.expand-env` (which had issues), we use an initContainer to preprocess the config:

```yaml
initContainers:
- name: config-preprocessor
  image: bhgedigital/envsubst:latest
  command: ["/bin/sh", "-c"]
  args:
    - envsubst < /etc/promtail-template/promtail.yaml > /etc/promtail-processed/promtail.yaml
```

### 2. Basic Auth Configuration
```yaml
clients:
  - url: https://logs-prod-036.grafana.net/loki/api/v1/push
    basic_auth:
      username: ${LOKI_USER_ID}    # Substituted by initContainer
      password: ${LOKI_API_KEY}    # Substituted by initContainer
```

### 3. Log Redirection
Application stdout/stderr redirected to file for Promtail to read:
```yaml
command: ["/bin/sh"]
args:
  - -c
  - python -m src.cli.main scrape 2>&1 | tee -a /var/log/scraper/app.log
```

### 4. JSON Log Parsing
Promtail extracts structured fields from Lambda Powertools JSON logs:
```yaml
pipeline_stages:
  - json:
      expressions:
        timestamp: timestamp
        level: level
        message: message
        service: service
        operation: operation
  - timestamp:
      source: timestamp
      format: RFC3339
  - labels:
      level:
      service:
```

## Viewing Logs in Grafana Cloud

### Quick Access
1. Go to [Grafana Cloud](https://grafana.com)
2. Select your stack: **silverbeer-logs**
3. Click **Explore** in left sidebar
4. Select **Loki** data source

### Example Queries

**All match-scraper logs:**
```
{job="mls-match-scraper"}
```

**Errors only:**
```
{job="mls-match-scraper", level="ERROR"}
```

**Specific service operation:**
```
{job="mls-match-scraper"} |= "scraping_start"
```

**Last hour:**
```
{job="mls-match-scraper"} | __timestamp__ >= now() - 1h
```

**Search for text:**
```
{job="mls-match-scraper"} |= "matches found"
```

### Available Labels
Your logs include these labels for filtering:
- `job`: mls-match-scraper
- `service`: mls-scraper
- `environment`: production
- `namespace`: match-scraper
- `level`: INFO, DEBUG, ERROR, WARNING
- `operation`: scraping_start, scraping_complete, api_call, browser_operation, etc.

## Testing

### Manual Test
```bash
# Trigger a test scrape
./scripts/trigger-scrape.sh -- --no-api --start 1 --end 1

# Check promtail logs (should see NO errors)
SHOW_PROMTAIL_LOGS=true ./scripts/trigger-scrape.sh -- --no-api --start 1 --end 1
```

### Verify in Grafana
Run this query in Grafana Explore:
```
{job="mls-match-scraper"} | __timestamp__ >= now() - 5m
```

Should show recent logs from your test run!

## Troubleshooting

### No logs appearing in Grafana

1. **Check Promtail is running:**
   ```bash
   kubectl get pods -n match-scraper
   # Should show 2/2 containers running
   ```

2. **Check Promtail logs for errors:**
   ```bash
   kubectl logs -n match-scraper <pod-name> -c promtail | grep -i error
   ```

3. **Verify initContainer processed config:**
   ```bash
   kubectl logs -n match-scraper <pod-name> -c config-preprocessor
   # Should show: "Promtail config processed successfully"
   ```

4. **Check log file exists:**
   ```bash
   kubectl exec -n match-scraper <pod-name> -c mls-scraper -- ls -lh /var/log/scraper/
   ```

### 401 Authentication Errors

If you see 401 errors in Promtail logs:
1. Verify secret has correct values:
   ```bash
   kubectl get secret mls-scraper-secrets -n match-scraper -o jsonpath='{.data.LOKI_USER_ID}' | base64 -d
   kubectl get secret mls-scraper-secrets -n match-scraper -o jsonpath='{.data.LOKI_API_KEY}' | base64 -d | head -c 30
   ```

2. Update secret with fresh credentials from Grafana Cloud UI

### Logs Delayed

- Normal: Promtail batches logs (1s batchwait, 1MB batchsize)
- Logs appear within 1-2 seconds of being written
- Check Grafana time range includes recent time

## Files Modified

### Configuration Files
- ✅ `k8s/promtail-config.yaml` - Promtail configuration with variable placeholders
- ✅ `k8s/cronjob.yaml` - Added initContainer for envsubst, updated volumes
- ✅ `k8s/secret.yaml` - Contains LOKI_USER_ID and LOKI_API_KEY
- ✅ `scripts/trigger-scrape.sh` - Added SHOW_PROMTAIL_LOGS option

### Documentation
- ✅ `docs/observability-review.md` - Initial review and issues found
- ✅ `docs/fix-loki-auth.md` - Authentication troubleshooting guide
- ✅ `docs/observability-success.md` - This file!

## Next Steps

### 1. Create Dashboards
Go to Grafana → Dashboards → New Dashboard

Example panels:
- **Scraping Success Rate**: Count of successful vs failed scrapes
- **Error Rate**: Rate of ERROR level logs over time
- **Match Extraction**: Number of matches found per scrape
- **API Call Latency**: Duration of API calls

### 2. Set Up Alerts
Go to Grafana → Alerting → New Alert Rule

Example alerts:
- High error rate (> 5 errors in 5 minutes)
- No logs received in 15 minutes
- Scraping failures
- API authentication failures

### 3. Log Retention
Check your Grafana Cloud plan:
- Free tier: 50GB ingestion, 14-day retention
- Pro tier: Custom retention up to 1 year

### 4. Add More Context
Enhance logging in your application:
```python
# In src/utils/logger.py
import os
logger.append_keys(
    pod_name=os.getenv("HOSTNAME", "unknown"),
    k8s_namespace=os.getenv("K8S_NAMESPACE", "unknown"),
    deployment_env=os.getenv("DEPLOYMENT_ENV", "unknown"),
)
```

## Maintenance

### Update Credentials
If you need to rotate the Loki API key:
```bash
# Get new credentials from Grafana Cloud UI
LOKI_USER_ID="<new-user-id>"
LOKI_API_KEY="<new-api-key>"

# Update secret
kubectl patch secret mls-scraper-secrets -n match-scraper --type=json \
  -p="[
    {\"op\": \"replace\", \"path\": \"/data/LOKI_USER_ID\", \"value\": \"$(echo -n "$LOKI_USER_ID" | base64)\"},
    {\"op\": \"replace\", \"path\": \"/data/LOKI_API_KEY\", \"value\": \"$(echo -n "$LOKI_API_KEY" | base64)\"}
  ]"

# Restart promtail (kill pod, it will recreate)
kubectl delete pod -n match-scraper -l app=mls-scraper
```

### Monitor Costs
- Check Grafana Cloud usage: Settings → Usage Insights
- Free tier limits: 50GB logs/month
- Set up alerts for usage thresholds

## Resources

- [Promtail Documentation](https://grafana.com/docs/loki/latest/send-data/promtail/)
- [LogQL Query Language](https://grafana.com/docs/loki/latest/query/)
- [Grafana Cloud Loki](https://grafana.com/docs/grafana-cloud/send-data/logs/)
- [AWS Lambda Powertools Logger](https://docs.powertools.aws.dev/lambda/python/latest/core/logger/)

## Summary

Your observability setup is **fully operational**!

- Logs flow automatically from every scrape job
- Structured JSON logs with rich metadata
- Query and analyze logs in Grafana Cloud
- No authentication errors
- Production-ready configuration

Happy monitoring! 🎉📊
