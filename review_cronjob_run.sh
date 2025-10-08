#!/bin/bash
# Match Scraper CronJob Run Diagnostic Script
# Reviews the latest scheduled run (6am UTC) and provides detailed diagnostics

set -e

echo "🔍 Match Scraper CronJob Diagnostic Report"
echo "=========================================="
echo ""
echo "📅 Current time: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo -e "${RED}❌ kubectl not found. Please install kubectl to continue.${NC}"
    exit 1
fi

# Check GKE cluster connectivity
echo "🔗 Checking cluster connectivity..."
if ! kubectl cluster-info &> /dev/null; then
    echo -e "${RED}❌ Not connected to GKE cluster. Please authenticate first:${NC}"
    echo "   gcloud container clusters get-credentials [CLUSTER_NAME] --region [REGION]"
    exit 1
fi
echo -e "${GREEN}✅ Connected to cluster${NC}"
echo ""

# Check namespace
NAMESPACE="match-scraper"
echo "📦 Checking namespace: $NAMESPACE"
if ! kubectl get namespace $NAMESPACE &> /dev/null; then
    echo -e "${RED}❌ Namespace $NAMESPACE not found${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Namespace exists${NC}"
echo ""

# Get CronJob status
echo "⏰ CronJob Status:"
echo "===================="
kubectl get cronjob -n $NAMESPACE mls-scraper-cronjob -o custom-columns=\
NAME:.metadata.name,\
SCHEDULE:.spec.schedule,\
SUSPEND:.spec.suspend,\
ACTIVE:.status.active,\
LAST_SCHEDULE:.status.lastScheduleTime,\
LAST_SUCCESS:.status.lastSuccessfulTime
echo ""

# List recent jobs (spawned by CronJob)
echo "📋 Recent Jobs (last 10):"
echo "===================="
kubectl get jobs -n $NAMESPACE --sort-by=.metadata.creationTimestamp -o custom-columns=\
NAME:.metadata.name,\
COMPLETIONS:.spec.completions,\
SUCCESSFUL:.status.succeeded,\
FAILED:.status.failed,\
AGE:.metadata.creationTimestamp | tail -11
echo ""

# Get the most recent job
LATEST_JOB=$(kubectl get jobs -n $NAMESPACE --sort-by=.metadata.creationTimestamp -o name | tail -1)

if [ -z "$LATEST_JOB" ]; then
    echo -e "${YELLOW}⚠️  No jobs found. CronJob may not have run yet.${NC}"
    exit 0
fi

JOB_NAME=$(echo $LATEST_JOB | cut -d'/' -f2)
echo -e "${BLUE}🎯 Analyzing latest job: $JOB_NAME${NC}"
echo ""

# Get job details
echo "📊 Job Details:"
echo "===================="
kubectl get job -n $NAMESPACE $JOB_NAME -o yaml | grep -A 20 "^status:" || true
echo ""

# Get pod status for this job
echo "🐳 Pod Status:"
echo "===================="
PODS=$(kubectl get pods -n $NAMESPACE -l job-name=$JOB_NAME --sort-by=.metadata.creationTimestamp -o name)

if [ -z "$PODS" ]; then
    echo -e "${YELLOW}⚠️  No pods found for job $JOB_NAME${NC}"
else
    for POD in $PODS; do
        POD_NAME=$(echo $POD | cut -d'/' -f2)
        echo -e "${BLUE}Pod: $POD_NAME${NC}"
        kubectl get pod -n $NAMESPACE $POD_NAME -o custom-columns=\
STATUS:.status.phase,\
RESTARTS:.status.containerStatuses[*].restartCount,\
READY:.status.containerStatuses[*].ready,\
STARTED:.status.startTime
        echo ""

        # Container statuses
        echo "  Container Statuses:"
        kubectl get pod -n $NAMESPACE $POD_NAME -o jsonpath='{range .status.containerStatuses[*]}  - {.name}: {.state}{"\n"}{end}' 2>/dev/null || echo "  (Unable to get container statuses)"
        echo ""

        # Init container statuses
        echo "  Init Container Statuses:"
        kubectl get pod -n $NAMESPACE $POD_NAME -o jsonpath='{range .status.initContainerStatuses[*]}  - {.name}: {.state}{"\n"}{end}' 2>/dev/null || echo "  (No init containers or unable to get status)"
        echo ""
    done
