# Match-Scraper Dockerfile for GKE Deployment
# Builds a container with Playwright, Celery, and all dependencies
# Platform: linux/amd64 (for GKE compatibility)

FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies for Playwright and Git dependencies
# These are required for running Chromium in a container
RUN apt-get update && apt-get install -y \
    git \
    wget \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libwayland-client0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    libu2f-udev \
    libvulkan1 \
    && rm -rf /var/lib/apt/lists/*

# Install uv (fast Python package installer)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first (for better Docker layer caching)
COPY pyproject.toml uv.lock ./

# Copy README.md (required by hatchling build backend)
COPY README.md ./

# Set Playwright browsers path BEFORE installation
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Install Python dependencies
# --frozen ensures reproducible builds
# --no-dev skips development dependencies
RUN uv sync --frozen --no-dev

# Install Playwright browsers (Chromium only for smaller image size)
# --with-deps ensures all browser dependencies are installed
RUN uv run playwright install chromium --with-deps

# Make Playwright browsers directory writable
RUN chmod -R 777 /ms-playwright

# Copy application source code
# This is done last to maximize Docker layer caching
COPY . .

# Set environment variables
# NO_COLOR=1 disables Rich terminal formatting for cleaner container logs
ENV NO_COLOR=1
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO

# Set HOME to /app for uv cache (fixes permission issues in Kubernetes)
ENV HOME=/app
ENV UV_CACHE_DIR=/app/.cache/uv
# Set Playwright browsers path to persist across HOME changes
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Make entire /app directory writable for Kubernetes non-root execution
# This allows uv to create/modify .venv and cache directories
RUN chmod -R 777 /app

# Health check (optional - checks if Python works)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Default command: Run scraper with queue submission
# Can be overridden by Kubernetes CronJob
CMD ["uv", "run", "mls-scraper", "scrape", \
     "--age-group", "U14", \
     "--division", "Northeast", \
     "--use-queue", \
     "--no-api"]

# Build command for GKE (AMD64):
# docker build --platform linux/amd64 -t us-central1-docker.pkg.dev/missing-table/missing-table/match-scraper:latest .
#
# Local build (current platform):
# docker build -t match-scraper:local .
#
# Test locally:
# docker run --rm -e RABBITMQ_URL="amqp://admin:admin123@host.docker.internal:5672//" match-scraper:local
