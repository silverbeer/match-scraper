# Dockerfile for MLS Match Scraper
# Runs as a K3s CronJob with Playwright for browser-based scraping

FROM python:3.12-slim

# Install system dependencies for Playwright and git for pip
RUN apt-get update && apt-get install -y \
    git \
    wget \
    unzip \
    fontconfig \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libxss1 \
    libxtst6 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Install uv for dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock README.md ./

# Install Python dependencies
RUN uv export --no-dev --frozen --no-hashes > requirements.txt && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ /app/src/

# Create a non-root user for security and set up log directory
RUN useradd -m -u 1000 scraper && \
    mkdir -p /var/log/scraper && \
    chown -R scraper:scraper /app /var/log/scraper

# Install Playwright browsers as the scraper user
USER scraper
RUN playwright install chromium

# Set environment variables
ENV PYTHONPATH=/app
ENV PLAYWRIGHT_BROWSERS_PATH=/home/scraper/.cache/ms-playwright

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Default command (can be overridden by Kubernetes)
CMD ["python", "-m", "src.cli.main"]
