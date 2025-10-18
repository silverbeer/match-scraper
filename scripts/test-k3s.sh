#!/bin/bash
#
# Test and monitor match-scraper deployment in k3s
#
# Usage:
#   ./scripts/test-k3s.sh trigger    # Trigger a manual job
#   ./scripts/test-k3s.sh status     # Check CronJob and job status
#   ./scripts/test-k3s.sh logs       # View logs from most recent job
#   ./scripts/test-k3s.sh cleanup    # Delete test jobs
#   ./scripts/test-k3s.sh rabbitmq   # Check RabbitMQ status
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

NAMESPACE="match-scraper"
CRONJOB_NAME="match-scraper-cronjob"

# Show usage if no command provided
if [ $# -eq 0 ]; then
    echo "Usage: $0 {trigger|status|logs|cleanup|rabbitmq}"
    echo ""
    echo "Commands:"
    echo "  trigger   - Trigger a manual test job"
    echo "  status    - Check CronJob and job status"
    echo "  logs      - View logs from most recent job"
    echo "  cleanup   - Delete all test jobs"
    echo "  rabbitmq  - Check RabbitMQ status and queues"
    exit 1
fi

COMMAND=$1

case $COMMAND in
    trigger)
        echo -e "${YELLOW}🚀 Triggering manual job...${NC}"
        JOB_NAME="test-run-$(date +%s)"
        kubectl create job --from=cronjob/$CRONJOB_NAME "$JOB_NAME" -n "$NAMESPACE"

        echo -e "${GREEN}✅ Job created: $JOB_NAME${NC}"
        echo ""
        echo "Monitor with:"
        echo "  kubectl logs -n $NAMESPACE -l job-name=$JOB_NAME --tail=100 -f"
        echo ""
        echo "Or run: ./scripts/test-k3s.sh logs"
        ;;

    status)
        echo -e "${BLUE}📋 CronJob Status:${NC}"
        kubectl get cronjob -n "$NAMESPACE"
        echo ""

        echo -e "${BLUE}📦 Recent Jobs:${NC}"
        kubectl get jobs -n "$NAMESPACE" --sort-by=.metadata.creationTimestamp
        echo ""

        echo -e "${BLUE}🔧 Pods:${NC}"
        kubectl get pods -n "$NAMESPACE" -l app=match-scraper
        echo ""

        # Show next scheduled run
        NEXT_SCHEDULE=$(kubectl get cronjob $CRONJOB_NAME -n "$NAMESPACE" -o jsonpath='{.status.lastScheduleTime}')
        if [ -n "$NEXT_SCHEDULE" ]; then
            echo -e "${BLUE}📅 Last Scheduled:${NC} $NEXT_SCHEDULE"
        fi
        ;;

    logs)
        echo -e "${YELLOW}📋 Fetching logs from most recent job...${NC}"
        echo ""

        # Get most recent job
        LATEST_JOB=$(kubectl get jobs -n "$NAMESPACE" -l app=match-scraper --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1].metadata.name}' 2>/dev/null)

        if [ -z "$LATEST_JOB" ]; then
            echo -e "${RED}❌ No jobs found${NC}"
            echo "Trigger a job first with: ./scripts/test-k3s.sh trigger"
            exit 1
        fi

        echo -e "${BLUE}Job:${NC} $LATEST_JOB"
        echo ""

        # Get pod for the job
        POD_NAME=$(kubectl get pods -n "$NAMESPACE" -l job-name="$LATEST_JOB" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

        if [ -z "$POD_NAME" ]; then
            echo -e "${RED}❌ No pod found for job $LATEST_JOB${NC}"
            exit 1
        fi

        echo -e "${BLUE}Pod:${NC} $POD_NAME"
        echo -e "${BLUE}Status:${NC}"
        kubectl get pod "$POD_NAME" -n "$NAMESPACE"
        echo ""

        echo -e "${BLUE}Logs:${NC}"
        echo "─────────────────────────────────────────────────────────────"
        kubectl logs "$POD_NAME" -n "$NAMESPACE" --tail=200
        ;;

    cleanup)
        echo -e "${YELLOW}🗑️  Cleaning up test jobs...${NC}"

        # Delete jobs that start with "test-run-"
        JOBS=$(kubectl get jobs -n "$NAMESPACE" -o jsonpath='{.items[?(@.metadata.name matches "test-run-.*")].metadata.name}')

        if [ -z "$JOBS" ]; then
            echo -e "${YELLOW}No test jobs to clean up${NC}"
            exit 0
        fi

        for JOB in $JOBS; do
            echo -e "  Deleting: $JOB"
            kubectl delete job "$JOB" -n "$NAMESPACE"
        done

        echo -e "${GREEN}✅ Cleanup complete${NC}"
        ;;

    rabbitmq)
        echo -e "${BLUE}🐰 RabbitMQ Status:${NC}"
        kubectl get pods -n "$NAMESPACE" -l app=rabbitmq
        echo ""

        echo -e "${BLUE}Services:${NC}"
        kubectl get svc -n "$NAMESPACE" -l app=rabbitmq
        echo ""

        # Check if RabbitMQ pod is running
        RABBITMQ_POD=$(kubectl get pods -n "$NAMESPACE" -l app=rabbitmq -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

        if [ -z "$RABBITMQ_POD" ]; then
            echo -e "${RED}❌ RabbitMQ pod not found${NC}"
            exit 1
        fi

        echo -e "${BLUE}Queue Status:${NC}"
        echo "Checking queues..."
        kubectl exec -n "$NAMESPACE" "$RABBITMQ_POD" -- rabbitmqctl list_queues name messages consumers
        echo ""

        echo -e "${BLUE}Management UI:${NC}"
        echo "  URL: http://localhost:30672"
        echo "  Username: admin"
        echo "  Password: admin123"
        echo ""

        echo -e "${BLUE}Connection Info:${NC}"
        echo "  Internal: amqp://admin:admin123@rabbitmq.match-scraper:5672//"
        ;;

    *)
        echo -e "${RED}❌ Unknown command: $COMMAND${NC}"
        echo "Usage: $0 {trigger|status|logs|cleanup|rabbitmq}"
        exit 1
        ;;
esac
