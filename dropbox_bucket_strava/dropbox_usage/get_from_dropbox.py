from project_env import config
from gcp_actions.secret_manager import SecretManagerClient
from gcp_actions.client import get_bucket
from gcp_actions.blob_manipulation import upload_to_gcp_bucket, delete_blob
from workshop.pipeline import run_pipeline_on_gcs
import json
import dropbox
from dropbox.exceptions import AuthError #not necessary, but hide fake error warning
from dropbox.files import FileMetadata, DeletedMetadata #add types, instead dropbox.files.FileMetadata, use only Fi.
import hmac
import hashlib
from flask import request, Response

bucket = get_bucket()

sm = SecretManagerClient(config.GCP_PROJECT_ID,config.s_email_dropbox)
secrets_db_dict = sm.get_secret_json(config.SEC_DROPBOX)
path_cursor_blob = config.CURSOR_BLOB

# ------- AUTHORIZATION -----------
def auth_dropbox():
    dbx_app_key = secrets_db_dict.get("DROPBOX_APP_KEY")
    dbx_app_secret = secrets_db_dict.get("DROPBOX_APP_SECRET")
    dbx_refresh_token = secrets_db_dict.get("DROPBOX_REFRESH_TOKEN")
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
    blob = bucket.blob(path_cursor_blob)
    if blob.exists():
        content = blob.download_as_text()
        return json.loads(content).get("cursor")
    else:
        print("Cursor doesn't exist. Creating...")
        return None

def save_cursor(cursor):
    """
    Saves the new cursor to GCS.
    'cursor' can be a string or None (to reset).
    """
    if cursor:
        print(f"Saving new cursor: {cursor[:15]}...")
        data = {"cursor": cursor}
        upload_to_gcp_bucket(path_cursor_blob, data, "string")
    else:
        # Called when sync fails and needs a full reset
        print("Resetting cursor to None.")
        delete_blob(path_cursor_blob)

def handle_deletions_in_gcs(deleted_entries):
    """
    Deletes corresponding files from GCS.
    """
    print(f"Deleting {len(deleted_entries)} files from GCS...")
    dropbox_prefix = "/apps/activities/"
    gcs_prefix = config.GSC_ORIG_FIT_FOLDER
    for entry in deleted_entries:
        # Remove the '/apps' prefix from Dropbox path
        # /apps/activities/file.fit -> /activities/file.fit
        relative_path = entry.path_lower.replace(dropbox_prefix, "", 1)
        gcs_path = f"{gcs_prefix.rstrip('/')}/{relative_path.lstrip('/')}"
        delete_blob(gcs_path)

# ---- Loading file in GCS ----
def download_fit_files_from_dropbox(entries, dbx):
    downloaded = []
    for entry in entries:
        if isinstance(entry, FileMetadata):
            print(f"Downloaded from Dropbox: {entry.path_lower}")
            metadata, res = dbx.files_download(entry.path_lower)
            downloaded.append((entry.path_lower, res.content))
    return downloaded

def upload_fit_files_to_gcs(files):
    copied_files = 0
    dropbox_prefix = "/apps/activities/"
    gcs_prefix = config.GSC_ORIG_FIT_FOLDER
    for path, content in files:
        # path is like: /apps/activities/file.fit
        # Remove the '/apps' prefix from Dropbox path
        # /apps/activities/file.fit -> /activities/file.fit
        relative_path = path.replace(dropbox_prefix, "", 1)
        gcs_path = f"{gcs_prefix.rstrip('/')}/{relative_path.lstrip('/')}"
        upload_to_gcp_bucket(gcs_path, content, "string_path")
        copied_files += 1
    return copied_files

def check_signature():
    signature = request.headers.get('X-Dropbox-Signature')
    dbx_app_secret = secrets_db_dict.get("DROPBOX_APP_SECRET")

    if not hmac.compare_digest(signature, hmac.new(dbx_app_secret.encode(), request.data, hashlib.sha256).hexdigest()):
        expected_sig = hmac.new(dbx_app_secret.encode(), request.data, hashlib.sha256).hexdigest()
        print(f"Expected signature: {expected_sig}")
        print(f"Received signature: {signature}")
        print("Invalid signature. Request ignored.")
        return Response("Forbidden", status=403)
    print("Request:", request.json)
    success = connect_to_dropbox()
    if success:
        return Response("Pipeline started", status=200)
    else:
        return Response("No files found. Nothing to process.", status=204)

