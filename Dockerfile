# Copyright 2026 Michael Ryan Hunsaker, M.Ed., Ph.D.
# SPDX-License-Identifier: Apache-2.0
#
# Multi-stage build for 3dmake-gui-wrapper
# Stage 1: build/install dependencies
# Stage 2: minimal runtime image

# ── Stage 1: builder ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy only what is needed to resolve dependencies first (layer-cache friendly)
COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/

# Install the project and its runtime dependencies into /install
RUN pip install --no-cache-dir --prefix=/install ".[viewer]"

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

LABEL org.opencontainers.image.title="3dmake-gui-wrapper" \
      org.opencontainers.image.description="NiceGUI-based GUI wrapper for 3dmake / OpenSCAD" \
      org.opencontainers.image.version="2026.04.29" \
      org.opencontainers.image.authors="Michael Ryan Hunsaker <github@mail.hunsakerweb.com>" \
      org.opencontainers.image.source="https://github.com/mrhunsaker/3dmakeGUI" \
      org.opencontainers.image.licenses="Apache-2.0"

# Runtime system packages: openscad for 3D rendering, xvfb for headless display
RUN apt-get update && apt-get install -y --no-install-recommends \
        openscad \
        xvfb \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Create a non-root user
RUN groupadd --gid 1001 appgroup \
 && useradd --uid 1001 --gid appgroup --shell /bin/bash --create-home appuser

# Application data / settings directory (mounted as a volume by users)
RUN mkdir -p /home/appuser/.config/3dmake-gui \
 && chown -R appuser:appgroup /home/appuser/.config

USER appuser
WORKDIR /home/appuser

# NiceGUI listens on 8080 inside the container.
# Bind only to localhost on the host unless you have a reverse proxy.
EXPOSE 8080

# Health-check: verify the HTTP server is up
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/')" \
    || exit 1

# Start the application (headless NiceGUI web server, no native window)
CMD ["python", "-m", "tdmake_gui_wrapper", "--host", "0.0.0.0", "--port", "8080"]
