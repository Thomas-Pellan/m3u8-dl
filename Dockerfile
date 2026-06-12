FROM python:3.12-slim

# ffmpeg for segment assembly; git/curl for pip installs from VCS
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/

# Core package + web server extras
RUN pip install --no-cache-dir -e ".[web]"

# Install camoufox
RUN pip install --no-cache-dir "camoufox[geoip] @ git+https://github.com/JWriter20/camoufox.git#subdirectory=pythonlib"

# System libraries needed by camoufox's patched Firefox (requires root)
RUN playwright install-deps firefox

# Create a non-root user whose UID/GID match the host user so that files
# written to the mounted output volume are owned by the host user, not root.
ARG UID=1000
ARG GID=1000
RUN groupadd -g ${GID} app && \
    useradd -m -u ${UID} -g ${GID} -d /home/app app && \
    mkdir -p /output && chown app:app /output

USER app
ENV HOME=/home/app

# Download camoufox's patched Firefox binary as the app user so the path is
# accessible at runtime (stored under $HOME, not /root).
RUN camoufox fetch

# ── defaults (all overridable at runtime via env / docker-compose) ──────────
ENV M3U8DL_OUTPUT_DIR=/output
ENV M3U8DL_TEMP_DIR=/tmp/m3u8-dl
ENV M3U8DL_HEADLESS=true
ENV M3U8DL_CAPTURE_MODE=auto
ENV M3U8DL_PREFERRED_QUALITY=best
ENV M3U8DL_MAX_PARALLEL_DOWNLOADS=6

VOLUME /output
EXPOSE 8080

CMD ["m3u8-dl-web"]
