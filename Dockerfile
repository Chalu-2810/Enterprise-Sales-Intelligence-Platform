# syntax=docker/dockerfile:1
FROM python:3.12-slim

# curl is needed only for the HEALTHCHECK below; kept minimal and cleaned
# up in the same layer to avoid bloating the image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies in their own layer so code changes don't invalidate
# the (slow) dependency-install cache.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Now bring in the application code (includes the bundled sample database
# and default assets -- see .dockerignore for what's excluded).
COPY . .

# Run as a non-root user. UID/GID 1000 is arbitrary but fixed, so bind
# mounts from a host user with the same UID don't hit permission issues.
RUN groupadd --gid 1000 appuser \
    && useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser \
    && chown -R appuser:appuser /app

ENV STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_BROWSER_GATHERUSAGESTATS=false \
    PYTHONUNBUFFERED=1

EXPOSE 8501

# Streamlit exposes a built-in health endpoint -- no custom health route
# needed. start-period gives the app time to initialize the DB/view/users
# table on first boot before failures start counting.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl --fail http://localhost:8501/_stcore/health || exit 1

USER appuser

ENTRYPOINT ["streamlit", "run", "app.py"]
