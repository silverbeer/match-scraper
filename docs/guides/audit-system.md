# Match Audit System

The match audit system provides comprehensive tracking of all match processing activity, enabling validation and troubleshooting of the match-scraper and RabbitMQ pipeline.

## Overview

Every time the match-scraper runs, it creates an audit trail that records:
- Match discoveries (new matches found)
- Match updates (scores, status changes)
- Queue submissions (matches sent to RabbitMQ)
- Run metadata (filters, date ranges, league info)

This audit trail helps you:
- ✅ Verify matches are being processed correctly
- ✅ Track changes between scraping runs (scheduled → scored)
- ✅ Validate sync between mlssoccer.com and Missing Table backend
- ✅ Troubleshoot queue submission issues with task IDs
- ✅ Understand historical scraping activity

## Audit File Format

Audit logs are written in **JSONL** (JSON Lines) format with daily file rotation.

### File Location

**Local development:**
```
./audit/match-audit-2025-11-13.jsonl
./audit/.state/last-run-state.json
```

**Kubernetes (mounted to host):**
```
/Users/silverbeer/gitrepos/match-scraper/audit/match-audit-2025-11-13.jsonl
/Users/silverbeer/gitrepos/match-scraper/audit/.state/last-run-state.json
```

Inside the pod, files are at: `/var/log/scraper/audit/`

### File Rotation

- New file created daily at midnight UTC
- Naming pattern: `match-audit-YYYY-MM-DD.jsonl`
- Old files retained indefinitely (manual cleanup)

## Audit Event Types

### Run Events

**run_started** - Logged when a scraping run begins
```json
{
  "timestamp": "2025-11-13T14:30:45.123Z",
  "run_id": "20251113-143045-abc123",
  "event_type": "run_started",
  "run_metadata": {
    "league": "Homegrown",
    "age_group": "U14",
    "division": "Northeast",
    "date_range": "2025-10-01 to 2025-10-31"
  }
}
```

**run_completed** - Logged when a scraping run finishes
```json
{
  "timestamp": "2025-11-13T14:32:20.123Z",
  "run_id": "20251113-143045-abc123",
  "event_type": "run_completed",
  "run_metadata": { /* ... */ },
  "summary": {
    "total_matches": 15,
    "discovered": 12,
    "updated": 3,
    "unchanged": 0,
    "queue_submitted": 15,
    "queue_failed": 0
  }
}
```

### Match Events

**match_discovered** - New match found for the first time
```json
{
  "timestamp": "2025-11-13T14:31:12.456Z",
  "run_id": "20251113-143045-abc123",
  "event_type": "match_discovered",
  "correlation_id": "100435",
  "match_data": {
    "home_team": "IFA",
    "away_team": "NEFC",
    "match_date": "2025-10-18",
    "home_score": null,
    "away_score": null,
    "match_status": "scheduled",
    "external_match_id": "100435",
    "league": "Homegrown",
    "age_group": "U14",
    "division": "Northeast",
    /* ... other fields ... */
  }
}
```

**match_updated** - Existing match changed (e.g., scheduled → scored)
```json
{
  "timestamp": "2025-11-13T14:31:15.456Z",
  "run_id": "20251113-143045-abc123",
  "event_type": "match_updated",
  "correlation_id": "100436",
  "match_data": {
    "home_team": "IFA",
    "away_team": "BV",
    "match_date": "2025-10-18",
    "home_score": 5,
    "away_score": 1,
    "match_status": "completed",
    "external_match_id": "100436",
    /* ... */
  },
  "changes": {
    "match_status": {"from": "scheduled", "to": "completed"},
    "home_score": {"from": null, "to": 5},
    "away_score": {"from": null, "to": 1}
  }
}
```

**match_unchanged** - Match seen again with no changes (not displayed by default)

### Queue Events

**queue_submitted** - Match successfully submitted to RabbitMQ
```json
{
  "timestamp": "2025-11-13T14:31:16.789Z",
  "run_id": "20251113-143045-abc123",
  "event_type": "queue_submitted",
  "correlation_id": "100436",
  "queue_task_id": "887795e2-12a9-4e72-ba8e-04ff29f44205",
  "queue_success": true
}
```

**queue_failed** - Queue submission failed
```json
{
  "timestamp": "2025-11-13T14:31:20.789Z",
  "run_id": "20251113-143045-abc123",
  "event_type": "queue_failed",
  "correlation_id": "100440",
  "queue_task_id": null,
  "queue_success": false,
  "error_message": "Connection refused"
}
```

## Key Concepts

### correlation_id vs external_match_id

- **correlation_id** (top-level): Used for grouping audit events for the same match across multiple entries
- **match_data.external_match_id**: The MLS match ID sent to the backend for deduplication

Both contain the same value, but serve different purposes in the audit log structure.

### Change Detection

The audit system compares each match against the previous scraping run's state:
- **discovered**: New match ID never seen before
- **updated**: Match ID exists but field values changed
- **unchanged**: Match ID exists with identical field values

State is persisted in `./audit/.state/last-run-state.json`

## CLI Commands

### View Audit Logs

View today's audit log:
```bash
match-scraper audit view
```

View specific date:
```bash
match-scraper audit view --date 2025-11-13
```

Filter by league:
```bash
match-scraper audit view --league Homegrown
match-scraper audit view --league Academy
```

Filter by event type:
```bash
match-scraper audit view --event-type match_updated
match-scraper audit view --event-type queue_failed
```

Filter by match ID:
```bash
match-scraper audit view --match-id 100436
```

