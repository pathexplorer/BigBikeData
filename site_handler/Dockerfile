FROM python:3.12-slim
ENV PYTHONUNBUFFERED=True \
    APP_HOME=/app \
    PORT=8080 \
    PYTHONPATH="/app"

WORKDIR $APP_HOME

# Variant 2: 1.there we add locale package from inside docker context
COPY ./gcp_actions ./gcp_actions

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

# Variant 1 without loaded localy packages, because anything not loaded from inside of context
#COPY . .

# Variant 2: There we write more preciously path of main project
COPY ./site_handler ./site_handler

# Structure Mapping:
# Host: Project/site_handler/site_handler/main.py
# Container: /app/site_handler/main.py
# Python Module: site_handler.main

# Run the web server on container startup.
# Gunicorn is a production-ready WSGI server.
# The 'workers' and 'threads' flags can be tuned for performance.
CMD ["sh", "-c", "gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 site_handler.main:app"]
#CMD ["sh", "-c", "echo '--- DEBUG: Listing files in /app ---' && ls -lR /app && echo '--- DEBUG: Python Path ---' && python -c 'import sys; print(sys.path)' && echo '--- DEBUG: Starting Gunicorn ---' && gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 site_handler.main:app"]

