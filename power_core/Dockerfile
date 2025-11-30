FROM python:3.12-slim
ENV PYTHONUNBUFFERED=True \
    APP_HOME=/app \
    PORT=8080 \
    PYTHONPATH="/app" \
    JAVA_HOME="/usr/lib/jvm/java-21-openjdk-amd64"
WORKDIR $APP_HOME

# --- 1. Install Java (System Layer) ---
RUN apt-get update && apt-get install -y --no-install-recommends \
    openjdk-21-jre-headless \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
# Check Java installation (Optional, good for build logs)
RUN java -version

# Variant 2: 1.there we add locale package from inside docker context
COPY ./gcp_actions ./gcp_actions

# --- 2. Install Python Dependencies (Cache Layer) ---
COPY requirements.txt .
RUN apt-get update \
    && apt-get install -y --no-install-recommends git build-essential \
    && pip install \
        --no-cache-dir \
        --disable-pip-version-check \
        --no-warn-script-location \
        --root-user-action=ignore \
        -r requirements.txt \
    && apt-get purge -y --auto-remove build-essential \
    && rm -rf /var/lib/apt/lists/*

# Variant 2: 2. There we install it
RUN pip install --no-cache-dir ./gcp_actions[processing-worker]

# --- 3. Copy Source Code (Application Layer) ---
# This is the most frequently changing layer, so it goes last.
# Context: Copies 'Project/power_core/' content into '/app/'
# Result: Your inner package is now at '/app/power_core/'

# Variant 1 without loaded localy packages, because anything not loaded from inside of context
#COPY . .

# Variant 2: There we write more preciously path of main project
COPY ./power_core ./power_core

# --- 4. Entry Point ---
# PYTHONPATH is /app.
# We import 'power_core.main', which maps to '/app/power_core/main.py'
CMD ["sh", "-c", "gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 power_core.main:app"]
#CMD ["sh", "-c", "echo '--- DEBUG: Listing files in /app ---' && ls -lR /app && echo '--- DEBUG: Python Path ---' && python -c 'import sys; print(sys.path)' && echo '--- DEBUG: Starting Gunicorn ---' && gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 power_core.main:app"]
