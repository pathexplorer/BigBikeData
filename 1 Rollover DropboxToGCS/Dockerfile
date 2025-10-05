# Use the official lightweight Python image.
FROM python:3.9-slim

# Set environment variables
ENV PYTHONUNBUFFERED True
ENV APP_HOME /app
WORKDIR $APP_HOME
COPY . ./

# Install production dependencies.
RUN pip install --no-cache-dir -r requirements.txt

# Run the web server on container startup.
# Gunicorn is a production-ready WSGI server.
# The 'workers' and 'threads' flags can be tuned for performance.
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 main:app