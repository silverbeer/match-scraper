# Grafana Dashboards for MLS Match Scraper

This directory contains pre-built Grafana dashboard definitions for monitoring the MLS Match Scraper.

## Available Dashboards

### 1. Scraper Overview (`scraper-overview.json`)
**Purpose**: High-level operational monitoring

**Panels**:
- **Scraper Execution Status** - Total runs in the last 24 hours
- **Total Matches Scraped** - Number of scheduled matches found
- **Matches with Scores** - Number of matches with score data
- **API Success Rate** - Percentage of successful API calls
- **Matches Scraped Over Time** - Time series of matches discovered
- **Execution Duration** - p50, p95, p99 latency percentiles
- **API Call Latency by Endpoint** - Heatmap of API response times
- **Error Rate by Type** - Bar chart of errors categorized by type
- **Browser Operations** - Table of browser operation counts and success rates

**Use Cases**:
- Daily operations monitoring
- Performance tracking
- Capacity planning
- SLA compliance

### 2. Errors & Debugging (`scraper-errors.json`)
**Purpose**: Error tracking and troubleshooting

**Panels**:
- **Total Errors (Last Hour)** - Recent error count
- **Failed API Calls** - Number of failed API requests
- **Error Rate** - Percentage of operations resulting in errors
- **Time Since Last Successful Run** - Alert on missed executions
- **Errors Over Time** - Stacked time series of errors by type
- **Failed API Calls by Endpoint** - Table of failed requests with details
- **Browser Operation Failures** - Table of failed browser operations
- **Recent Error Logs** - Live log stream filtered to ERROR level

**Use Cases**:
- Incident response
- Root cause analysis
- Debugging production issues
- Alert investigation

## Importing Dashboards

### Method 1: Via Grafana UI

1. Log into your Grafana Cloud instance
2. Navigate to **Dashboards** → **New** → **Import**
3. Click **Upload JSON file**
4. Select the dashboard JSON file
5. Choose your data sources:
   - **Prometheus/Mimir**: Select your Grafana Cloud Prometheus data source
   - **Loki**: Select your Grafana Cloud Loki data source
6. Click **Import**

### Method 2: Via API

```bash
# Set your Grafana Cloud credentials
GRAFANA_URL="https://YOUR_STACK.grafana.net"
GRAFANA_API_KEY="your-api-key"

# Import dashboard
curl -X POST "$GRAFANA_URL/api/dashboards/db" \
  -H "Authorization: Bearer $GRAFANA_API_KEY" \
  -H "Content-Type: application/json" \
  -d @scraper-overview.json
```

### Method 3: Terraform (Infrastructure as Code)

```hcl
resource "grafana_dashboard" "scraper_overview" {
  config_json = file("${path.module}/grafana/dashboards/scraper-overview.json")
}

resource "grafana_dashboard" "scraper_errors" {
  config_json = file("${path.module}/grafana/dashboards/scraper-errors.json")
}
```

## Dashboard Variables

The dashboards use the following data source variables:

- **Prometheus/Mimir**: Configured automatically when importing
- **Loki**: Configured automatically when importing

If you have multiple environments, you can add template variables:

1. Edit the dashboard
2. Go to **Settings** → **Variables**
3. Add variable:
   - **Name**: `environment`
   - **Type**: Query
   - **Label**: Environment
   - **Query**: `label_values(deployment_environment)`

Then update panel queries to use `{deployment_environment="$environment"}`.

## Customization

### Adding Custom Panels

1. Edit the dashboard in Grafana UI
2. Click **Add** → **Visualization**
3. Select your data source
4. Write your PromQL or LogQL query
5. Configure visualization options
6. Save the dashboard
7. Export to JSON: **Dashboard settings** → **JSON Model** → Copy

### Modifying Queries

Example: Change time range for a panel
```json
{
  "targets": [
    {
      "expr": "sum(increase(games_scheduled_total[1h]))",  // Change [1h] to [6h]
      "legendFormat": "Matches"
    }
  ]
}
```

### Adding Thresholds

```json
{
  "fieldConfig": {
    "defaults": {
      "thresholds": {
        "mode": "absolute",
        "steps": [
          {"value": null, "color": "green"},
          {"value": 80, "color": "yellow"},
          {"value": 90, "color": "red"}
        ]
      }
    }
  }
}
```

## Useful Queries

### PromQL Examples

**Total matches scraped today**:
```promql
sum(increase(games_scheduled_total{service_name="mls-match-scraper"}[24h]))
```

**Average execution time**:
```promql
rate(application_execution_duration_seconds_sum{service_name="mls-match-scraper"}[5m])
/
rate(application_execution_duration_seconds_count{service_name="mls-match-scraper"}[5m])
```

**API error rate**:
```promql
sum(rate(api_calls_total{service_name="mls-match-scraper",status_class=~"4xx|5xx"}[5m]))
/
sum(rate(api_calls_total{service_name="mls-match-scraper"}[5m])) * 100
```

### LogQL Examples

**All error logs**:
```logql
{job="mls-match-scraper"} |= "ERROR"
```

**API call failures**:
```logql
{job="mls-match-scraper", operation="api_call"} |= "failed"
```

**Slow operations (>5s)**:
```logql
{job="mls-match-scraper"}
| json
| duration_ms > 5000
```

## Dashboard Refresh Rates

- **Overview Dashboard**: 30 seconds
- **Errors Dashboard**: 1 minute

Adjust in **Dashboard settings** → **Time options** → **Auto refresh**.

## Alert Configuration

See `OBSERVABILITY.md` for recommended alert rules to configure based on these dashboards.

## Troubleshooting

### Dashboard shows "No data"

1. Verify metrics are being sent:
   ```bash
   kubectl logs -n match-scraper -l app=mls-scraper | grep -i otel
   ```

2. Check data source configuration in Grafana:
   - **Settings** → **Data sources** → Test connection

3. Verify time range matches data availability

### Panels show errors

1. Check PromQL/LogQL syntax in panel query
2. Ensure metric/label names match your setup
3. Verify data source permissions

### Missing data in specific panels

1. Check if metrics are actually being emitted:
   ```promql
   {__name__=~".+",service_name="mls-match-scraper"}
   ```

2. Verify cardinality limits haven't been exceeded
3. Check Grafana Cloud usage/limits

## Best Practices

1. **Set appropriate time ranges**: Use relative times (e.g., `now-6h`) for consistency
2. **Use variables**: Create reusable dashboards for multiple environments
3. **Add descriptions**: Document panels and queries for team members
4. **Version control**: Commit dashboard JSON to git
5. **Test queries**: Validate performance with `rate` and `increase` functions
6. **Monitor costs**: Be aware of Grafana Cloud series/query limits

## Resources

- [Grafana Dashboard Documentation](https://grafana.com/docs/grafana/latest/dashboards/)
- [PromQL Cheat Sheet](https://promlabs.com/promql-cheat-sheet/)
- [LogQL Documentation](https://grafana.com/docs/loki/latest/logql/)
- [Grafana Panel Types](https://grafana.com/docs/grafana/latest/panels-visualizations/)
