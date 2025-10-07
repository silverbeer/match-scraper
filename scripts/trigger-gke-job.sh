#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
NAMESPACE="match-scraper"
AGE_GROUP="U14"
DIVISION="Northeast"
START="0"
END="13"
FROM_DATE=""
TO_DATE=""
FOLLOW_LOGS=true

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --start=*)
            START="${1#*=}"
            shift
            ;;
        --start)
            START="$2"
            shift 2
            ;;
        --end=*)
            END="${1#*=}"
            shift
            ;;
        --end)
            END="$2"
            shift 2
            ;;
        --age-group=*)
            AGE_GROUP="${1#*=}"
            shift
            ;;
        --age-group)
            AGE_GROUP="$2"
            shift 2
            ;;
        --division=*)
            DIVISION="${1#*=}"
            shift
            ;;
        --division)
            DIVISION="$2"
            shift 2
            ;;
        --namespace=*)
            NAMESPACE="${1#*=}"
            shift
            ;;
        --namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        --from=*)
            FROM_DATE="${1#*=}"
            shift
            ;;
        --from)
            FROM_DATE="$2"
            shift 2
            ;;
        --to=*)
            TO_DATE="${1#*=}"
            shift
            ;;
        --to)
            TO_DATE="$2"
            shift 2
            ;;
        --no-follow)
            FOLLOW_LOGS=false
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --start N           Start date offset (default: 0 = today)"
            echo "  --end N             End date offset (default: 13)"
            echo "  --from DATE         Absolute start date (YYYY-MM-DD, e.g., 2025-10-01)"
            echo "  --to DATE           Absolute end date (YYYY-MM-DD, e.g., 2025-11-01)"
            echo "  --age-group GROUP   Age group (default: U14)"
            echo "  --division DIV      Division (default: Northeast)"
            echo "  --namespace NS      Kubernetes namespace (default: match-scraper)"
            echo "  --no-follow         Don't follow logs after job creation"
            echo "  -h, --help          Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0 --start 0 --end 13"
            echo "  $0 --start -7 --end 0  # Last 7 days"
            echo "  $0 --from 2025-10-01 --to 2025-11-01  # Absolute dates"
            echo "  $0 --age-group U16 --division Southeast"
            exit 0
            ;;
        *)
            echo -e "${RED}Error: Unknown option $1${NC}"
            exit 1
            ;;
    esac
done

# Generate unique job name
JOB_NAME="manual-scraper-$(date +%Y%m%d-%H%M%S)"

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║${NC}  ${GREEN}MLS Match Scraper - Manual Job Trigger${NC}                   ${BLUE}║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}Configuration:${NC}"
echo -e "  Job Name:    ${GREEN}${JOB_NAME}${NC}"
echo -e "  Namespace:   ${GREEN}${NAMESPACE}${NC}"
echo -e "  Age Group:   ${GREEN}${AGE_GROUP}${NC}"
echo -e "  Division:    ${GREEN}${DIVISION}${NC}"
if [ -n "$FROM_DATE" ] && [ -n "$TO_DATE" ]; then
    echo -e "  Date Range:  ${GREEN}--from=${FROM_DATE} --to=${TO_DATE}${NC}"
else
    echo -e "  Date Range:  ${GREEN}--start=${START} --end=${END}${NC}"
fi
echo ""

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo -e "${RED}Error: kubectl not found. Please install kubectl first.${NC}"
    exit 1
fi

# Check if cluster is accessible
if ! kubectl cluster-info &> /dev/null; then
    echo -e "${RED}Error: Cannot connect to Kubernetes cluster.${NC}"
    echo -e "${YELLOW}Hint: Make sure you're authenticated to GKE:${NC}"
    echo "  gcloud container clusters get-credentials CLUSTER_NAME --region REGION"
    exit 1
fi

# Get the project ID
PROJECT_ID=$(gcloud config get-value project 2>/dev/null || echo "missing-table")

# Build the CLI command with appropriate date flags
# Note: Rich CLI output goes to stdout/stderr for terminal visibility
# Structured JSON logs are written to /var/log/scraper/app.log by the logger
if [ -n "$FROM_DATE" ] && [ -n "$TO_DATE" ]; then
    CLI_CMD="python -m src.cli.main scrape --age-group=${AGE_GROUP} --division=${DIVISION} --from=${FROM_DATE} --to=${TO_DATE}"
