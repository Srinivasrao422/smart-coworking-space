# =========================================================================
# Production Dockerfile for Smart Co-Working Space Management
# Multi-platform compatible: AWS App Runner, AWS ECS, Lightsail, Docker
# =========================================================================

FROM python:3.13-slim AS production

# Set working directory
WORKDIR /app

# Set production environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    HOST=0.0.0.0

# Copy application code and assets
COPY app /app/app
COPY static /app/static
COPY run.py /app/run.py

# Create unprivileged system user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser \
    && chown -R appuser:appuser /app

USER appuser

# Expose standard container port
EXPOSE 8000

# Healthcheck to verify real-time server readiness
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/spaces')" || exit 1

# Start server entry point
CMD ["python", "run.py"]
