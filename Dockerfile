# Image for the match-scraper CronJobs on K3s.
#
# Ships both console scripts from one install:
#   match-scraper-agent — the orchestrator (run, watch-release, audit, …)
#   mls-scraper         — the scraping CLI
#
# ENTRYPOINT is the orchestrator because that is what the CronJobs invoke.
# `mls-scraper` is reachable by overriding it.
#
# Structurally this is the agent repo's Dockerfile, which has run in
# production for months, with two changes: the build is pinned to uv.lock,
# and it drops the CLAUDE.md copy.

FROM python:3.12-slim AS base

RUN pip install --no-cache-dir uv

WORKDIR /app

# System libraries Playwright's chromium needs, plus git for the
# telegram-notify dependency.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libdbus-1-3 libxkbcommon0 libatspi2.0-0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 && \
    rm -rf /var/lib/apt/lists/*

# Dependencies first, so a source-only change does not reinstall them.
# --frozen keeps builds reproducible: the agent's Dockerfile synced from
# pyproject.toml alone, so two builds of one commit could resolve
# different versions.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --no-dev --frozen --no-install-project

RUN uv run playwright install chromium

COPY src/ src/
RUN uv sync --no-dev --frozen

# `uv run` re-syncs the environment before executing, which at runtime means
# every CronJob tick reinstalls the dev group over the network before doing
# any work — and fails outright if the network is down. The image is already
# synced, so tell uv to trust it. The CronJobs invoke `uv run
# match-scraper-agent …`, so this has to hold for them, not just the
# ENTRYPOINT.
ENV UV_NO_SYNC=1

ENTRYPOINT ["uv", "run", "match-scraper-agent"]
CMD ["run", "--json-logs"]
