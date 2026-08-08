"""Central configuration for power_core: loads env-derived constants and fails fast when required variables are missing."""
import os
import sys
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pre-flight check — fail fast with a clear message if critical vars are unset.
# This prevents confusing downstream errors like "/secrets/None/versions/latest".
# ---------------------------------------------------------------------------
_REQUIRED_ENV_VARS = [
    ("GCP_PROJECT_ID",       "export GCP_PROJECT_ID=local-test-project  (or ./local_dev.sh env)"),
    ("APP_JSON_KEYS",        "add to local_config.json"),
    ("SEC_DROPBOX",          "add to local_config.json"),
    ("S_ACCOUNT_DROPBOX",    "add to local_config.json"),
    ("S_ACCOUNT_RUN",        "add to local_config.json"),
]

_missing = [(name, hint) for name, hint in _REQUIRED_ENV_VARS if not os.environ.get(name)]
if _missing:
    lines = []
    for name, hint in _missing:
        lines.append(f"  • {name}")
        lines.append(f"    → {hint}")
    print(
        "\n" + "=" * 60 + "\n"
        "\033[31m❌  MISSING REQUIRED ENVIRONMENT VARIABLES\033[0m\n"
        + "=" * 60 + "\n"
        "The following variables must be set before starting the app:\n\n"
        + "\n".join(lines) +
        "\n\n💡  Quick fix for local dev:\n"
        "    1. Add missing vars to BigBikeData/local_config.json\n"
        "    2. Or run:  source <(./local_dev.sh env)\n"
        + "=" * 60 + "\n",
        file=sys.stderr,
    )
    sys.exit(1)

try:
    GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
    APP_JSON_KEYS = os.environ.get("APP_JSON_KEYS")
    # -------------- Configuration --------------
    GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME")
    GCS_PUB_OUTPUT_BUCKET=os.environ.get("GCS_PUB_OUTPUT_BUCKET")
    EMAIL_MODE=os.environ.get("EMAIL_MODE")
    STRAVA_UPLOAD = os.environ.get("STRAVA_UPLOAD")


    # -------------- Brevo Email --------------
    BREVO_API_KEY = os.environ.get("BREVO_API_KEY")
    SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
    SENDER_NAME = os.environ.get("SENDER_NAME")
    # -------------- SMTP Email --------------
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
    SMTP_SENDER = os.environ.get("SMTP_SENDER")
    SMTP_SERVER = os.environ.get("SMTP_SERVER")
    SMTP_PORT = os.environ.get("SMTP_PORT")
    SMTP_USER = os.environ.get("SMTP_USER")
    CLOUD_RUN_SERVICE = os.environ.get("CLOUD_RUN_SERVICE")
    CLOUD_RUN_SERVICE_PUB = os.environ.get("CLOUD_RUN_SERVICE_PUB")
    EVENTARC_SA=os.environ.get("EVENTARC_SA")
    EVENTARC_TRIGGER=os.environ.get("EVENTARC_TRIGGER")
    GCP_TOPIC_NAME=os.environ.get("GCP_TOPIC_NAME")
    DROPBOX_TOPIC_NAME=os.environ.get("DROPBOX_TOPIC_NAME")
    DROpbox_WEBHOOK_PATH=os.environ.get("DROpbox_WEBHOOK_PATH")
    COOKIE_DOMAIN=os.environ.get("COOKIE_DOMAIN")
    # Dropbox and Strava
    SEC_STRAVA=os.environ.get("SEC_STRAVA")

    s_email_run = os.environ.get("S_ACCOUNT_RUN")
    s_email_dropbox = os.environ.get("S_ACCOUNT_DROPBOX")
    SEC_DROPBOX = os.environ.get("SEC_DROPBOX")
    s_email_strava = os.environ.get("S_ACCOUNT_STRAVA")
    PRIVATE_ACCESS_TOKEN=os.environ.get("PRIVATE_ACCESS_TOKEN")
    PRIVATE_UPLOAD_TOKEN=os.environ.get("PRIVATE_UPLOAD_TOKEN")
    FRONTEND_BASE_URL=os.environ.get("FRONTEND_BASE_URL")
    DONATION_HTML_SNIPPET_MONO = os.environ.get("DONATION_HTML_SNIPPET_MONO", "")
    DONATION_HTML_SNIPPET_PRIVAT = os.environ.get("DONATION_HTML_SNIPPET_PRIVAT", "")
    # LOGGING_LEVEL=os.environ.get("LOGGING_LEVEL")

    # VERSION MANAGEMENT
    BACKEND_TAG=os.environ.get("BACKEND_TAG")
    FRONTEND_TAG=os.environ.get("FRONTEND_TAG")

except KeyError as e:
    logger.critical(f"FATAL: Missing required environment variable: {e}")
    raise EnvironmentError(f"Configuration missing from environment: {e}")

LOGGING_LEVEL="DEBUG"
DROPBOX_REDIRECT_URI = "http://localhost:5000/oauth/callback"
STRAVA_REDIRECT_URI="http://localhost:5000/exchange_token"
# Pathes
DROPBOX_WATCHED_FOLDER = "/apps/activities"
LOCAL_TMP = "/tmp"
# load heatmap, app route "upload to dropbox"
DROPBOX_HEATMAP = "heatmap"
GSC_HEATMAP_PATH = "heatmap"
HEATMAP_FILES = ['mtb.gpx','gravel.gpx']
CHUNK_SIZE = 8 * 1024 * 1024  # 8MB