else
    CLI_CMD="python -m src.cli.main scrape --age-group=${AGE_GROUP} --division=${DIVISION} --start=${START} --end=${END}"
fi

echo -e "${BLUE}📦 Creating job from CronJob template...${NC}"

# Create job manifest
cat <<EOF | kubectl apply -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: ${JOB_NAME}
  namespace: ${NAMESPACE}
  labels:
    app: mls-scraper
    trigger: manual
spec:
  ttlSecondsAfterFinished: 3600  # Clean up after 1 hour
  template:
    metadata:
      labels:
        app: mls-scraper
        job: ${JOB_NAME}
    spec:
      restartPolicy: Never
      containers:
      - name: scraper
        image: gcr.io/${PROJECT_ID}/mls-scraper:latest
        command: ["/bin/sh", "-c"]
        args:
        - "${CLI_CMD}"
        envFrom:
        - configMapRef:
            name: mls-scraper-config
        - secretRef:
            name: mls-scraper-secrets
        volumeMounts:
        - name: scraper-logs
          mountPath: /var/log/scraper
        - name: promtail-config
          mountPath: /etc/promtail
      - name: promtail
        image: grafana/promtail:latest
        args:
        - "-config.file=/etc/promtail/promtail.yaml"
        - "-config.expand-env=true"
        envFrom:
        - secretRef:
            name: mls-scraper-secrets
        volumeMounts:
        - name: scraper-logs
          mountPath: /var/log/scraper
          readOnly: true
        - name: promtail-config
          mountPath: /etc/promtail
      volumes:
      - name: scraper-logs
        emptyDir: {}
      - name: promtail-config
        configMap:
          name: promtail-config
EOF

echo -e "${GREEN}✓ Job created successfully${NC}"
echo ""

# Wait for pod to be created
echo -e "${BLUE}⏳ Waiting for pod to be created...${NC}"
sleep 3

# Get pod name
POD_NAME=$(kubectl get pods -n ${NAMESPACE} -l job-name=${JOB_NAME} -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

if [ -z "$POD_NAME" ]; then
    echo -e "${RED}Error: Pod not found${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Pod created: ${POD_NAME}${NC}"
echo ""

# Wait for pod to be running
echo -e "${BLUE}⏳ Waiting for pod to start...${NC}"
kubectl wait --for=condition=Ready pod/${POD_NAME} -n ${NAMESPACE} --timeout=60s || true

# Check pod status
POD_STATUS=$(kubectl get pod ${POD_NAME} -n ${NAMESPACE} -o jsonpath='{.status.phase}')
echo -e "${GREEN}✓ Pod status: ${POD_STATUS}${NC}"
echo ""

if [ "$FOLLOW_LOGS" = true ]; then
    echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║${NC}  ${YELLOW}Following logs (Ctrl+C to stop)${NC}                          ${BLUE}║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""

    # Follow logs
    kubectl logs -f ${POD_NAME} -n ${NAMESPACE} -c scraper || true

    echo ""
    echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║${NC}  ${YELLOW}Job Status${NC}                                               ${BLUE}║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"

    # Check final job status
    JOB_STATUS=$(kubectl get job ${JOB_NAME} -n ${NAMESPACE} -o jsonpath='{.status.conditions[0].type}' 2>/dev/null || echo "Unknown")

    if [ "$JOB_STATUS" = "Complete" ]; then
        echo -e "${GREEN}✓ Job completed successfully${NC}"
    elif [ "$JOB_STATUS" = "Failed" ]; then
        echo -e "${RED}✗ Job failed${NC}"
        exit 1
    else
        echo -e "${YELLOW}⚠ Job status: ${JOB_STATUS}${NC}"
    fi
else
    echo -e "${YELLOW}To view logs:${NC}"
    echo "  kubectl logs -f ${POD_NAME} -n ${NAMESPACE} -c scraper"
fi

echo ""
echo -e "${BLUE}Management Commands:${NC}"
echo "  View logs:   kubectl logs ${POD_NAME} -n ${NAMESPACE} -c scraper"
echo "  Job status:  kubectl get job ${JOB_NAME} -n ${NAMESPACE}"
echo "  Delete job:  kubectl delete job ${JOB_NAME} -n ${NAMESPACE}"
echo ""
