"""High-throughput production microservice with health probes, Prometheus metrics, and zero-downtime canary support."""

from datetime import datetime, timezone
import json
import logging
import os
import signal
import sys
import time
from typing import Callable, Dict, List, Tuple
from urllib.parse import parse_qs

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='{"timestamp":"%(asctime)s","level":"%(levelname)s","slot":"%(name)s","message":"%(message)s"}',
)
logger = logging.getLogger(os.getenv("DEPLOYMENT_SLOT", "blue"))

START_TIME = time.time()
RELEASE_VERSION = os.getenv("RELEASE_VERSION", "1.0.0")
DEPLOYMENT_SLOT = os.getenv("DEPLOYMENT_SLOT", "blue")
COMMIT_SHA = os.getenv("COMMIT_SHA", "unknown")

# In-memory metrics & health status
STATE = {
    "is_alive": True,
    "is_ready": True,
    "total_requests": 0,
    "status_2xx": 0,
    "status_4xx": 0,
    "status_5xx": 0,
    "total_latency_ms": 0.0,
}


def sigterm_handler(signum, frame):
    """Graceful shutdown signal handler: transition ready -> false before terminating."""
    logger.info("Received termination signal %s. Initiating graceful shutdown drain...", signum)
    STATE["is_ready"] = False
    time.sleep(0.5)
    sys.exit(0)


signal.signal(signal.SIGTERM, sigterm_handler)
signal.signal(signal.SIGINT, sigterm_handler)


def handle_liveness() -> Tuple[int, Dict[str, str], bytes]:
    """Liveness probe: verifies process is alive and responsive."""
    if STATE["is_alive"]:
        body = json.dumps({"status": "UP", "timestamp": datetime.now(timezone.utc).isoformat()}).encode("utf-8")
        return 200, {"Content-Type": "application/json"}, body
    body = json.dumps({"status": "DOWN"}).encode("utf-8")
    return 503, {"Content-Type": "application/json"}, body


def handle_readiness() -> Tuple[int, Dict[str, str], bytes]:
    """Readiness probe: verifies dependencies are ready to accept traffic."""
    if STATE["is_ready"]:
        uptime = round(time.time() - START_TIME, 2)
        body = json.dumps({
            "status": "READY",
            "slot": DEPLOYMENT_SLOT,
            "version": RELEASE_VERSION,
            "uptime_seconds": uptime,
        }).encode("utf-8")
        return 200, {"Content-Type": "application/json"}, body
    body = json.dumps({"status": "NOT_READY", "slot": DEPLOYMENT_SLOT}).encode("utf-8")
    return 503, {"Content-Type": "application/json"}, body


def handle_version() -> Tuple[int, Dict[str, str], bytes]:
    """Version metadata endpoint for deployment verification and smoke tests."""
    uptime = round(time.time() - START_TIME, 2)
    data = {
        "version": RELEASE_VERSION,
        "slot": DEPLOYMENT_SLOT,
        "commit_sha": COMMIT_SHA,
        "uptime_seconds": uptime,
        "started_at": datetime.fromtimestamp(START_TIME, tz=timezone.utc).isoformat(),
    }
    return 200, {"Content-Type": "application/json"}, json.dumps(data).encode("utf-8")


def handle_metrics() -> Tuple[int, Dict[str, str], bytes]:
    """Prometheus exposition format metrics."""
    avg_latency = (
        (STATE["total_latency_ms"] / STATE["total_requests"])
        if STATE["total_requests"] > 0
        else 0.0
    )
    lines = [
        "# HELP http_requests_total Total number of HTTP requests processed",
        "# TYPE http_requests_total counter",
        f'http_requests_total{{slot="{DEPLOYMENT_SLOT}",status="2xx"}} {STATE["status_2xx"]}',
        f'http_requests_total{{slot="{DEPLOYMENT_SLOT}",status="4xx"}} {STATE["status_4xx"]}',
        f'http_requests_total{{slot="{DEPLOYMENT_SLOT}",status="5xx"}} {STATE["status_5xx"]}',
        "# HELP http_request_duration_ms_avg Average request processing latency",
        "# TYPE http_request_duration_ms_avg gauge",
        f'http_request_duration_ms_avg{{slot="{DEPLOYMENT_SLOT}"}} {round(avg_latency, 3)}',
        "# HELP app_uptime_seconds Application uptime in seconds",
        "# TYPE app_uptime_seconds gauge",
        f'app_uptime_seconds{{slot="{DEPLOYMENT_SLOT}"}} {round(time.time() - START_TIME, 2)}',
    ]
    payload = "\n".join(lines) + "\n"
    return 200, {"Content-Type": "text/plain; version=0.0.4; charset=utf-8"}, payload.encode("utf-8")


def handle_work(environ: dict) -> Tuple[int, Dict[str, str], bytes]:
    """Simulated workload endpoint with canary header inspection."""
    canary_header = environ.get("HTTP_X_CANARY", "false").lower() == "true"
    payload = {
        "status": "success",
        "processed_by": DEPLOYMENT_SLOT,
        "version": RELEASE_VERSION,
        "is_canary": canary_header,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return 200, {"Content-Type": "application/json"}, json.dumps(payload).encode("utf-8")


def handle_simulate_unhealthy() -> Tuple[int, Dict[str, str], bytes]:
    """Admin endpoint to intentionally trigger unhealthiness for automated rollback testing."""
    STATE["is_ready"] = False
    logger.warning("Simulated failure triggered: readiness state toggled to false.")
    return 200, {"Content-Type": "application/json"}, json.dumps({"status": "failure_simulated", "is_ready": False}).encode("utf-8")


def application(environ: dict, start_response: Callable) -> List[bytes]:
    """WSGI standard application entry point."""
    t_start = time.perf_counter()
    path = environ.get("PATH_INFO", "/")

    headers: Dict[str, str] = {}
    status_code = 404
    body = b'{"error":"not_found"}'

    if path == "/health/live":
        status_code, headers, body = handle_liveness()
    elif path == "/health/ready":
        status_code, headers, body = handle_readiness()
    elif path == "/version":
        status_code, headers, body = handle_version()
    elif path == "/metrics":
        status_code, headers, body = handle_metrics()
    elif path.startswith("/api/v1/work"):
        status_code, headers, body = handle_work(environ)
    elif path == "/simulate/unhealthy":
        status_code, headers, body = handle_simulate_unhealthy()
    else:
        status_code = 404
        headers = {"Content-Type": "application/json"}
        body = json.dumps({"error": "not_found", "path": path}).encode("utf-8")

    duration_ms = (time.perf_counter() - t_start) * 1000.0
    STATE["total_requests"] += 1
    STATE["total_latency_ms"] += duration_ms

    if 200 <= status_code < 300:
        STATE["status_2xx"] += 1
    elif 400 <= status_code < 500:
        STATE["status_4xx"] += 1
    else:
        STATE["status_5xx"] += 1

    headers["Server"] = f"DevOps-Pipeline-Microservice/{RELEASE_VERSION}"
    headers["X-Deployment-Slot"] = DEPLOYMENT_SLOT
    headers["Content-Length"] = str(len(body))

    status_str = f"{status_code} OK" if status_code == 200 else f"{status_code} Error"
    start_response(status_str, list(headers.items()))
    return [body]


if __name__ == "__main__":
    from wsgiref.simple_server import make_server
    port = int(os.getenv("PORT", "8000"))
    logger.info("Starting microservice on port %d [Slot: %s, Version: %s]...", port, DEPLOYMENT_SLOT, RELEASE_VERSION)
    with make_server("0.0.0.0", port, application) as httpd:
        httpd.serve_forever()
