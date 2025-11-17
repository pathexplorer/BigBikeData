FROM python:3.12-slim

# Set environment variables
ENV PYTHONUNBUFFERED=True
ENV APP_HOME=/app
ENV PORT=8080
WORKDIR $APP_HOME
COPY . ./

RUN apt-get update \
    # 1. Install git (and build-essential, which is good practice for C extensions)
    && apt-get install -y --no-install-recommends git build-essential \
    \
    # 2. Run pip install *after* git is available
    && pip install \
        --no-cache-dir \
        --disable-pip-version-check \
        --no-warn-script-location \
        --root-user-action=ignore \
        -r requirements.txt \
    \
    # 3. Clean up the apt cache to keep the final image slim
    && apt-get purge -y --auto-remove build-essential \
    && rm -rf /var/lib/apt/lists/*

# Run the web server on container startup.
# Gunicorn is a production-ready WSGI server.
# The 'workers' and 'threads' flags can be tuned for performance.
CMD ["sh", "-c", "gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 main:app"]
