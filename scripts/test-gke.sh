#!/bin/bash

# Test MLS Match Scraper on GKE
# Usage: ./scripts/test-gke.sh [action]
# Actions: trigger, logs, status, cleanup

set -e

ACTION=${1:-"trigger"}
NAMESPACE="match-scraper"
JOB_NAME="test-run"

case $ACTION in
    "trigger")
        echo "🚀 Triggering test run of MLS Match Scraper..."
        kubectl create job --from=cronjob/mls-scraper-cronjob "$JOB_NAME" -n "$NAMESPACE"
        echo "✅ Test job created: $JOB_NAME"
        echo "Monitor with: $0 status"
        ;;
    "status")
        echo "📊 Checking job status..."
        echo ""
        echo "=== CronJob Status ==="
        kubectl get cronjob -n "$NAMESPACE"
        echo ""
        echo "=== Recent Jobs ==="
        kubectl get jobs -n "$NAMESPACE" --sort-by=.metadata.creationTimestamp
        echo ""
        echo "=== Test Job Pods ==="
        kubectl get pods -n "$NAMESPACE" -l job-name="$JOB_NAME"
        ;;
    "logs")
        echo "📋 Fetching logs from test run..."
        POD_NAME=$(kubectl get pods -n "$NAMESPACE" -l job-name="$JOB_NAME" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

        if [ -z "$POD_NAME" ]; then
            echo "❌ No test job pod found. Run '$0 trigger' first."
            exit 1
        fi

        echo "Pod: $POD_NAME"
        echo "=== Recent Logs ==="
        kubectl logs "$POD_NAME" -n "$NAMESPACE" --tail=50
        ;;
    "cleanup")
        echo "🧹 Cleaning up test job..."
        kubectl delete job "$JOB_NAME" -n "$NAMESPACE" --ignore-not-found=true
        echo "✅ Test job cleaned up"
        ;;
    "monitor")
        echo "👀 Monitoring job progress..."
        while true; do
            clear
            echo "=== MLS Match Scraper Test Monitor ==="
            echo "Time: $(date)"
            echo ""
            $0 status
            echo ""
            echo "Press Ctrl+C to stop monitoring"
            sleep 5
        done
        ;;
    *)
        echo "Usage: $0 [action]"
        echo ""
        echo "Actions:"
        echo "  trigger  - Create and start a test job"
        echo "  status   - Show job and pod status"
        echo "  logs     - Show logs from the test job"
        echo "  cleanup  - Remove the test job"
        echo "  monitor  - Continuously monitor job progress"
        echo ""
        echo "Examples:"
        echo "  $0 trigger    # Start a test run"
        echo "  $0 status     # Check status"
        echo "  $0 logs       # View logs"
        echo "  $0 cleanup    # Clean up test job"
        ;;
esac
