# Stage 1: Build frontend
FROM node:20-slim AS frontend-build

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --ignore-scripts
COPY frontend/ ./
RUN npm run build

# Stage 2: Runtime
FROM python:3.12-slim

# Install Node.js 20 (required for Claude Code CLI) and gosu (for privilege drop)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    gnupg \
    gosu \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code@0.2.61

# Install GitHub CLI
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# Set up Python app
WORKDIR /app

COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir .

# Copy built frontend
COPY --from=frontend-build /build/frontend/dist ./frontend/dist

# Create non-root user (claude CLI refuses --dangerously-skip-permissions as root)
RUN useradd -m -s /bin/bash agent0

# Create data directory
RUN mkdir -p /data/workspaces /data/audit

# Entrypoint: fix /data ownership then drop to agent0
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV CLAUDE_CODE_ACCEPT_TOS=true

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:9999/health || exit 1

EXPOSE 9999

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "-m", "agent0"]
