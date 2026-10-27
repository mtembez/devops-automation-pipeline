"""Deterministic unit and integration tests for application endpoints, metrics, and health probes."""

import json
from unittest.mock import MagicMock
import pytest

from app.main import (
    STATE,
    application,
    handle_liveness,
    handle_metrics,
    handle_readiness,
    handle_simulate_unhealthy,
    handle_version,
    handle_work,
)


@pytest.fixture(autouse=True)
def reset_state():
    """Reset application state before each test."""
    STATE["is_alive"] = True
    STATE["is_ready"] = True
    STATE["total_requests"] = 0
    STATE["status_2xx"] = 0
    STATE["status_4xx"] = 0
    STATE["status_5xx"] = 0
    STATE["total_latency_ms"] = 0.0


def call_app(path: str, headers: dict = None) -> tuple:
    """Helper to execute WSGI application in-memory."""
    environ = {
        "REQUEST_METHOD": "GET",
        "PATH_INFO": path,
        "SERVER_NAME": "localhost",
        "SERVER_PORT": "8080",
    }
    if headers:
        for k, v in headers.items():
            header_key = f"HTTP_{k.upper().replace('-', '_')}"
            environ[header_key] = v

    captured_status = []
    captured_headers = []

    def start_response(status, response_headers, exc_info=None):
        captured_status.append(status)
        captured_headers.append(dict(response_headers))

    body_chunks = application(environ, start_response)
    raw_body = b"".join(body_chunks)
    status_code = int(captured_status[0].split()[0])
    resp_headers = captured_headers[0]

    return status_code, resp_headers, raw_body


class TestApplicationProbesAndEndpoints:
    def test_liveness_probe_returns_up(self):
        code, headers, body = call_app("/health/live")
        assert code == 200
        assert headers["Content-Type"] == "application/json"
        data = json.loads(body.decode("utf-8"))
        assert data["status"] == "UP"
        assert "timestamp" in data

    def test_liveness_probe_when_down(self):
        STATE["is_alive"] = False
        code, headers, body = call_app("/health/live")
        assert code == 503
        data = json.loads(body.decode("utf-8"))
        assert data["status"] == "DOWN"

    def test_readiness_probe_returns_ready(self):
        code, headers, body = call_app("/health/ready")
        assert code == 200
        data = json.loads(body.decode("utf-8"))
        assert data["status"] == "READY"
        assert "slot" in data
        assert "version" in data

    def test_readiness_probe_when_not_ready(self):
        STATE["is_ready"] = False
        code, headers, body = call_app("/health/ready")
        assert code == 503
        data = json.loads(body.decode("utf-8"))
        assert data["status"] == "NOT_READY"

    def test_version_endpoint_metadata(self):
        code, headers, body = call_app("/version")
        assert code == 200
        data = json.loads(body.decode("utf-8"))
        assert "version" in data
        assert "slot" in data
        assert "commit_sha" in data
        assert "uptime_seconds" in data

    def test_metrics_prometheus_exposition_format(self):
        # Generate some traffic first
        call_app("/version")
        call_app("/nonexistent-path")

        code, headers, body = call_app("/metrics")
        assert code == 200
        assert "text/plain" in headers["Content-Type"]
        text = body.decode("utf-8")
        assert "http_requests_total" in text
        assert "http_request_duration_ms_avg" in text
        assert "app_uptime_seconds" in text

    def test_canary_workload_header_inspection(self):
        # Regular request
        code, headers, body = call_app("/api/v1/work")
        assert code == 200
        data = json.loads(body.decode("utf-8"))
        assert data["is_canary"] is False

        # Canary request with X-Canary: true
        code, headers, body = call_app("/api/v1/work", headers={"X-Canary": "true"})
        assert code == 200
        data = json.loads(body.decode("utf-8"))
        assert data["is_canary"] is True

    def test_simulate_unhealthy_transition(self):
        code, _, _ = call_app("/simulate/unhealthy")
        assert code == 200
        assert STATE["is_ready"] is False

        # Next readiness check must return 503
        code, _, body = call_app("/health/ready")
        assert code == 503
        data = json.loads(body.decode("utf-8"))
        assert data["status"] == "NOT_READY"

    def test_404_not_found_handling(self):
        code, headers, body = call_app("/unknown/endpoint")
        assert code == 404
        data = json.loads(body.decode("utf-8"))
        assert data["error"] == "not_found"
        assert data["path"] == "/unknown/endpoint"
