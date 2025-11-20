import os
from dotenv import load_dotenv

# Cloud Run assets K_SERVICE. If it is not present, is locally env
IS_LOCAL = os.environ.get("K_SERVICE") is None

if IS_LOCAL: # then load .env file
    dotenv_path = os.path.join(os.path.dirname(__file__), "../project_env/keys.env")
    load_dotenv(dotenv_path=dotenv_path, override=False)

# -------------- Configuration --------------
# GCP credentials
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME")
GCS_PUB_INPUT_BUCKET=os.environ.get("GCS_PUB_INPUT_BUCKET")
GCS_PUB_OUTPUT_BUCKET=os.environ.get("GCS_PUB_OUTPUT_BUCKET")
CLOUD_RUN_SERVICE = os.environ.get("CLOUD_RUN_SERVICE")
CLOUD_RUN_SERVICE_PUB = os.environ.get("CLOUD_RUN_SERVICE_PUB")
EVENTARC_SA=os.environ.get("EVENTARC_SA")
EVENTARC_TRIGGER=os.environ.get("EVENTARC_TRIGGER")
GCP_TOPIC_NAME=os.environ.get("GCP_TOPIC_NAME")
EMAIL_MODE=os.environ.get("EMAIL_MODE")
# Dropbox and Strava
SEC_STRAVA=os.environ.get("SEC_STRAVA")
SEC_DROPBOX=os.environ.get("SEC_DROPBOX")
BREVO_CREDENTIALS=os.environ.get("BREVO_API_KEY")
s_email_run = os.environ.get("S_ACCOUNT_RUN")
s_email_dropbox = os.environ.get("S_ACCOUNT_DROPBOX")
s_email_strava = os.environ.get("S_ACCOUNT_STRAVA")
PRIVATE_ACCESS_TOKEN=os.environ.get("PRIVATE_ACCESS_TOKEN")
PRIVATE_UPLOAD_TOKEN=os.environ.get("PRIVATE_UPLOAD_TOKEN")
DROPBOX_REDIRECT_URI = "http://localhost:5000/oauth/callback"
STRAVA_REDIRECT_URI="http://localhost:5000/exchange_token"
# Pathes
DROPBOX_WATCHED_FOLDER = "/apps/activities"
GSC_ORIG_FIT_FOLDER=f"{CLOUD_RUN_SERVICE}/apps/activities"
LOCAL_TMP = "/tmp"
# load heatmap, app route "upload to dropbox"
DROPBOX_HEATMAP = "heatmap"
GSC_HEATMAP_PATH = "heatmap"
HEATMAP_FILES = ['mtb.gpx','gravel.gpx']
CHUNK_SIZE = 8 * 1024 * 1024  # 8MB
# Indexes
CURSOR_BLOB = "tmp/dropbox_cursor.json"
MAINFEST_GSC_PATH = f"{CLOUD_RUN_SERVICE}/manifests.json"
SMTP_SERVER=os.environ.get("SMTP_SERVER")
SMTP_PORT=os.environ.get("SMTP_PORT")
SMTP_USER=os.environ.get("SMTP_USER")
SMTP_PASSWORD=os.environ.get("SMTP_PASSWORD")
SENDER_EMAIL=os.environ.get("SENDER_EMAIL")

# VERSION MANAGEMENT
BACKEND_TAG=os.environ.get("BACKEND_TAG")
FRONTEND_TAG=os.environ.get("FRONTEND_TAG")

