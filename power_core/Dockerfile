# --- Stage 1: Build Environment ---
FROM python:3.12-slim as builder

# Set environment variables
ENV PYTHONUNBUFFERED=True \
    APP_HOME=/app
WORKDIR $APP_HOME

# Install build-time dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends git build-essential && \
    rm -rf /var/lib/apt/lists/*

# Copy local package first
COPY ./gcp_actions ./gcp_actions

# Install Python dependencies
COPY requirements.txt .
RUN pip install \
    --no-cache-dir \
    --disable-pip-version-check \
    --no-warn-script-location \
    --root-user-action=ignore \
    -r requirements.txt

# --- Stage 2: Production Environment ---
FROM python:3.12-slim

# Set environment variables
ENV PYTHONUNBUFFERED=True \
    APP_HOME=/app \
    PORT=8080 \
    PYTHONPATH="/app" \
    JAVA_HOME="/usr/lib/jvm/java-21-openjdk-amd64"
WORKDIR $APP_HOME

# Install Java (runtime dependency)
RUN apt-get update && \
    apt-get install -y --no-install-recommends openjdk-21-jre-headless && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy installed Python packages and executables from the build stage
COPY --from=builder /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Copy application code
COPY ./power_core ./power_core

# Set the entry point
CMD ["sh", "-c", "gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 power_core.main:app"]
#CMD ["sh", "-c", "echo '--- DEBUG: Listing files in /app ---' && ls -lR /app && echo '--- DEBUG: Python Path ---' && python -c 'import sys; print(sys.path)' && echo '--- DEBUG: Starting Gunicorn ---' && gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 power_core.main:app"]
