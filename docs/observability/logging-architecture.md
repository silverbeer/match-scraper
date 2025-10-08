# Match Scraper Logging Architecture

## Current Setup

### ✅ What You Have (Verified)

**1. GKE Native Logging (FluentBit)**
- **DaemonSet**: `fluentbit-gke-big` in `kube-system` namespace
- **Purpose**: Ships container stdout/stderr logs to Google Cloud Logging
- **Coverage**: Automatic for all pods in the cluster

**2. Promtail DaemonSet (Custom)**
- **Location**: `monitoring` namespace
- **DaemonSet**: `promtail` (2 pods running)
- **Purpose**: Ships logs to Grafana Loki (logs-prod-036.grafana.net)
- **Source**: Reads from `/var/log/pods/` on each node
- **Configuration**: Scrapes all Kubernetes pods using `kubernetes-pods` job
- **Verified**: Successfully collecting match-scraper pod logs

### 📋 Log Flow

```
match-scraper CronJob Pod
  └─> mls-scraper container writes JSON logs to stdout/stderr
       │
       ├─> Kubernetes captures logs to /var/log/pods/match-scraper_<pod-name>_<uid>/<container>/*.log
       │
       ├─> Promtail DaemonSet (monitoring namespace)
       │    └─> Reads from /var/log/pods/
       │    └─> Ships to Grafana Loki
       │    └─> ✅ WORKING (verified pod logs are visible)
       │
       └─> FluentBit DaemonSet (kube-system)
            └─> Ships to GCP Cloud Logging
            └─> ✅ WORKING (GKE default)
```

## ❌ The Problem: Promtail Sidecar in CronJob

**Current CronJob Configuration** (k8s/cronjob.yaml):
- Init container: `config-preprocessor` (prepares promtail config)
- Main container: `mls-scraper` (runs scraper, exits after completion)
- Sidecar container: `promtail` (stays running indefinitely)

**Issue**:
The promtail **sidecar** in the CronJob pod is **redundant** and **causes the job to hang**:
1. Main container finishes (exitCode: 0)
2. Promtail sidecar keeps running (waiting for more logs)
3. Kubernetes won't mark the job "Complete" until ALL containers exit
4. Job status stays "ACTIVE" forever
5. CronJob history shows job never completed
6. Grafana metrics show no successful runs

## ✅ Your Understanding is CORRECT

> "match-scraper runs as a CronJob, it produces json logs to stdout/stderr.
> A daemonset process running on the nodes in GKE will pick up the logs
> and ship to grafana/loki"

**YES! This is exactly correct.**

The **Promtail DaemonSet** in the `monitoring` namespace:
- Runs on every node (2/2 pods running)
- Automatically discovers all pods via Kubernetes service discovery
- Reads logs from `/var/log/pods/match-scraper_*/`
- Ships them to your Grafana Loki instance
- **Already working** - verified it has access to match-scraper logs

## ✅ Recommended Fix: Remove Promtail Sidecar

### Why This is Safe:

1. **Promtail DaemonSet already collects your logs**
   - It reads from `/var/log/pods/` where Kubernetes writes container logs
   - No sidecar needed

2. **GKE FluentBit also collects your logs**
   - Backup logging to GCP Cloud Logging
   - Useful for disaster recovery

3. **Sidecar pattern doesn't work for Jobs**
   - Sidecars are for long-running processes (Deployments, StatefulSets)
   - Jobs need all containers to terminate

### What to Remove from k8s/cronjob.yaml:

**Lines to delete:**
1. Init container `config-preprocessor` (lines 23-47)
2. Sidecar container `promtail` (lines 154-170)
3. Volume mounts for promtail in mls-scraper (lines 133-135)
4. Volumes: `promtail-config` and `promtail-processed` (lines 175-179)
5. Volume: `logs` emptyDir (lines 173-174) - no longer needed

**Result:**
- CronJob pod will have only the `mls-scraper` container
- It writes JSON logs to stdout/stderr
- Promtail DaemonSet picks them up from `/var/log/pods/`
- Job completes when mls-scraper exits
- Grafana metrics show successful runs

## 🔧 Implementation Steps

1. **Backup current config**
   ```bash
   kubectl get cronjob -n match-scraper mls-scraper-cronjob -o yaml > cronjob-backup.yaml
   ```

2. **Kill stuck job** (quick fix)
   ```bash
   kubectl delete job -n match-scraper mls-scraper-cronjob-29331720
   ```

3. **Edit k8s/cronjob.yaml** - Remove sections mentioned above

4. **Apply updated config**
   ```bash
   kubectl apply -f k8s/cronjob.yaml
   ```

5. **Verify next run completes**
   ```bash
   # Wait for next scheduled run (6am UTC) or trigger manually:
   kubectl create job --from=cronjob/mls-scraper-cronjob -n match-scraper test-run-$(date +%s)

   # Watch job complete:
   kubectl get jobs -n match-scraper -w
   ```

6. **Check Grafana dashboards**
   - Logs should still appear in Loki (via DaemonSet)
   - Metrics should show successful job completion

## 🎯 Summary

| Component | Status | Ships Logs To | Notes |
|-----------|--------|---------------|-------|
| Promtail DaemonSet (monitoring) | ✅ Working | Grafana Loki | Collects from /var/log/pods/ |
| FluentBit DaemonSet (kube-system) | ✅ Working | GCP Cloud Logging | GKE default |
| Promtail Sidecar (CronJob pod) | ❌ Remove | N/A | Redundant, causes job to hang |

**Your understanding is 100% correct** - the DaemonSet handles log shipping, making the sidecar unnecessary.
