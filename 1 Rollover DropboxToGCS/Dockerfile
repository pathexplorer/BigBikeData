# Use the official lightweight Python image.
FROM python:3.10


# istall Java
#RUN DEBIAN_FRONTEND=noninteractive apt-get update && apt-get install -y --no-install-recommends \
#    openjdk-21-jre-headless \
#    && apt-get clean \
#    && rm -rf /var/lib/apt/lists/*
# Checking Java
#RUN java -version

# Set environment variables
ENV PYTHONUNBUFFERED=True
ENV APP_HOME=/app
ENV PORT=8080
WORKDIR $APP_HOME
COPY . ./

# Install production dependencies.
RUN pip install --no-cache-dir --disable-pip-version-check --no-warn-script-location -r requirements.txt

# Run the web server on container startup.
# Gunicorn is a production-ready WSGI server.
# The 'workers' and 'threads' flags can be tuned for performance.
CMD ["sh", "-c", "gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 main:app"]
