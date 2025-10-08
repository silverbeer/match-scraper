#!/bin/bash
# Fix for CronJob stuck due to promtail sidecar not terminating
# This script provides options to resolve the issue

set -e

echo "🔧 Match Scraper CronJob Sidecar Fix"
echo "====================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

NAMESPACE="match-scraper"
CRONJOB_NAME="mls-scraper-cronjob"

echo "Issue Identified:"
echo "----------------"
echo "The mls-scraper container completes successfully, but the promtail sidecar"
echo "keeps running indefinitely, preventing the Kubernetes Job from completing."
echo ""
echo "Current job status: ACTIVE (stuck)"
echo "Main container: Completed (exitCode: 0)"
echo "Promtail sidecar: Still Running"
echo ""

echo -e "${YELLOW}Resolution Options:${NC}"
echo "===================="
echo ""
echo "1. Quick Fix - Kill current stuck job and let CronJob retry"
echo "2. Permanent Fix - Update CronJob to remove promtail sidecar (recommended)"
echo "3. Permanent Fix - Add shared process namespace with preStop hook"
echo "4. Check if native sidecars are supported (K8s 1.29+)"
echo ""

read -p "Select option (1-4): " option

case $option in
    1)
        echo ""
        echo -e "${BLUE}Executing Quick Fix...${NC}"
        echo "Deleting stuck job: mls-scraper-cronjob-29331720"
        kubectl delete job -n $NAMESPACE mls-scraper-cronjob-29331720
        echo ""
        echo -e "${GREEN}✅ Job deleted successfully${NC}"
        echo ""
        echo "Note: This is a temporary fix. The issue will recur on the next scheduled run."
        echo "Apply one of the permanent fixes (option 2 or 3) to resolve permanently."
        ;;

    2)
        echo ""
        echo -e "${BLUE}Creating permanent fix by removing promtail sidecar...${NC}"
        echo ""
        echo "This will:"
        echo "  1. Backup current cronjob.yaml"
        echo "  2. Remove promtail sidecar and related volumes"
        echo "  3. Apply updated configuration"
        echo ""
        read -p "Continue? (y/n): " confirm

        if [ "$confirm" = "y" ]; then
            # Backup current configuration
            kubectl get cronjob -n $NAMESPACE $CRONJOB_NAME -o yaml > cronjob-backup-$(date +%Y%m%d-%H%M%S).yaml
            echo -e "${GREEN}✅ Backup created${NC}"

            echo ""
            echo "Please manually update k8s/cronjob.yaml to remove:"
            echo "  - The promtail container (lines 154-170)"
            echo "  - The promtail-config volume mount from mls-scraper container (lines 134-135)"
            echo "  - The init container config-preprocessor (lines 23-47)"
            echo "  - The promtail-config and promtail-processed volumes (lines 175-179)"
            echo ""
            echo "After editing, run:"
            echo "  kubectl apply -f k8s/cronjob.yaml"
            echo ""
            echo "Then delete the stuck job:"
            echo "  kubectl delete job -n $NAMESPACE mls-scraper-cronjob-29331720"
        fi
        ;;

    3)
        echo ""
        echo -e "${BLUE}Creating permanent fix with shared process namespace...${NC}"
        echo ""
        echo "This approach keeps promtail but makes it terminate when the main container exits."
        echo ""
        echo "Required changes to k8s/cronjob.yaml:"
        echo "  1. Add 'shareProcessNamespace: true' to pod spec"
        echo "  2. Add preStop lifecycle hook to promtail"
        echo ""
        echo "Example:"
        echo "---"
        cat <<'EOF'
spec:
  jobTemplate:
    spec:
      template:
        spec:
          shareProcessNamespace: true  # Add this
          restartPolicy: OnFailure
          # ... other config ...
          containers:
          - name: promtail
            image: grafana/promtail:2.9.3
            lifecycle:
              preStop:
                exec:
                  command:
                  - /bin/sh
                  - -c
                  - |
                    # Wait for main container to finish
                    while kill -0 1 2>/dev/null; do sleep 1; done
                    # Give promtail time to flush logs
                    sleep 5
EOF
        echo "---"
        echo ""
        echo "After making these changes, apply with:"
        echo "  kubectl apply -f k8s/cronjob.yaml"
        echo ""
        echo "Then delete the stuck job:"
        echo "  kubectl delete job -n $NAMESPACE mls-scraper-cronjob-29331720"
        ;;

    4)
        echo ""
        echo -e "${BLUE}Checking for native sidecar support...${NC}"
        K8S_VERSION=$(kubectl version -o json | python3 -c "import sys, json; print(json.load(sys.stdin)['serverVersion']['minor'])" 2>/dev/null || echo "unknown")
        echo "Kubernetes version: 1.$K8S_VERSION"

        if [ "$K8S_VERSION" -ge 29 ] 2>/dev/null; then
            echo -e "${GREEN}✅ Native sidecars are supported!${NC}"
            echo ""
            echo "Add this to your promtail container spec in k8s/cronjob.yaml:"
            echo "---"
            cat <<'EOF'
containers:
- name: promtail
  restartPolicy: Always  # Makes this a native sidecar
  image: grafana/promtail:2.9.3
  # ... rest of config
EOF
            echo "---"
            echo ""
            echo "This tells Kubernetes that promtail is a sidecar that should be"
            echo "terminated when the main container completes."
        else
            echo -e "${YELLOW}⚠️  Native sidecars require Kubernetes 1.29+${NC}"
            echo "Consider upgrading your cluster or using Option 2 or 3."
        fi
        ;;

    *)
        echo -e "${RED}Invalid option${NC}"
        exit 1
        ;;
esac

echo ""
echo -e "${BLUE}📊 For monitoring, check Grafana dashboards at:${NC}"
echo "   (Your Grafana URL here)"
echo ""
