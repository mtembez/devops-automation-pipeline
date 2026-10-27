"""Integration and deterministic validation tests for deployment shell scripts."""

import json
import os
from pathlib import Path
import subprocess
import threading
import time
from wsgiref.simple_server import make_server
import pytest

from app.main import application

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
ROOT_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def mock_app_server():
    """Runs the WSGI application on an ephemeral port in a daemon background thread."""
    server = make_server("127.0.0.1", 8899, application)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.3)
    yield "http://127.0.0.1:8899"
    server.shutdown()


class TestDeploymentScripts:
    def test_health_probe_success_against_live_server(self, mock_app_server):
        script = SCRIPTS_DIR / "health_probe.sh"
        cmd = [str(script), f"{mock_app_server}/health/ready", "3", "1", "2"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        assert res.returncode == 0
        assert "SUCCESS on attempt" in res.stdout

    def test_health_probe_failure_against_dead_port(self):
        script = SCRIPTS_DIR / "health_probe.sh"
        cmd = [str(script), "http://127.0.0.1:59999/health/ready", "2", "1", "1"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        assert res.returncode != 0
        assert "Health check failed" in res.stderr

    def test_canary_validation_success_against_live_server(self, mock_app_server):
        script = SCRIPTS_DIR / "canary.sh"
        cmd = [str(script), f"{mock_app_server}/api/v1/work", "5", "0"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        assert res.returncode == 0
        assert "Total Requests : 5" in res.stdout
        assert "Failures       : 0" in res.stdout
        assert "Canary evaluation passed" in res.stdout

    def test_canary_validation_failure_on_unreachable_target(self):
        script = SCRIPTS_DIR / "canary.sh"
        cmd = [str(script), "http://127.0.0.1:59999/api/v1/work", "3", "0"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        assert res.returncode != 0
        assert "failures exceeded threshold" in res.stderr

    def test_rollback_script_atomicity_and_state(self, tmp_path):
        script = SCRIPTS_DIR / "rollback.sh"
        upstream_conf = ROOT_DIR / "nginx" / "active_upstream.conf"
        state_file = ROOT_DIR / "deploy_state.json"

        # Execute rollback to green
        res = subprocess.run([str(script), "green"], capture_output=True, text=True)
        assert res.returncode == 0
        assert "Restoring stable upstream: Slot=green" in res.stdout

        # Verify upstream conf content
        with open(upstream_conf) as f:
            content = f.read()
            assert "server app_green:8080" in content

        # Verify state file content
        with open(state_file) as f:
            state = json.load(f)
            assert state["active_slot"] == "green"
            assert state["status"] == "rolled_back"

        # Execute rollback back to blue
        res = subprocess.run([str(script), "blue"], capture_output=True, text=True)
        assert res.returncode == 0
        with open(upstream_conf) as f:
            content = f.read()
            assert "server app_blue:8080" in content
