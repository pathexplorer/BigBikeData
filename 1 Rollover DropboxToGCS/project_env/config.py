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
GCS_CLOUD_PROJECT = os.environ.get("GCS_CLOUD_PROJECT")

# Dropbox and GCS configuration
SECRET_DROPBOX_APP_SECRET = "dropbox-app-secret"
SECRET_DROPBOX_REFRESH_TOKEN = "dropbox-refresh-token"
DROPBOX_APP_KEY = "dropbox-app-key"
DROPBOX_REDIRECT_URI= "http://localhost:5000/oauth/callback"

# Strava
STRAVA_CLIENT_ID="strava-client-id"
STRAVA_SECRET="strava-client-secret"
STRAVA_REDIRECT_URI="http://localhost:5000/exchange_token"

# Pathes
DROPBOX_WATCHED_FOLDER = "/apps/wahoofitness"
GSC_ORIG_FIT_FOLDER=f"{GCS_CLOUD_PROJECT}/apps/wahoofitness"
LOCAL_TMP = "/tmp"

# load heatmap, app route "upload to dropbox"
DROPBOX_HEATMAP = "heatmap"
GSC_HEATMAP_PATH = "heatmap"
HEATMAP_FILES = ['mtb.gpx','gravel.gpx']
CHUNK_SIZE = 8 * 1024 * 1024  # 8MB

# Indexes
CURSOR_BLOB = "tmp/dropbox_cursor.json"
MAINFEST_GSC_PATH = f"{GCS_CLOUD_PROJECT}/manifests.json"