def connect_to_dropbox():
    """
    Connects to Dropbox and syncs file changes (.fit files) to GCS.
    Handles both initial sync and delta syncs using a cursor.
    """
    print("Sync Dropbox → GCS starts")
    dbx = auth_dropbox()
    cursor = load_cursor()
    folder_path = config.DROPBOX_WATCHED_FOLDER
    all_entries = []

    try:
        # 1. GET ALL CHANGES (either delta or initial)
        if cursor:
            # DELTA SYNC: We have a cursor, get changes since then
            print(f"Continuing sync with cursor: {cursor[:15]}...")
            result = dbx.files_list_folder_continue(cursor)
            all_entries.extend(result.entries)

            # Added pagination loop for delta sync
            while result.has_more:
                print("Fetching more changes...")
                result = dbx.files_list_folder_continue(result.cursor)
                all_entries.extend(result.entries)

            # The new cursor is from the last page of changes
            new_cursor = result.cursor

        else:
            # INITIAL SYNC: No cursor, list all files
            print(f"No cursor found. Starting initial sync of: {folder_path}...")
            result = dbx.files_list_folder(path=folder_path, recursive=True)
            all_entries.extend(result.entries)

            # Pagination loop for initial list
            while result.has_more:
                print("Folder is large. Fetching more files...")
                result = dbx.files_list_folder_continue(result.cursor)
                all_entries.extend(result.entries)

            # Get the *correct* cursor for future changes
            print("Getting latest cursor for future changes...")
            latest_cursor_result = dbx.files_list_folder_get_latest_cursor(
                path=folder_path,
                recursive=True,
                include_deleted=True
            )
            new_cursor = latest_cursor_result.cursor

    except dropbox.exceptions.ApiError as e:
        if e.error.is_path() and e.error.get_path().is_not_found():
            print(f"Error: Path '{folder_path}' not found. Check capitalization.")
        elif e.error.is_path_reset():
            print("Cursor is invalid (folder moved/renamed?). Restarting with full sync.")
            save_cursor(None)  # Clear bad cursor
            # re-run or alert here
        else:
            print(f"Error: {e}")
        return False

    # 2. PROCESS ALL GATHERED ENTRIES
    if not all_entries:
        print("No new changes found.")
        # We still save the new cursor to mark the "check" as complete
        if 'new_cursor' in locals():
            save_cursor(new_cursor)
        return True  # Not an error, just no work

    print(f"\n--- Processing {len(all_entries)} total entries ---")

    # <-- FIX: Handle both new/modified files and deletions
    fit_entries = [
        entry for entry in all_entries
        if isinstance(entry, FileMetadata)
           and entry.path_lower.startswith("/apps/activities")  # Your filter
           and entry.name.endswith(".fit")
    ]

    deleted_entries = [
        entry for entry in all_entries
        if isinstance(entry, DeletedMetadata)
           and entry.path_lower.startswith("/apps/activities")  # Your filter
           and entry.name.endswith(".fit")
    ]

    # 3. EXECUTE ACTIONS
    processed_files = False

    if deleted_entries:
        print(f"Found {len(deleted_entries)} deleted .fit files. Removing from GCS...")
        handle_deletions_in_gcs(deleted_entries)
        processed_files = True

    if fit_entries:
        print(f"Found {len(fit_entries)} new/modified .fit files. Syncing to GCS...")
        files = download_fit_files_from_dropbox(fit_entries, dbx)

        # Don't pass cursor to GCS function
        copied_files = upload_fit_files_to_gcs(files)
        print(f"Copied {copied_files} .fit files to GCS")

        # Only run pipeline if new files were actually copied
        if copied_files > 0:
            run_pipeline_on_gcs(
                config.GCS_BUCKET_NAME,
                config.GSC_ORIG_FIT_FOLDER,
                config.MAINFEST_GSC_PATH
            )
        processed_files = True

    if not processed_files:
        print("No relevant .fit file changes found.")

    save_cursor(new_cursor)
    print(f"Sync complete. New cursor saved: {new_cursor[:15]}...")
    return True

if __name__ == "__main__":
    connect_to_dropbox()