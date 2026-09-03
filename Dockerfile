# ==============================================================================
# TokenPulse — Dockerfile
# Production-ready, secure, unprivileged container for TokenPulse
# ==============================================================================

FROM python:3.12-slim AS builder

WORKDIR /build

# Install build tools if any C extensions require compiling
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Final stage
FROM python:3.12-slim AS runner

# Security: run as non-root user
RUN groupadd -g 1001 appgroup && \
    useradd -u 1001 -g appgroup -s /bin/bash -m appuser

WORKDIR /app

# Install runtime dependencies (curl for container healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /root/.local /home/appuser/.local
ENV PATH="/home/appuser/.local/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Copy application files
COPY --chown=appuser:appgroup backend /app/backend
COPY --chown=appuser:appgroup frontend /app/frontend

# Create data directory with restricted permissions (0700)
RUN mkdir -p /app/backend/data && \
    chown -R appuser:appgroup /app/backend/data && \
    chmod 700 /app/backend/data

USER appuser

WORKDIR /app/backend

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/api/ping || exit 1

CMD ["python", "main.py"]
