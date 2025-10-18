from gcs.google_secret_manager import get_secret
from project_env import config
import json
import dropbox
from dropbox.exceptions import AuthError #not necessary, but hide fake error warning
from dropbox.files import FileMetadata #add types, instead dropbox.files.FileMetadata, use only Fi.
from workshop.pipeline import run_pipeline_on_gcs
from gcs.client import get_bucket

bucket = get_bucket()


# ------- AUTHORIZATION -----------
def auth_dropbox():
    dbx_app_secret = get_secret(config.SECRET_DROPBOX_APP_SECRET)
    dbx_app_key = get_secret(config.DROPBOX_APP_KEY)
    dbx_refresh_token = get_secret(config.SECRET_DROPBOX_REFRESH_TOKEN)
    dbx = dropbox.Dropbox(
        app_key=dbx_app_key,
        app_secret=dbx_app_secret,
        oauth2_refresh_token=dbx_refresh_token
    )
    print("Dropbox-client is created, checking authorization...")
    try:
        dbx.users_get_current_account()
        print("Authorization in Dropbox successful")
        return dbx
    except AuthError as e:
        print("Authorization in Dropbox FAILED", e)
        raise

# ---- Cursor for Dropbox ----
def load_cursor():
# 'loads' convert JSON into Dict, then reads key 'cursor'
# use '.get' instead 'loads(content)["cursor"]' because
# - if cursor doesn't exist, code is stops (KeyError)
# - must use try\except, instead simple check
# - in situation, where doesn't existing cursor is normal
    blob = bucket.blob(config.CURSOR_BLOB)
    if blob.exists():
        content = blob.download_as_text()
        return json.loads(content).get("cursor")
    else:
        print("Cursor doesn't exist. Creating...")
        return None

def save_cursor(cursor):
    blob = bucket.blob(config.CURSOR_BLOB)
    data = json.dumps({"cursor": cursor})
    blob.upload_from_string(data, content_type="application/json")

# ---- Loading file in GCS ----
def download_fit_files_from_dropbox(entries, dbx):
    downloaded = []
    for entry in entries:
        if isinstance(entry, FileMetadata):
            print(f"Downloaded from Dropbox: {entry.path_lower}")
            metadata, res = dbx.files_download(entry.path_lower)
            downloaded.append((entry.path_lower, res.content))
    return downloaded

def upload_to_gcs(path, content):
# storage.Client().bucket(GCS_BUCKET_NAME).blob(path).upload_from_string(content)
    blob = bucket.blob(path)
    blob.upload_from_string(content)
    print(f"File {path} loaded")

def upload_fit_files_to_gcs(files, cursor):
    copied_files = 0
    for path, content in files:
        gcs_path = f"{config.GCS_CLOUD_PROJECT}{path}"
        upload_to_gcs(gcs_path, content)
        print(f"Uploaded in GCS: {gcs_path}")
        copied_files += 1
    save_cursor(cursor)
    print(f"Cursor Dropbox saved: {cursor}")
    return copied_files

def connect_to_dropbox():
    """
    Start stages of pipeline
    'result' returns next data
        ListFolderResult(
        entries=[FileMetadata, FolderMetadata, DeletedMetadata],
        cursor="AAM123...",
        has_more=True
    """
    print("Sync Dropbox → GCS starts")
    dbx = auth_dropbox()
    cursor = load_cursor()
    print(f"Cursor: {cursor}")

    # Get lisf of changes
    if cursor:
        result = dbx.files_list_folder_continue(cursor)
        print("Continue with cursor")
    else:
        result = dbx.files_list_folder(path=config.DROPBOX_WATCHED_FOLDER, recursive=True)
        print("Start from empty file")

    # Filtering only .fit files from certain folder
    fit_entries = [
        entry for entry in result.entries
        if isinstance(entry, FileMetadata)
           and entry.path_lower.startswith("/apps/wahoofitness/")
           and entry.name.endswith(".fit")
    ]
    if fit_entries:
        files = download_fit_files_from_dropbox(fit_entries, dbx)
        copied_files = upload_fit_files_to_gcs(files, result.cursor)
        print(f"Copied {copied_files} .fit files to GCS")
        run_pipeline_on_gcs(
            config.GCS_BUCKET_NAME,
            config.GSC_ORIG_FIT_FOLDER,
            config.MAINFEST_GSC_PATH
        )
    else:
        print(f"No .fit files found in {config.DROPBOX_WATCHED_FOLDER}")