# This Dockerfile should be in the project root (e.g., BigBikeData/)
FROM python:3.12-slim

# istall Java
RUN DEBIAN_FRONTEND=noninteractive apt-get update && apt-get install -y --no-install-recommends \
    openjdk-21-jre-headless \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
# Checking Java
RUN java -version

# Set environment variables
ENV PYTHONUNBUFFERED=True
ENV APP_HOME=/app
ENV PORT=8080

# Set the Python Path to include the app root.
# This allows imports like 'from power_core...' and 'from routes...' to work.
ENV PYTHONPATH=$APP_HOME

WORKDIR $APP_HOME
COPY . ./

# Install production dependencies.
# Note the updated path to requirements.txt
RUN apt-get update \
    && apt-get install -y --no-install-recommends git build-essential \
    \
    && pip install \
        --no-cache-dir \
        --disable-pip-version-check \
        --no-warn-script-location \
        --root-user-action=ignore \
        -r power_core/requirements.txt \
    \
    && apt-get purge -y --auto-remove build-essential \
    && rm -rf /var/lib/apt/lists/*

# Run the web server on container startup.
# Gunicorn is a production-ready WSGI server.
# The entrypoint is now power_core.main
CMD ["sh", "-c", "gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 power_core.main:app"]
