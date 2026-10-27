# ==============================================================================
# Multi-stage production container image for DevOps Automation Pipeline
# ==============================================================================
FROM python:3.13-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Final minimal runtime image
FROM python:3.13-slim AS runner

LABEL maintainer="Simon M. Munyambu <simonmaeleq7@gmail.com>"
LABEL org.opencontainers.image.title="DevOps Automation Pipeline Service"
LABEL org.opencontainers.image.description="Zero-downtime microservice with health probes and Prometheus metrics"

WORKDIR /app

# Create non-root system group and user
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /sbin/nologin -d /app appuser && \
    apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PORT=8080

COPY --chown=appuser:appgroup . /app

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=5s --timeout=3s --start-period=3s --retries=3 \
    CMD curl -f http://localhost:8080/health/ready || exit 1

CMD ["python", "app/main.py"]
