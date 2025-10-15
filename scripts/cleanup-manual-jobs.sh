#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

NAMESPACE="match-scraper"
DRY_RUN=false
AGE_HOURS=24

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --namespace=*)
            NAMESPACE="${1#*=}"
            shift
            ;;
        --namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        --age=*)
            AGE_HOURS="${1#*=}"
            shift
            ;;
        --age)
            AGE_HOURS="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --namespace NS      Kubernetes namespace (default: match-scraper)"
            echo "  --age HOURS         Delete jobs older than N hours (default: 24)"
            echo "  --dry-run           Show what would be deleted without actually deleting"
            echo "  -h, --help          Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0 --dry-run                    # Preview what would be deleted"
            echo "  $0 --age 12                     # Delete jobs older than 12 hours"
            echo "  $0 --namespace match-scraper    # Specify namespace"
            exit 0
            ;;
        *)
            echo -e "${RED}Error: Unknown option $1${NC}"
            exit 1
            ;;
    esac
done

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║${NC}  ${GREEN}Manual Job Cleanup${NC}                                       ${BLUE}║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}Configuration:${NC}"
echo -e "  Namespace:   ${GREEN}${NAMESPACE}${NC}"
echo -e "  Age Limit:   ${GREEN}${AGE_HOURS} hours${NC}"
if [ "$DRY_RUN" = true ]; then
    echo -e "  Mode:        ${YELLOW}DRY RUN (no changes will be made)${NC}"
else
    echo -e "  Mode:        ${RED}LIVE (jobs will be deleted)${NC}"
fi
echo ""

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo -e "${RED}Error: kubectl not found. Please install kubectl first.${NC}"
    exit 1
fi

# Get all manual scraper jobs
echo -e "${BLUE}🔍 Finding manual scraper jobs older than ${AGE_HOURS} hours...${NC}"

# Calculate age in seconds
AGE_SECONDS=$((AGE_HOURS * 3600))

# Get jobs with age
JOBS=$(kubectl get jobs -n ${NAMESPACE} -l trigger=manual -o json)

if [ -z "$JOBS" ] || [ "$(echo "$JOBS" | jq -r '.items | length')" -eq 0 ]; then
    echo -e "${YELLOW}No manual jobs found${NC}"
    exit 0
fi

# Get current timestamp
CURRENT_TIME=$(date +%s)

# Array to store jobs to delete
declare -a JOBS_TO_DELETE

# Parse jobs and filter by age
while IFS= read -r job_name; do
    # Get job creation timestamp
    CREATION_TIME=$(kubectl get job "$job_name" -n ${NAMESPACE} -o jsonpath='{.metadata.creationTimestamp}')
    CREATION_TIMESTAMP=$(date -j -f "%Y-%m-%dT%H:%M:%SZ" "$CREATION_TIME" +%s 2>/dev/null || date -d "$CREATION_TIME" +%s 2>/dev/null)

    # Calculate age
    JOB_AGE=$((CURRENT_TIME - CREATION_TIMESTAMP))

    # Check if job is older than age limit
    if [ $JOB_AGE -gt $AGE_SECONDS ]; then
        JOBS_TO_DELETE+=("$job_name")
        AGE_HOURS_ACTUAL=$((JOB_AGE / 3600))
        echo -e "  ${YELLOW}→${NC} $job_name (${AGE_HOURS_ACTUAL}h old)"
    fi
done < <(echo "$JOBS" | jq -r '.items[].metadata.name')

# Check if any jobs to delete
if [ ${#JOBS_TO_DELETE[@]} -eq 0 ]; then
    echo -e "${GREEN}✓ No jobs older than ${AGE_HOURS} hours found${NC}"
    exit 0
fi

echo ""
echo -e "${YELLOW}Found ${#JOBS_TO_DELETE[@]} job(s) to delete${NC}"
echo ""

if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}DRY RUN: Would delete the following jobs:${NC}"
    for job in "${JOBS_TO_DELETE[@]}"; do
        echo -e "  - $job"
    done
    echo ""
    echo -e "${YELLOW}Run without --dry-run to actually delete these jobs${NC}"
    exit 0
fi

# Delete jobs
echo -e "${BLUE}🗑️  Deleting jobs...${NC}"
DELETED_COUNT=0
FAILED_COUNT=0

for job in "${JOBS_TO_DELETE[@]}"; do
    if kubectl delete job "$job" -n ${NAMESPACE} --grace-period=0 --wait=false 2>/dev/null; then
        echo -e "  ${GREEN}✓${NC} Deleted $job"
        DELETED_COUNT=$((DELETED_COUNT + 1))
    else
        echo -e "  ${RED}✗${NC} Failed to delete $job"
        FAILED_COUNT=$((FAILED_COUNT + 1))
    fi
done

echo ""
echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║${NC}  ${GREEN}Cleanup Summary${NC}                                          ${BLUE}║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo -e "  Deleted:  ${GREEN}${DELETED_COUNT}${NC}"
if [ $FAILED_COUNT -gt 0 ]; then
    echo -e "  Failed:   ${RED}${FAILED_COUNT}${NC}"
fi
echo ""
