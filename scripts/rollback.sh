#!/usr/bin/env bash
# ==============================================================================
# DevOps Automation Pipeline: Automated Rollback Controller
# Usage: ./scripts/rollback.sh [target_slot]
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
STATE_FILE="${ROOT_DIR}/deploy_state.json"
UPSTREAM_CONF="${ROOT_DIR}/nginx/active_upstream.conf"

echo "[ROLLBACK] =========================================================="
echo "[ROLLBACK] CRITICAL: Initiating automated zero-downtime rollback..."
echo "[ROLLBACK] =========================================================="

# Determine target fallback slot
FALLBACK_SLOT="${1:-}"
if [ -z "${FALLBACK_SLOT}" ]; then
    if [ -f "${STATE_FILE}" ]; then
        FALLBACK_SLOT=$(python3 -c "
import json
try:
    with open('${STATE_FILE}') as f:
        data = json.load(f)
        print(data.get('previous_slot', 'blue'))
except Exception:
    print('blue')
")
    else
        FALLBACK_SLOT="blue"
    fi
fi

if [ "${FALLBACK_SLOT}" = "blue" ]; then
    FALLBACK_HOST="app_blue"
    FALLBACK_PORT=8081
elif [ "${FALLBACK_SLOT}" = "green" ]; then
    FALLBACK_HOST="app_green"
    FALLBACK_PORT=8082
else
    echo "[ROLLBACK] Unknown slot '${FALLBACK_SLOT}'. Defaulting to blue."
    FALLBACK_SLOT="blue"
    FALLBACK_HOST="app_blue"
    FALLBACK_PORT=8081
fi

echo "[ROLLBACK] Restoring stable upstream: Slot=${FALLBACK_SLOT} Host=${FALLBACK_HOST}:${FALLBACK_PORT}"

# Atomic swap of active upstream configuration
TMP_CONF="${UPSTREAM_CONF}.rollback.tmp"
cat <<EOF > "${TMP_CONF}"
# Active upstream server node (RESTORED VIA AUTOMATED ROLLBACK)
server ${FALLBACK_HOST}:8080 max_fails=2 fail_timeout=5s;
EOF

mv -f "${TMP_CONF}" "${UPSTREAM_CONF}"
echo "[ROLLBACK] Atomically replaced ${UPSTREAM_CONF}"

# Signal Nginx reload if running in Docker or host
if command -v docker >/dev/null 2>&1 && docker ps --format '{{.Names}}' | grep -q "nginx_proxy"; then
    echo "[ROLLBACK] Sending SIGHUP reload signal to nginx_proxy container..."
    docker exec nginx_proxy nginx -s reload || true
elif command -v nginx >/dev/null 2>&1; then
    echo "[ROLLBACK] Reloading host Nginx..."
    nginx -s reload 2>/dev/null || true
fi

# Update deploy state record
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
cat <<EOF > "${STATE_FILE}"
{
  "active_slot": "${FALLBACK_SLOT}",
  "previous_slot": "failed_candidate",
  "status": "rolled_back",
  "updated_at": "${TIMESTAMP}"
}
EOF

echo "[ROLLBACK] State recorded in ${STATE_FILE}"
echo "[ROLLBACK] SUCCESS: Rollback successfully executed."
exit 0
