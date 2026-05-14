# anker-mini — 24/7 Obsidian automation container
#
# What's inside:
#   - obsidian-headless (npm)        → bidirectional vault sync via Obsidian Sync
#   - Claude Code CLI                → skill execution
#   - anker-mini (this repo)         → Telegram bot + cron-driven scheduler
#   - cron daemon                    → fires scheduled skills
#
# Volumes (declared in docker-compose.yml):
#   /vault            → the Obsidian vault (synced via ob)
#   /state/obsidian   → ~/.obsidian-headless (auth token, sync config)
#   /state/ankermini  → ~/.ankermini (config + schedules)
#   /state/claude     → ~/.claude (Claude Code OAuth)
#   /state/logs       → skill output logs

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:/root/.local/bin"

# Base OS + python + node 22 + tools
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl gnupg \
      git tini cron tzdata openssl \
      python3.12 python3.12-venv python3-pip \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# uv (fast Python package manager) — used by anker-mini
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    cp /root/.local/bin/uv /usr/local/bin/uv && \
    cp /root/.local/bin/uvx /usr/local/bin/uvx

# obsidian-headless
RUN npm install -g obsidian-headless

# Claude Code CLI — official install script
RUN curl -fsSL https://claude.ai/install.sh | bash && \
    ln -sf /root/.local/bin/claude /usr/local/bin/claude || true

# Working dir for the app
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY code ./code
COPY examples ./examples
COPY scripts ./scripts

# Install Python deps into a venv in /app/.venv
RUN uv sync --frozen

# State layout: HOME=/root, symlinks from /root/.foo → /state/foo (set up in entrypoint).
# This way tool defaults (~/.obsidian-headless etc.) work AND state is at a clean
# inspectable path inside the volume.
ENV HOME=/root \
    PYTHONPATH=/app

# Symlinks: state-volume layout → expected paths
# (handled at runtime by entrypoint.sh because /state is a volume)

# Cron file location — entrypoint regenerates this from skill anker_cron fields
RUN mkdir -p /var/spool/cron/crontabs && touch /var/spool/cron/crontabs/root && chmod 600 /var/spool/cron/crontabs/root

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# tini for proper signal handling (SIGTERM → graceful shutdown of all 3 children)
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint.sh"]
