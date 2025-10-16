import os
from dotenv import load_dotenv
#load_dotenv()
load_dotenv(dotenv_path="../other/keys.env") # Only for local test

# ---- Configuration ----
# GCP credentials
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME")  # Set as environment variable
print("Loaded GCS_BUCKET_NAME:", GCS_BUCKET_NAME)
GCS_CLOUD_PROJECT = os.environ.get("GCS_CLOUD_PROJECT")

# Dropbox and GCS configuration
SECRET_DROPBOX_APP_SECRET = "dropbox-app-secret"
SECRET_DROPBOX_REFRESH_TOKEN = "dropbox-refresh-token"
DROPBOX_APP_KEY = "dropbox-app-key"

# Pathes
DROPBOX_WATCHED_FOLDER = "/apps/wahoofitness" # The folder to monitor (case-insensitive)
GSC_ORIG_FIT_FOLDER=f"{GCS_CLOUD_PROJECT}/apps/wahoofitness"

# load heatmap, app route "upload to dropbox"
DROPBOX_HEATMAP = "heatmap"
GSC_HEATMAP_PATH = "heatmap"
HEATMAP_FILES = ['mtb.gpx','gravel.gpx']
CHUNK_SIZE = 8 * 1024 * 1024  # 8MB

# Indexes
CURSOR_BLOB = "tmp/dropbox_cursor.json"
MAINFEST_GSC_PATH = f"{GCS_CLOUD_PROJECT}/manifests.json"

