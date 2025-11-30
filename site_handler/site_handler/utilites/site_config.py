import os
import logging
logger = logging.getLogger(__name__)

try:
    # -------------- Loaded environment variables from YAML, access immediately --------------
    GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
    APP_JSON_KEYS = os.environ.get("APP_JSON_KEYS")
    # -------------- Initialization secret and firestore clients --------------
    GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME")
    GCS_PUB_INPUT_BUCKET=os.environ.get("GCS_PUB_INPUT_BUCKET")
    GCS_PUB_OUTPUT_BUCKET=os.environ.get("GCS_PUB_OUTPUT_BUCKET")
    S_ACCOUNT_RUN = os.environ.get("s_email_run")
    CLOUD_RUN_SERVICE = os.environ.get("CLOUD_RUN_SERVICE")
    GCP_TOPIC_NAME = os.environ.get("GCP_TOPIC_NAME")

    FLASK_SECRET_KEY = os.environ.get("FLASK_SECRET_KEY")
    ALLOWED_DOMAINS = os.environ.get("ALLOWED_DOMAINS")

except KeyError as e:
    logger.critical(f"FATAL: Missing required environment variable: {e}")
    raise EnvironmentError(f"Configuration missing from environment: {e}")

if __name__ == "__main__":
    print("")
