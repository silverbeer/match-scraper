#!/bin/bash
#
# Test and monitor match-scraper deployment in k3s
#
# Usage:
#   ./scripts/test-k3s.sh trigger [options]  # Trigger a manual job
#   ./scripts/test-k3s.sh status             # Check CronJob and job status
#   ./scripts/test-k3s.sh logs [-f]          # View logs from most recent job
#   ./scripts/test-k3s.sh workers [-f]       # View Celery worker logs
#   ./scripts/test-k3s.sh cleanup            # Delete test jobs
#   ./scripts/test-k3s.sh rabbitmq           # Check RabbitMQ status
#
# Trigger Options:
#   --age-group, -a     Age group (default: U14)
#   --division, -d      Division (default: Northeast)
#   --club, -c          Club name filter (e.g., IFA)
#   --from             Start date YYYY-MM-DD
#   --to               End date YYYY-MM-DD
#   --start            Days backward from today (0=today, 1=yesterday)
#   --end              Days forward from today (0=today, 1=tomorrow)
#   --queue            Target specific queue (matches.dev or matches.prod)
#   --exchange         Use custom exchange (default: matches-fanout for both envs)
#
# Examples:
#   ./scripts/test-k3s.sh trigger                                    # Default: fanout to BOTH dev and prod
#   ./scripts/test-k3s.sh trigger -a U13 -d Northeast                # U13 Northeast (both envs)
#   ./scripts/test-k3s.sh trigger --queue matches.dev                # Target dev only
#   ./scripts/test-k3s.sh trigger --queue matches.prod               # Target prod only
#   ./scripts/test-k3s.sh trigger -a U13 -d Northeast --club IFA     # U13 Northeast IFA (both envs)
#   ./scripts/test-k3s.sh trigger --from 2025-10-16 --to 2025-10-20  # Specific dates
#   ./scripts/test-k3s.sh trigger --start 7 --end 0                  # Last 7 days
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
    echo "Usage: $0 {trigger|status|logs|workers|cleanup|rabbitmq} [options]"
    echo ""
    echo "Commands:"
    echo "  trigger [options]  - Trigger a manual test job with custom parameters"
    echo "  status             - Check CronJob and job status"
    echo "  logs [-f]          - View logs from most recent scraper job (-f to follow)"
    echo "  workers [-f]       - View logs from Celery workers (-f to follow)"
    echo "  cleanup            - Delete all test jobs"
    echo "  rabbitmq           - Check RabbitMQ status and queues"
    echo ""
    echo "Trigger Options:"
    echo "  --age-group, -a <group>    Age group (U13-U19, default: U14)"
    echo "  --division, -d <div>       Division (default: Northeast)"
    echo "  --club, -c <name>          Club name filter (e.g., IFA)"
    echo "  --from <YYYY-MM-DD>        Start date"
    echo "  --to <YYYY-MM-DD>          End date"
    echo "  --start <days>             Days backward from today"
    echo "  --end <days>               Days forward from today"
    echo "  --queue <name>             Target specific queue (matches.dev or matches.prod)"
    echo "  --exchange <name>          Use custom exchange (default: matches-fanout)"
    echo ""
    echo "Logs/Workers Options:"
    echo "  -f, --follow               Follow logs in real-time (Ctrl+C to exit)"
    echo ""
    echo "Examples:"
    echo "  $0 trigger -a U13 -d Northeast              # Fanout to both dev and prod"
    echo "  $0 trigger --queue matches.dev              # Target dev only"
    echo "  $0 trigger --queue matches.prod             # Target prod only"
    echo "  $0 trigger -a U13 -d Northeast --club IFA"
    echo "  $0 trigger --from 2025-10-16 --to 2025-10-20"
    echo "  $0 logs -f"
    echo "  $0 workers -f"
    exit 1
fi

COMMAND=$1
shift  # Remove command from arguments

