# GKE Testing and Monitoring Guide

This guide covers all the ways to test, monitor, and view logs for your MLS Match Scraper deployment on GKE.

## Quick Testing Commands

### Using the Test Script (Recommended)

```bash
# Trigger a test run
./scripts/test-gke.sh trigger

# Check status of all jobs
./scripts/test-gke.sh status

# View logs from the latest test run
./scripts/test-gke.sh logs

# Monitor job progress in real-time
./scripts/test-gke.sh monitor

# Clean up test jobs
./scripts/test-gke.sh cleanup
```

## Manual Testing Commands

### 1. Create a Manual Test Job

```bash
# Create a one-time job from the CronJob
kubectl create job --from=cronjob/mls-scraper-cronjob test-run -n match-scraper

# Or create with a timestamped name
kubectl create job --from=cronjob/mls-scraper-cronjob "test-run-$(date +%s)" -n match-scraper
```

### 2. Monitor Job Status

```bash
# Check CronJob status
kubectl get cronjob -n match-scraper

# Check all jobs (including manual runs)
kubectl get jobs -n match-scraper --sort-by=.metadata.creationTimestamp

# Check pods for a specific job
kubectl get pods -n match-scraper -l job-name=test-run

# Get detailed job information
kubectl describe job test-run -n match-scraper
```

### 3. View Logs

```bash
# Get the pod name for your test job
POD_NAME=$(kubectl get pods -n match-scraper -l job-name=test-run -o jsonpath='{.items[0].metadata.name}')

# View logs from the pod
kubectl logs $POD_NAME -n match-scraper

# Follow logs in real-time
kubectl logs -f $POD_NAME -n match-scraper

# View last 100 lines
kubectl logs $POD_NAME -n match-scraper --tail=100

# View logs with timestamps
kubectl logs $POD_NAME -n match-scraper --timestamps
```

### 4. Advanced Log Viewing

```bash
# View logs from all pods in the namespace
kubectl logs -l app=mls-scraper -n match-scraper

# View logs from the most recent job
kubectl logs -l job-name=test-run -n match-scraper

# Get logs from a specific time range (last 10 minutes)
kubectl logs -l job-name=test-run -n match-scraper --since=10m

# View logs and follow new ones
kubectl logs -l job-name=test-run -n match-scraper -f --tail=50
```

## Monitoring and Debugging

### 1. Check Pod Status and Events

```bash
# Get pod status
kubectl get pods -n match-scraper

# Get detailed pod information
kubectl describe pod <pod-name> -n match-scraper

# Check pod events
kubectl get events -n match-scraper --sort-by=.metadata.creationTimestamp
```

### 2. Check Resource Usage

```bash
# Check resource usage of pods
kubectl top pods -n match-scraper

# Check resource usage of nodes
kubectl top nodes
```

### 3. Debug Container Issues

```bash
# Execute commands in a running pod
kubectl exec -it <pod-name> -n match-scraper -- /bin/bash

# Check container environment variables
kubectl exec <pod-name> -n match-scraper -- env

# Check if Playwright browsers are installed
kubectl exec <pod-name> -n match-scraper -- ls -la /opt/playwright/
```

## Scheduled Job Monitoring

### 1. Check CronJob Schedule

```bash
# View CronJob details
kubectl get cronjob mls-scraper-cronjob -n match-scraper -o yaml

# Check when the next job will run
kubectl describe cronjob mls-scraper-cronjob -n match-scraper
```

### 2. View Scheduled Job History

```bash
# Get all jobs created by the CronJob
kubectl get jobs -n match-scraper -l app=mls-scraper

# Get jobs from the last 24 hours
kubectl get jobs -n match-scraper --field-selector metadata.creationTimestamp>$(date -d '24 hours ago' -u +%Y-%m-%dT%H:%M:%SZ)
```

## Log Analysis and Filtering

### 1. Filter Logs by Content

```bash
# Search for specific patterns in logs
kubectl logs -l job-name=test-run -n match-scraper | grep -i "error"
kubectl logs -l job-name=test-run -n match-scraper | grep -i "success"
kubectl logs -l job-name=test-run -n match-scraper | grep -i "scraping"

# Count log lines
kubectl logs -l job-name=test-run -n match-scraper | wc -l
```

### 2. Save Logs to File

```bash
# Save logs to a file
kubectl logs -l job-name=test-run -n match-scraper > scraper-logs.txt

# Save logs with timestamps
kubectl logs -l job-name=test-run -n match-scraper --timestamps > scraper-logs-timestamped.txt
```

## Troubleshooting Common Issues

### 1. Job Not Starting

```bash
# Check if the CronJob is active
kubectl get cronjob mls-scraper-cronjob -n match-scraper

# Check for resource constraints
kubectl describe nodes

# Check if the image exists
gcloud container images list --repository=gcr.io/missing-table
```

### 2. Pod Failing to Start

```bash
# Check pod status
kubectl get pods -n match-scraper

# Check pod events
kubectl describe pod <pod-name> -n match-scraper

# Check if secrets are properly mounted
kubectl get secret mls-scraper-secrets -n match-scraper -o yaml
```

### 3. Application Errors

```bash
# Check application logs
kubectl logs <pod-name> -n match-scraper

# Check if environment variables are set correctly
kubectl exec <pod-name> -n match-scraper -- env | grep -E "(AGE_GROUP|DIVISION|API_TOKEN)"

# Check if the API endpoint is reachable
kubectl exec <pod-name> -n match-scraper -- curl -I https://dev.missingtable.com
```

## Continuous Monitoring

### 1. Set Up Log Monitoring

```bash
# Create a monitoring script
cat > monitor-scraper.sh << 'EOF'
#!/bin/bash
while true; do
    echo "=== $(date) ==="
    kubectl get jobs -n match-scraper --sort-by=.metadata.creationTimestamp | tail -5
    echo ""
    sleep 30
done
EOF

chmod +x monitor-scraper.sh
./monitor-scraper.sh
```

### 2. Watch for New Jobs

```bash
# Watch for new jobs in real-time
kubectl get jobs -n match-scraper -w

# Watch for new pods
kubectl get pods -n match-scraper -w
```

## Cleanup Commands

### 1. Clean Up Test Jobs

```bash
# Delete a specific test job
kubectl delete job test-run -n match-scraper

# Delete all test jobs
kubectl delete jobs -n match-scraper -l job-name=test-run

# Delete all jobs (be careful!)
kubectl delete jobs -n match-scraper --all
```

### 2. Clean Up Pods

```bash
# Delete completed pods
kubectl delete pods -n match-scraper --field-selector=status.phase=Succeeded

# Delete failed pods
kubectl delete pods -n match-scraper --field-selector=status.phase=Failed
```

## Best Practices

1. **Always test with manual jobs** before relying on the scheduled CronJob
2. **Monitor resource usage** to ensure your cluster can handle the workload
3. **Check logs regularly** to catch issues early
4. **Use descriptive job names** with timestamps for easy identification
5. **Clean up test jobs** to avoid clutter
6. **Save important logs** for debugging and analysis

## Quick Reference

| Action | Command |
|--------|---------|
| Create test job | `kubectl create job --from=cronjob/mls-scraper-cronjob test-run -n match-scraper` |
| Check job status | `kubectl get jobs -n match-scraper` |
| View logs | `kubectl logs -l job-name=test-run -n match-scraper` |
| Monitor real-time | `kubectl get pods -n match-scraper -w` |
| Clean up | `kubectl delete job test-run -n match-scraper` |
