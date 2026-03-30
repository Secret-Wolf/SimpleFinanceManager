# Finanzmanager Docker Image
# Multi-stage build for smaller image size

FROM python:3.11-slim AS builder

WORKDIR /app

# Install dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Production image
FROM python:3.11-slim

# Install gosu for privilege dropping in entrypoint
RUN apt-get update && apt-get install -y --no-install-recommends gosu && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /app/.local
RUN chown -R appuser:appuser /app/.local
ENV PATH=/app/.local/bin:$PATH
ENV PYTHONUSERBASE=/app/.local

# Copy application code
COPY --chown=appuser:appuser backend/ ./backend/
COPY --chown=appuser:appuser frontend/ ./frontend/

# Create data directory with correct ownership
RUN mkdir -p /app/data && chown -R appuser:appuser /app/data

# Entrypoint fixes volume permissions at runtime, then drops to appuser
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

WORKDIR /app/backend
ENTRYPOINT ["/entrypoint.sh"]
