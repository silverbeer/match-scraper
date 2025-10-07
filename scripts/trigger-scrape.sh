#!/usr/bin/env bash

set -euo pipefail

NAMESPACE="match-scraper"
CRONJOB_NAME="mls-scraper-cronjob"
CLEANUP="false"
EXTRA_ARGS=()
JOB_NAME="run-$(date +%s)"

usage() {
  echo "Usage: $0 [-n namespace] [-c] [-- ARGS...]"
  echo "  -n NAMESPACE   Kubernetes namespace (default: match-scraper)"
  echo "  -c             Cleanup the Job after completion"
  echo "  -- ARGS        Additional args passed to scraper (e.g. -- --no-api --start 3)"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--namespace)
      NAMESPACE="$2"; shift 2;;
    -c|--cleanup)
      CLEANUP="true"; shift;;
    --)
      shift; EXTRA_ARGS=("$@"); break;;
    -h|--help)
      usage; exit 0;;
    *)
      echo "Unknown option: $1" >&2; usage; exit 1;;
  esac
done

if [[ ${#EXTRA_ARGS[@]} -gt 0 ]]; then
  echo "Creating Job manifest with overridden args: ${EXTRA_ARGS[*]}"
  TMP_JSON=$(mktemp)
  kubectl create job --from=cronjob/$CRONJOB_NAME "$JOB_NAME" -n "$NAMESPACE" --dry-run=client -o json > "$TMP_JSON"
  if command -v jq >/dev/null 2>&1; then
    # Build the Python command with extra args, wrapped in shell
    PYTHON_CMD="python -m src.cli.main scrape ${EXTRA_ARGS[*]} 2>&1 | tee -a /var/log/scraper/app.log"
    ARGS_JSON=$(jq -n --arg cmd "$PYTHON_CMD" '["-c", $cmd]')
    jq ".spec.template.spec.containers[0].args = $ARGS_JSON" "$TMP_JSON" | kubectl apply -n "$NAMESPACE" -f - >/dev/null
  else
    echo "jq not found. Please install jq or run without extra args." >&2
    rm -f "$TMP_JSON"
    exit 1
  fi
  rm -f "$TMP_JSON"
else
  echo "Creating Job from CronJob/$CRONJOB_NAME in namespace $NAMESPACE ..."
  kubectl create job --from=cronjob/$CRONJOB_NAME "$JOB_NAME" -n "$NAMESPACE" >/dev/null
fi

echo "Waiting for pod to start ..."
POD=""
for i in {1..60}; do
  POD=$(kubectl get pods -n "$NAMESPACE" -l job-name="$JOB_NAME" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
  [[ -n "$POD" ]] && break
  sleep 1
done

if [[ -z "$POD" ]]; then
  echo "Failed to find pod for job $JOB_NAME" >&2
  exit 1
fi

echo "Pod: $POD"

echo "Waiting for container to be running/ready ..."
kubectl wait --for=condition=Ready pod/"$POD" -n "$NAMESPACE" --timeout=180s || true

echo "Streaming logs (mls-scraper container) ..."
set +e
kubectl logs -f -n "$NAMESPACE" job/"$JOB_NAME" -c mls-scraper
STATUS=$?
set -e

echo ""
echo "Job $JOB_NAME logs ended (exit code: $STATUS)."

# Optionally show promtail logs for debugging
if [[ "${SHOW_PROMTAIL_LOGS:-false}" == "true" ]]; then
  echo ""
  echo "Promtail sidecar logs:"
  kubectl logs -n "$NAMESPACE" job/"$JOB_NAME" -c promtail --tail=50 || true
fi

if [[ "$CLEANUP" == "true" ]]; then
  echo "Cleaning up job $JOB_NAME ..."
  kubectl delete job "$JOB_NAME" -n "$NAMESPACE" --wait=false >/dev/null || true
fi

exit $STATUS