case $COMMAND in
    trigger)
        # Parse trigger options
        AGE_GROUP="U14"
        DIVISION="Northeast"
        CLUB_NAME=""
        FROM_DATE=""
        TO_DATE=""
        START_OFFSET=""
        END_OFFSET=""
        QUEUE_NAME=""
        EXCHANGE_NAME=""

        while [[ $# -gt 0 ]]; do
            case $1 in
                --age-group|-a)
                    AGE_GROUP="$2"
                    shift 2
                    ;;
                --division|-d)
                    DIVISION="$2"
                    shift 2
                    ;;
                --club|-c)
                    CLUB_NAME="$2"
                    shift 2
                    ;;
                --from)
                    FROM_DATE="$2"
                    shift 2
                    ;;
                --to)
                    TO_DATE="$2"
                    shift 2
                    ;;
                --start)
                    START_OFFSET="$2"
                    shift 2
                    ;;
                --end)
                    END_OFFSET="$2"
                    shift 2
                    ;;
                --queue)
                    QUEUE_NAME="$2"
                    shift 2
                    ;;
                --exchange)
                    EXCHANGE_NAME="$2"
                    shift 2
                    ;;
                *)
                    echo -e "${RED}Unknown option: $1${NC}"
                    exit 1
                    ;;
            esac
        done

        echo -e "${YELLOW}🚀 Triggering manual job...${NC}"
        echo -e "${BLUE}Age Group:${NC} $AGE_GROUP"
        echo -e "${BLUE}Division:${NC} $DIVISION"
        if [ -n "$CLUB_NAME" ]; then
            echo -e "${BLUE}Club Filter:${NC} $CLUB_NAME"
        fi

        # Determine routing target
        if [ -n "$QUEUE_NAME" ]; then
            echo -e "${BLUE}Target:${NC} Queue '$QUEUE_NAME' only"
        elif [ -n "$EXCHANGE_NAME" ]; then
            echo -e "${BLUE}Target:${NC} Exchange '$EXCHANGE_NAME'"
        else
            echo -e "${BLUE}Target:${NC} Fanout to BOTH dev and prod (default)"
        fi

        # Build args array
        ARGS=("--age-group" "$AGE_GROUP" "--division" "$DIVISION" "--submit-queue")

        if [ -n "$CLUB_NAME" ]; then
            ARGS+=("--club" "$CLUB_NAME")
        fi

        if [ -n "$QUEUE_NAME" ]; then
            ARGS+=("--queue" "$QUEUE_NAME")
        elif [ -n "$EXCHANGE_NAME" ]; then
            ARGS+=("--exchange" "$EXCHANGE_NAME")
        fi

        if [ -n "$FROM_DATE" ] && [ -n "$TO_DATE" ]; then
            echo -e "${BLUE}Date Range:${NC} $FROM_DATE to $TO_DATE"
            ARGS+=("--from" "$FROM_DATE" "--to" "$TO_DATE")
        elif [ -n "$START_OFFSET" ] && [ -n "$END_OFFSET" ]; then
            echo -e "${BLUE}Offset Range:${NC} -$START_OFFSET days to +$END_OFFSET days"
            ARGS+=("--start" "$START_OFFSET" "--end" "$END_OFFSET")
        fi

        # Create job name
        JOB_NAME="manual-$(echo $AGE_GROUP | tr '[:upper:]' '[:lower:]')-$(date +%s)"

        # Create job manifest
        cat <<EOF | kubectl apply -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: $JOB_NAME
  namespace: $NAMESPACE
spec:
  template:
    metadata:
      labels:
        app: match-scraper
    spec:
      restartPolicy: Never
      containers:
      - name: scraper
        image: match-scraper:latest
        imagePullPolicy: Never
        command: ["uv", "run", "mls-scraper", "scrape"]
        args: $(printf '%s\n' "${ARGS[@]}" | jq -R . | jq -s .)
        env:
        - name: RABBITMQ_URL
          value: "amqp://admin:admin123@messaging-rabbitmq.match-scraper:5672//"
        - name: NO_COLOR
          value: "1"
        # Note: Don't set KUBERNETES_SERVICE_HOST for manual jobs
        # This avoids permission warnings when trying to write to /var/log/scraper
        # Production cronjob gets this automatically from k8s