fi

# Get logs from the most recent pod
echo "📝 Container Logs:"
echo "===================="
LATEST_POD=$(kubectl get pods -n $NAMESPACE -l job-name=$JOB_NAME --sort-by=.metadata.creationTimestamp -o name | tail -1)

if [ -n "$LATEST_POD" ]; then
    LATEST_POD_NAME=$(echo $LATEST_POD | cut -d'/' -f2)
    echo -e "${BLUE}Logs from pod: $LATEST_POD_NAME${NC}"
    echo ""

    # Check if pod is ready for logs
    POD_PHASE=$(kubectl get pod -n $NAMESPACE $LATEST_POD_NAME -o jsonpath='{.status.phase}')

    echo "--- Init Container: config-preprocessor ---"
    kubectl logs -n $NAMESPACE $LATEST_POD_NAME -c config-preprocessor --tail=50 2>&1 || echo "(No logs available)"
    echo ""

    echo "--- Main Container: mls-scraper ---"
    kubectl logs -n $NAMESPACE $LATEST_POD_NAME -c mls-scraper --tail=100 2>&1 || echo "(No logs available yet)"
    echo ""

    echo "--- Sidecar Container: promtail ---"
    kubectl logs -n $NAMESPACE $LATEST_POD_NAME -c promtail --tail=30 2>&1 || echo "(No logs available)"
    echo ""
else
    echo -e "${YELLOW}⚠️  No pods available to fetch logs from${NC}"
fi

# Events related to the job/pod
echo "📢 Recent Events:"
echo "===================="
kubectl get events -n $NAMESPACE --sort-by='.lastTimestamp' --field-selector involvedObject.name=$JOB_NAME 2>&1 | tail -20 || echo "(No events found)"
echo ""

# Check for any pod events
if [ -n "$LATEST_POD_NAME" ]; then
    echo "Pod Events for $LATEST_POD_NAME:"
    kubectl get events -n $NAMESPACE --sort-by='.lastTimestamp' --field-selector involvedObject.name=$LATEST_POD_NAME 2>&1 | tail -20 || echo "(No events found)"
fi
echo ""

# Summary
echo "📊 Summary & Next Steps:"
echo "===================="
JOB_STATUS=$(kubectl get job -n $NAMESPACE $JOB_NAME -o jsonpath='{.status.conditions[0].type}' 2>/dev/null || echo "Unknown")

if [ "$JOB_STATUS" == "Complete" ]; then
    echo -e "${GREEN}✅ Job completed successfully${NC}"
elif [ "$JOB_STATUS" == "Failed" ]; then
    echo -e "${RED}❌ Job failed - review logs above for errors${NC}"
    echo ""
    echo "Common issues to check:"
    echo "  1. Image pull errors (check imagePullPolicy and image tag)"
    echo "  2. Missing secrets or config maps"
    echo "  3. Application errors in mls-scraper container logs"
    echo "  4. Init container failures (config-preprocessor)"
    echo "  5. Resource limits (OOMKilled)"
else
    echo -e "${YELLOW}⚠️  Job status: $JOB_STATUS${NC}"
    echo "   Job may still be running or in unknown state"
fi

echo ""
echo "🔧 Useful Commands:"
echo "===================="
echo "  # Watch job in real-time:"
echo "  kubectl get jobs -n $NAMESPACE -w"
echo ""
echo "  # Describe the job for more details:"
echo "  kubectl describe job -n $NAMESPACE $JOB_NAME"
echo ""
echo "  # Follow logs from latest pod:"
echo "  kubectl logs -n $NAMESPACE $LATEST_POD_NAME -c mls-scraper -f"
echo ""
echo "  # Delete failed job to trigger retry:"
echo "  kubectl delete job -n $NAMESPACE $JOB_NAME"
echo ""
echo "  # Manually trigger a test run:"
echo "  kubectl create job --from=cronjob/mls-scraper-cronjob -n $NAMESPACE test-run-\$(date +%s)"
echo ""
