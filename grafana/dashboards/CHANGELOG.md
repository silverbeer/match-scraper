# Dashboard Changelog

## 2025-10-07 - Label Name Fix

### Changes Made
Fixed all dashboard queries to use the correct metric label name `service` instead of `service_name`.

### Context
The metrics code in `src/utils/metrics.py` uses `service` as the label name (e.g., `{"service": self.service_name}`), but the dashboard JSON files were querying using `service_name`. This mismatch would cause all panels to show no data.

### Files Modified
- `scraper-overview.json` - Updated all 9 panels
- `scraper-errors.json` - Updated all 7 panels (excluding logs panel)

### Affected Metrics
All metric queries were updated:
- `application_execution_duration_seconds_*`
- `games_scheduled_total`
- `games_scored_total`
- `api_calls_total`
- `scraping_errors_total`
- `browser_operations_total`
- `api_call_duration_seconds_*`

### Before
```promql
sum(increase(games_scheduled_total{service_name="mls-match-scraper"}[24h]))
```

### After
```promql
sum(increase(games_scheduled_total{service="mls-match-scraper"}[24h]))
```

## Metrics Reference

### Available Metrics
Based on `src/utils/metrics.py`:

**Counters:**
- `games_scheduled_total` - Total scheduled games found (labels: service, operation)
- `games_scored_total` - Total games with scores (labels: service, operation)
- `api_calls_total` - Total API calls (labels: service, endpoint, method, status_code, status_class)
- `scraping_errors_total` - Total errors (labels: service, error_type)
- `browser_operations_total` - Total browser operations (labels: service, operation, success)

**Histograms:**
- `scraping_duration_seconds` - Scraping operation duration (labels: service, operation)
- `api_call_duration_seconds` - API call response times (labels: service, endpoint, method, status_code, status_class)
- `browser_operation_duration_seconds` - Browser operation times (labels: service, operation, success)
- `application_execution_duration_seconds` - Full application execution time (labels: service, instance)

### Common Labels
- `service` - Always set to "mls-match-scraper"
- `operation` - Operation type (varies by metric)
- `endpoint` - API endpoint path
- `method` - HTTP method (GET, POST, etc.)
- `status_code` - HTTP status code as string
- `status_class` - Status code class (2xx, 4xx, 5xx)
- `error_type` - Type of error encountered
- `success` - Boolean as string ("true" or "false")
- `instance` - Hostname/pod name

## Testing Dashboards

After importing the dashboards to Grafana:

1. Check that all panels show data (not "No data")
2. Verify the time ranges are appropriate
3. Confirm that the API Success Rate gauge shows a percentage
4. Ensure browser operations table populates
5. Check that error panels only show data when errors occur

## Known Issues

None currently. All dashboard queries have been validated against the actual metric labels in the codebase.
