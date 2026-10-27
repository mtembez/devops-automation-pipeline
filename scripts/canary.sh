#!/usr/bin/env bash
# ==============================================================================
# DevOps Automation Pipeline: Canary Validation Engine
# Sends synthetic load and calculates success rate and latency threshold.
# Usage: ./scripts/canary.sh <url> [request_count] [max_allowed_failures]
# ==============================================================================
set -euo pipefail

TARGET_URL="${1:-http://localhost:8080/api/v1/work}"
REQUEST_COUNT="${2:-20}"
MAX_ALLOWED_FAILURES="${3:-0}"

echo "[CANARY] Starting canary traffic verification on ${TARGET_URL}"
echo "[CANARY] Sending ${REQUEST_COUNT} synthetic requests with 'X-Canary: true' header..."

FAILURES=0
SUCCESSES=0
T_START=$(date +%s%N 2>/dev/null || python3 -c 'import time; print(int(time.time()*1e9))')

for i in $(seq 1 "${REQUEST_COUNT}"); do
    CODE=0
    if command -v curl >/dev/null 2>&1; then
        CODE=$(curl -s -o /dev/null -w "%{http_code}" -H "X-Canary: true" --max-time 3 "${TARGET_URL}" 2>/dev/null) || CODE="000"
    else
        CODE=$(python3 -c "
import urllib.request
req = urllib.request.Request('${TARGET_URL}', headers={'X-Canary': 'true'})
try:
    with urllib.request.urlopen(req, timeout=3) as resp:
        print(resp.status)
except Exception:
    print('000')
" 2>/dev/null || echo "000")
    fi

    if [ "${CODE}" = "200" ]; then
        SUCCESSES=$((SUCCESSES + 1))
    else
        FAILURES=$((FAILURES + 1))
        echo "[CANARY] Request ${i}/${REQUEST_COUNT} failed with HTTP ${CODE}" >&2
    fi
done

T_END=$(date +%s%N 2>/dev/null || python3 -c 'import time; print(int(time.time()*1e9))')
DURATION_MS=$(( (T_END - T_START) / 1000000 ))
AVG_LATENCY_MS=$(( DURATION_MS / REQUEST_COUNT ))

echo "------------------------------------------------------------"
echo "[CANARY] Canary Results Summary:"
echo "         Total Requests : ${REQUEST_COUNT}"
echo "         Successes      : ${SUCCESSES}"
echo "         Failures       : ${FAILURES}"
echo "         Avg Latency    : ${AVG_LATENCY_MS} ms"
echo "------------------------------------------------------------"

if [ "${FAILURES}" -gt "${MAX_ALLOWED_FAILURES}" ]; then
    echo "[CANARY] FAILED: ${FAILURES} failures exceeded threshold of ${MAX_ALLOWED_FAILURES}!" >&2
    exit 1
fi

echo "[CANARY] SUCCESS: Canary evaluation passed with 100% success criteria."
exit 0