Filter by run ID:
```bash
match-scraper audit view --run-id 20251113-143045-abc123
```

Show only changes (match_updated events):
```bash
match-scraper audit view --changes-only
```

Output as JSON (for scripting):
```bash
match-scraper audit view --format json
```

### Audit Statistics

Show statistics for a date:
```bash
match-scraper audit stats
match-scraper audit stats --date 2025-11-13
```

Example output:
```
=== Audit Statistics: 2025-11-13 ===

Metric                 Count
───────────────────────────
Total Entries             89
Scraping Runs              2
Matches Discovered        20
Matches Updated            3
Matches Unchanged          0
Queue Submitted           23
Queue Failed               0

By League:
  Homegrown: 50 entries
  Academy: 39 entries
```

### Validate Audit Logs

Basic validation (counts matches in audit):
```bash
match-scraper audit validate
match-scraper audit validate --date 2025-11-13
match-scraper audit validate --league Homegrown
```

Note: Full backend validation requires MT backend API integration (planned).

## Manual Querying with jq

Audit files are JSONL format, perfect for `jq`:

**Find all completed matches:**
```bash
cat audit/match-audit-2025-11-13.jsonl | \
  jq 'select(.event_type == "match_updated" and .match_data.match_status == "completed")'
```

**Count matches by league:**
```bash
cat audit/match-audit-2025-11-13.jsonl | \
  jq -r 'select(.match_data != null) | .match_data.league' | \
  sort | uniq -c
```

**Find queue failures:**
```bash
cat audit/match-audit-2025-11-13.jsonl | \
  jq 'select(.event_type == "queue_failed")'
```

**Extract all task IDs:**
```bash
cat audit/match-audit-2025-11-13.jsonl | \
  jq -r 'select(.queue_task_id != null) | .queue_task_id'
```

**Find specific match journey:**
```bash
cat audit/match-audit-2025-11-13.jsonl | \
  jq 'select(.correlation_id == "100436")'
```

**Summary by run:**
```bash
cat audit/match-audit-2025-11-13.jsonl | \
  jq 'select(.event_type == "run_completed") | .summary'
```

## Validation Workflow

### Verify Recent Scraping Activity

```bash
# 1. View today's audit log
match-scraper audit view

# 2. Check statistics
match-scraper audit stats

# 3. Look for errors
match-scraper audit view --event-type queue_failed
```

### Troubleshoot Missing Matches

If a match isn't showing up in Missing Table:

1. **Check if it was discovered:**
   ```bash
   match-scraper audit view --match-id 100436
   ```

2. **Verify queue submission:**
   Look for `queue_submitted` event with task ID

3. **Check Celery workers:**
   ```bash
   kubectl exec -n match-scraper rabbitmq-0 -- \
     rabbitmqctl list_queues name messages consumers
   ```

4. **Trace task in Celery logs:**
   Use the task ID from audit log to search Celery worker logs

### Validate Score Updates

Find matches where scores changed:

```bash
match-scraper audit view --changes-only | grep -A 2 "score"
```

### Compare Daily Activity

```bash
# Today vs yesterday
match-scraper audit stats --date $(date +%Y-%m-%d)
match-scraper audit stats --date $(date -d '1 day ago' +%Y-%m-%d)
```

## Integration with Grafana/Loki

Audit logs can be ingested by Loki for dashboards:

1. **Configure Promtail** to tail audit files:
   ```yaml
   - job_name: match-audit
     static_configs:
       - targets:
           - localhost
         labels:
           job: match-audit
           __path__: /var/log/scraper/audit/*.jsonl
     pipeline_stages:
       - json:
           expressions:
             run_id: run_id
             event_type: event_type
             league: run_metadata.league
   ```

2. **Query in Loki:**
   ```logql
   {job="match-audit"} | json | event_type="match_updated"
   ```

3. **Create Grafana dashboard** tracking:
   - Matches discovered per day
   - Queue submission success rate
   - Match updates by league
   - Scraping run frequency

## Troubleshooting

### Audit directory not found

If you see "No audit file found", check:

```bash
ls -la ./audit/
ls -la /var/log/scraper/audit/  # In pod
```

Ensure the directory was created: `mkdir -p audit/.state`

### Permission errors

In Kubernetes, ensure the volume mount has correct permissions:

```bash
chmod 755 /Users/silverbeer/gitrepos/match-scraper/audit
```

### State file corruption

If change detection seems wrong, delete state file:

```bash
rm ./audit/.state/last-run-state.json
```

Next scraping run will treat all matches as "discovered".

### Large audit files

Compress old audit files:

```bash
gzip audit/match-audit-2024-*.jsonl
```

Or archive files older than 90 days:

```bash
find audit/ -name "*.jsonl" -mtime +90 -exec gzip {} \;
mkdir -p audit/archive
mv audit/*.jsonl.gz audit/archive/
```

## Best Practices

1. **Review audit logs daily** to catch issues early
2. **Monitor queue failures** - they indicate infrastructure problems
3. **Track match updates** to understand scraping coverage
4. **Correlate with Celery logs** using task IDs for end-to-end tracing
5. **Archive old logs** to prevent disk space issues
6. **Use jq for ad-hoc analysis** - it's faster than writing scripts

## Future Enhancements

Planned improvements:
- [ ] Full MT backend API integration for `audit validate`
- [ ] Automatic archival of old audit files
- [ ] Grafana dashboard templates
- [ ] Slack/email alerts for queue failures
- [ ] Audit log retention policies
- [ ] Web UI for browsing audit logs
