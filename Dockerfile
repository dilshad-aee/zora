# ──────────────────────────────────────────────────────────────────
# Zora Music — Production Dockerfile for Render
# ──────────────────────────────────────────────────────────────────

FROM python:3.11-slim

# Install system dependencies (ffmpeg for audio conversion, curl for healthchecks)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create required directories
RUN mkdir -p downloads/thumbnails

# Expose port (Render provides $PORT)
EXPOSE 10000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${PORT:-10000}/ || exit 1

# Start with gunicorn (production WSGI server)
CMD gunicorn \
    --bind 0.0.0.0:${PORT:-10000} \
    --workers 2 \
    --threads 4 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    "run:app"
