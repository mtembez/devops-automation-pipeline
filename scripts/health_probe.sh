#!/usr/bin/env bash
# ==============================================================================
# DevOps Automation Pipeline: Deterministic Health Probe Sentinel
# Usage: ./scripts/health_probe.sh <url> [max_retries] [retry_delay_seconds] [timeout_seconds]
# ==============================================================================
set -euo pipefail

TARGET_URL="${1:-http://localhost:8080/health/ready}"
MAX_RETRIES="${2:-15}"
RETRY_DELAY="${3:-1}"
TIMEOUT_SECONDS="${4:-2}"

echo "[PROBE] Initiating health verification on ${TARGET_URL}"
echo "[PROBE] Config: max_retries=${MAX_RETRIES}, delay=${RETRY_DELAY}s, timeout=${TIMEOUT_SECONDS}s"

ATTEMPT=1
while [ "${ATTEMPT}" -le "${MAX_RETRIES}" ]; do
    HTTP_CODE=0
    RESPONSE_BODY=""

    if command -v curl >/dev/null 2>&1; then
        HTTP_CODE=$(curl -s -o /tmp/health_probe_body.txt -w "%{http_code}" --max-time "${TIMEOUT_SECONDS}" "${TARGET_URL}" 2>/dev/null) || HTTP_CODE="000"
        if [ -f /tmp/health_probe_body.txt ]; then
            RESPONSE_BODY=$(cat /tmp/health_probe_body.txt 2>/dev/null || true)
            rm -f /tmp/health_probe_body.txt
        fi
    elif command -v python3 >/dev/null 2>&1; then
        PY_RES=$(python3 -c "
import urllib.request, urllib.error, sys
url = '${TARGET_URL}'
try:
    with urllib.request.urlopen(url, timeout=${TIMEOUT_SECONDS}) as resp:
        print(f'{resp.status}|{resp.read().decode(\"utf-8\")}')
except urllib.error.HTTPError as e:
    print(f'{e.code}|{e.read().decode(\"utf-8\")}')
except Exception as e:
    print('000|' + str(e))
" 2>/dev/null || echo "000|connection_failed")
        HTTP_CODE="${PY_RES%%|*}"
        RESPONSE_BODY="${PY_RES#*|}"
    fi

    if [ "${HTTP_CODE}" = "200" ]; then
        echo "[PROBE] SUCCESS on attempt ${ATTEMPT}/${MAX_RETRIES}: HTTP ${HTTP_CODE}"
        echo "[PROBE] Response: ${RESPONSE_BODY}"
        exit 0
    else
        echo "[PROBE] WARN Attempt ${ATTEMPT}/${MAX_RETRIES} returned HTTP ${HTTP_CODE}. Retrying in ${RETRY_DELAY}s..."
    fi

    ATTEMPT=$((ATTEMPT + 1))
    sleep "${RETRY_DELAY}"
done

echo "[PROBE] ERROR: Health check failed after ${MAX_RETRIES} attempts against ${TARGET_URL}!" >&2
exit 1
