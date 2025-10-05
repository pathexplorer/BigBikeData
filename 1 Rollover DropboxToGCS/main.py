import os
import hmac
import hashlib
import threading
import json
import dropbox
from flask import Flask, request, Response
from google.cloud import storage, secretmanager

# --- Configuration ---
# GCP Project ID and Secret Names from Secret Manager
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
if not GCP_PROJECT_ID:
    raise ValueError("GCP_PROJECT_ID not installs")
SECRET_DROPBOX_APP_SECRET = "dropbox-app-secret"
SECRET_DROPBOX_REFRESH_TOKEN = "dropbox-refresh-token"

# Dropbox and GCS configuration
DROPBOX_APP_KEY = os.environ.get("DROPBOX_APP_KEY")  # Set as environment variable
if not DROPBOX_APP_KEY:
    raise ValueError("DROPBOX_APP_KEY not installs")
DROPBOX_WATCHED_FOLDER = "/apps/wahoofitness" # The folder to monitor (case-insensitive)
GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME")  # Set as environment variable
if not GCS_BUCKET_NAME:
    raise ValueError("GCS_BUCKET_NAME not installs")
CURSOR_BLOB = "tmp/dropbox_cursor.json"


# --- Initialize Clients ---
app = Flask(__name__)
storage_client = storage.Client()
secret_client = secretmanager.SecretManagerServiceClient()


# GCS cursor
# Result is True or False
def load_cursor():
# 'loads' convert JSON into Dict, then reads key 'cursor'
# use '.get' instead 'loads(content)["cursor"]' because
# - if cursor doesnt exist, code is stops (KeyError)
# - must use try\except, instead simple check
# - in situation, where doesnt existing cursor is normal
    client = storage.Client()
    bucket = client.bucket(GCS_BUCKET_NAME)
    blob = bucket.blob(CURSOR_BLOB)
    if blob.exists():
        content = blob.download_as_text()
        return json.loads(content).get("cursor")
    else:
        print("Cursor doesn't exist. Creating...")
        return None

def save_cursor(cursor):
    client = storage.Client()
    bucket = client.bucket(GCS_BUCKET_NAME)
    blob = bucket.blob(CURSOR_BLOB)
    data = json.dumps({"cursor": cursor})
    blob.upload_from_string(data, content_type="application/json")

# Loading file in GCS
def upload_to_gcs(path, content):
# This function also rewrite as:
# storage.Client().bucket(GCS_BUCKET_NAME).blob(path).upload_from_string(content)
    client = storage.Client()
    bucket = client.bucket(GCS_BUCKET_NAME)
    blob = bucket.blob(path)
    blob.upload_from_string(content)
    print(f"File {path} loaded")

def sync_dropbox():
# The code use Flask, therefore that not needs to use context manager "with ... as dbx"
    print("Sync Dropbox → GCS starts")

    dbx_app_secret = get_secret(SECRET_DROPBOX_APP_SECRET)
    dbx_refresh_token = get_secret(SECRET_DROPBOX_REFRESH_TOKEN)
    print("APP_SECRET starts from:", dbx_app_secret[:4], "...")
    print("REFRESH_TOKEN starts from:", dbx_refresh_token[:4], "...")

    dbx = dropbox.Dropbox(
        app_key=DROPBOX_APP_KEY,
        app_secret=dbx_app_secret,
        oauth2_refresh_token=dbx_refresh_token
    )
    print("Dropbox-client is created, checking authorization...")
    try:
        dbx.users_get_current_account()
        print("Authorization in Dropbox succesful")
    except dropbox.exceptions.AuthError as e:
        print("Authorization in Dropbox FAILED", e)
        raise

    cursor = load_cursor()
    print(f"Cursor: {cursor}")

# If 'cursor' it any valid value, it is 'True' and start runing 'result=..'
# 'result' returns next data
#	ListFolderResult(
#	entries=[FileMetadata, FolderMetadata, DeletedMetadata],
#	cursor="AAM123...",
#	has_more=True
    if cursor:
        result = dbx.files_list_folder_continue(cursor)
        print("Continue with cursor")

# if 'cursor' is None,"",[],{}, running this 'else:' section
# With 'recursive', we get all subfolders
    else:
        result = dbx.files_list_folder(path="", recursive=True)
        print("Start from root Dropbox")

    synced_files = 0

# 'files_download' return Tuple with two elements (dropbox.files.FileMetadata, requests.models.Responce),
# therefore we need UNPACKING it and creating two
# variables for handling: metadata and res. But in this code metadata not used.
# If by mistake, write "res = dbx...", that creating tuple without unpacking,
# and in next steps must use 'res[1]'
    for entry in result.entries:
        if isinstance(entry, dropbox.files.FileMetadata):
            print(f"Downloaded from Dropbox: {entry.path_lower}")
            metadata, res = dbx.files_download(entry.path_lower)
            gcs_path = f"dropbox_sync{entry.path_lower}"
            # using method .content from responce lib
            upload_to_gcs(gcs_path, res.content)
            print(f"Uploaded in GCS: {gcs_path}")
            synced_files += 1

    save_cursor(result.cursor)
    print(f"Cursor saved: {result.cursor}")

    return f"Synced {synced_files} files"

# Fetches a secret from Google Secret Manager
def get_secret(secret_id, version_id="latest"):
    name = f"projects/{GCP_PROJECT_ID}/secrets/{secret_id}/versions/{version_id}"
    response = secret_client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8").strip()

# Flask Route
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
# GET: Used by Dropbox to verify the webhook endpoint.
# POST: Receives notifications about file changes.
    if request.method == 'GET':
        # Dropbox verification challenge
        challenge = request.args.get('challenge')
        print("Challenge is OK")
        return Response(challenge, mimetype='text/plain')

    elif request.method == 'POST':
        # Verify the request signature to ensure it's from Dropbox
        signature = request.headers.get('X-Dropbox-Signature')
        dbx_app_secret = get_secret(SECRET_DROPBOX_APP_SECRET).strip()
        print(repr(dbx_app_secret))

        if not hmac.compare_digest(signature,hmac.new(dbx_app_secret.encode(), request.data, hashlib.sha256).hexdigest()):
            expected_sig = hmac.new(dbx_app_secret.encode(), request.data, hashlib.sha256).hexdigest()
            print(f"Expected signature: {expected_sig}")
            print(f"Received signature: {signature}")

            print("Invalid signature. Request ignored.")
            return ('', 403)

        #if 'list_folder' in request.json:
        #    print("Received a change notification")

        sync_dropbox()
        print("Webhook received. A file change was detected")

        return ('', 200)

    return ('', 405)  # Method Not Allowed


if __name__ == "__main__":
    # Cloud Run set PORT as it want. For testing code locally, already will be using 8080
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))