EOF

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

        # Check for -f flag
        FOLLOW_LOGS=false
        if [ "$1" == "-f" ] || [ "$1" == "--follow" ]; then
            FOLLOW_LOGS=true
        fi

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

        if [ "$FOLLOW_LOGS" = true ]; then
            echo -e "${BLUE}Following logs (Ctrl+C to exit):${NC}"
            echo "─────────────────────────────────────────────────────────────"
            kubectl logs "$POD_NAME" -n "$NAMESPACE" --tail=200 -f
        else
            echo -e "${BLUE}Logs:${NC}"
            echo "─────────────────────────────────────────────────────────────"
            kubectl logs "$POD_NAME" -n "$NAMESPACE" --tail=200
            echo ""
            echo -e "${YELLOW}💡 Tip: Use './scripts/test-k3s.sh logs -f' to follow logs in real-time${NC}"
        fi
        ;;

    workers)
        echo -e "${YELLOW}📋 Fetching Celery worker logs...${NC}"
        echo ""

        # Check for -f flag
        FOLLOW_LOGS=false
        if [ "$1" == "-f" ] || [ "$1" == "--follow" ]; then
            FOLLOW_LOGS=true
        fi

        # Get worker pods
        WORKER_PODS=$(kubectl get pods -n "$NAMESPACE" -l app=missing-table-worker -o jsonpath='{.items[*].metadata.name}' 2>/dev/null)

        if [ -z "$WORKER_PODS" ]; then
            echo -e "${RED}❌ No worker pods found${NC}"
            echo "Deploy workers from missing-table repo first"
            exit 1
        fi

        echo -e "${BLUE}Worker Pods:${NC}"
        kubectl get pods -n "$NAMESPACE" -l app=missing-table-worker
        echo ""

        if [ "$FOLLOW_LOGS" = true ]; then
            echo -e "${BLUE}Following worker logs (Ctrl+C to exit):${NC}"
            echo "─────────────────────────────────────────────────────────────"
            kubectl logs -n "$NAMESPACE" -l app=missing-table-worker --tail=100 -f --prefix=true
        else
            echo -e "${BLUE}Worker Logs:${NC}"
            echo "─────────────────────────────────────────────────────────────"
            kubectl logs -n "$NAMESPACE" -l app=missing-table-worker --tail=100 --prefix=true
            echo ""
            echo -e "${YELLOW}💡 Tip: Use './scripts/test-k3s.sh workers -f' to follow worker logs in real-time${NC}"
        fi
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

        echo -e "${BLUE}Exchanges:${NC}"
        kubectl exec -n "$NAMESPACE" "$RABBITMQ_POD" -- rabbitmqctl list_exchanges name type | grep -E "(name|matches)"
        echo ""

        echo -e "${BLUE}Queue Status:${NC}"
        kubectl exec -n "$NAMESPACE" "$RABBITMQ_POD" -- rabbitmqctl list_queues name messages consumers | grep -E "(name|matches)"
        echo ""

        echo -e "${BLUE}Exchange Bindings:${NC}"
        kubectl exec -n "$NAMESPACE" "$RABBITMQ_POD" -- rabbitmqctl list_bindings | grep matches-fanout || echo "  (No fanout bindings found)"
        echo ""

        echo -e "${BLUE}Architecture:${NC}"
        echo "  Scraper → matches-fanout exchange"
        echo "            ├→ matches.prod queue → Prod Workers → Prod Supabase"
        echo "            └→ matches.dev queue  → Dev Workers  → Dev Supabase"
        echo ""

        echo -e "${BLUE}Management UI:${NC}"
        echo "  URL: http://localhost:30672"
        echo "  Username: admin"
        echo "  Password: admin123"
        echo ""

        echo -e "${BLUE}Connection Info:${NC}"
        echo "  Internal: amqp://admin:admin123@messaging-rabbitmq.messaging.svc.cluster.local:5672//"
        ;;

    *)
        echo -e "${RED}❌ Unknown command: $COMMAND${NC}"
        echo "Usage: $0 {trigger|status|logs|workers|cleanup|rabbitmq}"
        exit 1
        ;;
esac
