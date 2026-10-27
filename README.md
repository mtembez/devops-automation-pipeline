# Automated CI/CD Deployment Pipeline & Zero-Downtime Engine

[![CI/CD Pipeline](https://github.com/mtembez/devops-automation-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/mtembez/devops-automation-pipeline/actions/workflows/ci.yml)
[![Coverage: 91%](https://img.shields.io/badge/Coverage-91%25-brightgreen.svg)](https://github.com/mtembez/devops-automation-pipeline)
[![Python 3.13](https://img.shields.io/badge/Python-3.13-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Multi--Stage-2496ED.svg)](https://www.docker.com/)
[![Nginx](https://img.shields.io/badge/Nginx-Zero--Downtime-009639.svg)](https://nginx.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An enterprise-grade, zero-downtime continuous integration and continuous deployment (CI/CD) engine. Built with **GitHub Actions**, **Docker multi-stage builds**, **POSIX shell automation**, and **Nginx atomic Blue/Green upstream switching**.

> **Key Achievement**: Architected automated CI/CD deployment pipelines accelerating release cycles while guaranteeing zero user-facing downtime through atomic traffic switching, pre-flight health sentinels, synthetic canary analysis, and sub-500ms automated rollback traps.

---

## Architectural Workflow

```
+---------------------------------------------------------------------------------+
|                               GITHUB ACTIONS CI/CD                              |
+---------------------------------------------------------------------------------+
|  [Stage 1: Lint & Static Syntax]                                                |
|   - python -m py_compile (app + tests)                                          |
|   - bash -n (all deployment scripts)                                            |
|   - Non-root container linting                                                  |
|                                                                                 |
|  [Stage 2: Deterministic Tests]                                                 |
|   - Pytest unit and integration suite                                           |
|   - 91% code coverage enforcement (fail-under=85%)                             |
|                                                                                 |
|  [Stage 3: Container Security & Build]                                          |
|   - Multi-stage Docker build caching                                            |
|   - Non-root user (UID 10001) security context verification                     |
|                                                                                 |
|  [Stage 4: Zero-Downtime Deployment & Automated Rollback Simulation]            |
|   - Health probe verification loop                                              |
|   - Synthetic canary traffic evaluation                                         |
|   - Circuit-breaker rollback execution                                          |
+---------------------------------------+-----------------------------------------+
                                        |
                                        v
+---------------------------------------------------------------------------------+
|                  PRODUCTION BLUE / GREEN DEPLOYMENT TOPOLOGY                    |
+---------------------------------------------------------------------------------+
|                                                                                 |
|                       Client Ingress Traffic (:80)                              |
|                                     |                                           |
|                                     v                                           |
|                        +--------------------------+                             |
|                        |   Nginx Reverse Proxy    |                             |
|                        | (Active Upstream Include)|                             |
|                        +-------------+------------+                             |
|                                      |                                          |
|                   +------------------+------------------+                       |
|                   |                                     |                       |
|                   v (Active: Slot Blue)                 v (Candidate: Slot Green|
|        +---------------------+               +---------------------+            |
|        |      app_blue       |               |      app_green      |            |
|        |    Port: 8081       |               |    Port: 8082       |            |
|        |   Status: Serving   |               |   Status: Warming   |            |
|        +---------------------+               +----------+----------+            |
|                                                         |                       |
|                                                1. Pre-flight Probe              |
|                                                2. Canary Evaluation             |
|                                                         |                       |
|             <-- [Atomic mv active_upstream.conf + nginx -s reload] <--+         |
|                                                                                 |
|   * On Error: Automatic Rollback Trap triggers sub-500ms revert to Slot Blue    |
+---------------------------------------------------------------------------------+
```

---

## Core Engineering Capabilities

### 1. Zero-Downtime Blue/Green Deployment Controller (`scripts/deploy.sh`)
- Inspects `deploy_state.json` to identify active versus candidate deployment slots.
- Provisions candidate slot in isolation without disrupting existing client connections.
- Executes pre-flight health sentinel polling `/health/ready` with exponential backoff.
- Executes synthetic canary validation before switching production ingress.
- Performs atomic cutover by creating `active_upstream.conf.tmp` and replacing `active_upstream.conf` via single atomic POSIX `mv` syscall, followed by `nginx -s reload` (zero dropped connections).

### 2. Circuit-Breaker Automated Rollback Engine (`scripts/rollback.sh`)
- Embedded in deployment scripts via POSIX shell `trap rollback_on_failure EXIT`.
- If health probes fail, canary latency degrades, or error thresholds are breached, the controller triggers immediate rollback:
  - Reverts upstream proxy configuration in $<500\text{ ms}$.
  - Signals Nginx reload.
  - Updates audit state in `deploy_state.json`.
  - Exits with non-zero failure code without exposing broken releases to clients.

### 3. Production Microservice Probes & Observability (`app/main.py`)
- **`/health/live`**: Validates process execution and event loop responsiveness.
- **`/health/ready`**: Validates operational readiness and dependency connectivity (returns HTTP 503 during warmup or simulated downtime).
- **`/version`**: Returns JSON payload with slot identifier, commit hash, uptime, and version.
- **`/metrics`**: Exposes Prometheus exposition format counters (`http_requests_total`) and gauges (`http_request_duration_ms_avg`, `app_uptime_seconds`).
- **`/api/v1/work`**: Production workload endpoint with `X-Canary: true` request tagging.
- **`/simulate/unhealthy`**: Admin diagnostic endpoint for intentional fault injection during CI automated rollback drills.

---

## Repository Structure

```
├── .github/
│   └── workflows/
│       └── ci.yml                 # Multi-stage CI/CD workflow
├── app/
│   ├── __init__.py
│   └── main.py                    # WSGI microservice with probes & Prometheus metrics
├── nginx/
│   ├── active_upstream.conf       # Dynamically included upstream server definition
│   └── nginx.conf                 # Production reverse proxy configuration
├── scripts/
│   ├── canary.sh                  # Synthetic canary evaluation script
│   ├── deploy.sh                  # Blue/Green deployment controller
│   ├── health_probe.sh            # Deterministic health probe sentinel
│   └── rollback.sh                # Automated circuit-breaker rollback script
├── tests/
│   ├── __init__.py
│   ├── test_application.py        # Probes, metrics, and endpoint tests
│   └── test_deployment_scripts.py # Shell script execution and rollback tests
├── Dockerfile                     # Multi-stage non-root container image
├── docker-compose.yml             # Blue/Green orchestration topology
├── pytest.ini                     # Pytest configuration
├── requirements.txt               # Pinned dependencies
└── README.md                      # Documentation
```

---

## Local Development & Verification

### 1. Setup Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Run Deterministic Test Suite
```bash
pytest -v --cov=app --cov-report=term-missing
```

Output:
```text
============================== 14 passed in 4.06s ==============================
Coverage: 91%
```

### 3. Static Syntax Analysis
```bash
python -m py_compile app/main.py
bash -n scripts/*.sh
```

### 4. Blue/Green Deployment with Docker Compose
```bash
# Start Blue service and Nginx proxy
docker compose up -d app_blue nginx_proxy

# Execute Zero-Downtime Deployment to Green
./scripts/deploy.sh 1.1.0 $(git rev-parse --short HEAD)

# Verify active upstream
cat nginx/active_upstream.conf
# Output: server app_green:8080 max_fails=2 fail_timeout=5s;

# Trigger Automated Rollback
./scripts/rollback.sh blue
# Output: server app_blue:8080 max_fails=2 fail_timeout=5s;
```

---

## Author
**Simon M. Munyambu**  
GitHub: [@mtembez](https://github.com/mtembez)  
Email: simonmaeleq7@gmail.com
