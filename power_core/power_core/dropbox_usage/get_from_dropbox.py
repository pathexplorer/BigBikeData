from gcp_actions.blob_manipulation import upload_to_gcp_bucket, delete_blob
from gcp_actions.firestore_box.json_manipulations import FirestoreMagic
from power_core.workshop.pipeline import run_pipeline_on_gcs
from power_core.project_env.config import (
    GSC_ORIG_FIT_FOLDER,
    DROPBOX_WATCHED_FOLDER,
    GCS_BUCKET_NAME,
    DROPBOX_APP_KEY,
    DROPBOX_APP_SECRET,
    DROPBOX_REFRESH_TOKEN
)
from dropbox.exceptions import AuthError
from dropbox.files import FileMetadata, DeletedMetadata  #add types, instead dropbox.files.FileMetadata, use only Fi.
import dropbox
import hmac
import hashlib
from flask import request, Response
import logging

logger = logging.getLogger(__name__)

bucket_name = "GCS_BUCKET_NAME"


# ------- AUTHORIZATION -----------
def auth_dropbox():
    dbx = dropbox.Dropbox(
        app_key=DROPBOX_APP_KEY,
        app_secret=DROPBOX_APP_SECRET,
        oauth2_refresh_token=DROPBOX_REFRESH_TOKEN
    )
    logger.debug("Dropbox-client is created, checking authorization...")
    try:
        dbx.users_get_current_account()
        logger.debug("Dropbox authorization is successful")
        return dbx
    except AuthError as e:
        logger.error(f"Authorization in Dropbox FAILED: {e}")
        raise


class DropBoxCursor:

    def __init__(self, db_cursor_doc: str):
        self.db_cursor_doc = db_cursor_doc
        self.client = FirestoreMagic( "cursors", self.db_cursor_doc)

    """
    :param db_cursor_doc: name of document
    """

    def load_cursor(self):
        """
        Loads cursor from Firestore.
        :return: value from dict "cursor"
        """

        dict_cursor = self.client.load_firejson()
        value_cursor = dict_cursor["cursor"]
        logger.debug(f"Cursor at {len(value_cursor)} symbols from Firestore loaded: {value_cursor[:15]}")
        return value_cursor

    def save_cursor(self, cursor):
        """
        Saves the new cursor to Firestore.
        """
        if cursor:
            logger.debug(f"Saving new {len(cursor)} symbols cursor: {cursor[:15]}...")
            data = {"cursor": cursor}
            self.client.set_firejson(data, True)
        else:
            data = {}
            self.client.set_firejson(data)
            logger.warning(f"Overwrite by empty dict")
            reset = self.load_cursor
            if reset is data:
                logger.warning(f"Successfully emptied dict")


def handle_deletions_in_gcs(deleted_entries):
    """
    Deletes corresponding files from GCS and from Storage Cursor
    """
    # del_js = FirestoreMagic("cursors", "storage_cursor")

    logger.info(f"Deleting {len(deleted_entries)} files from GCS...")
    dropbox_prefix = "/apps/activities/"
    gcs_prefix = GSC_ORIG_FIT_FOLDER
    for entry in deleted_entries:
        # Remove the '/apps' prefix from Dropbox path
        # /apps/activities/file.fit -> /activities/file.fit
        relative_path = entry.path_lower.replace(dropbox_prefix, "", 1)
        gcs_path = f"{gcs_prefix.rstrip('/')}/{relative_path.lstrip('/')}"
        delete_blob(bucket_name, gcs_path)
        # todo as fact, Storage Cursor is immutable. Problem in space in names
        # delete from Storage Cursor
        # logger.debug(f"Records in Storage Cursor before deleting {len(del_js.load_firejson())}")
        # full_gcs_path = f"gs://{GCS_BUCKET_NAME}/{gcs_path}"
        # logger.debug(f"Attempt delete {full_gcs_path} from Storage Cursor...")
        # logger.debug(f"{len(full_gcs_path)}")
        # logger.debug(f"{type(full_gcs_path)}")
        # del_js.delete_field_firejson(full_gcs_path)
        # logger.debug(f"Records in Storage Cursor after deleting {len(del_js.load_firejson())}")


def download_fit_files_from_dropbox(entries, dbx):
    """
    Loading file in GCS. Notice, we need to first load all new files from Dropbox to Storage, and
    then can run a pipeline.
    :param entries:
    :param dbx:
    :return:
    """
    downloaded = []
    for entry in entries:
        if isinstance(entry, FileMetadata):
            logger.debug(f"Downloaded from Dropbox: {entry.path_lower}")
            metadata, res = dbx.files_download(entry.path_lower)
            downloaded.append((entry.path_lower, res.content))
    return downloaded


def upload_fit_files_to_gcs(files):
    copied_files = 0
    dropbox_prefix = "/apps/activities/"
    gcs_prefix = GSC_ORIG_FIT_FOLDER
    for path, content in files:
        # the path is like: /apps/activities/file.fit
        # Remove the '/apps' prefix from a Dropbox path
        # /apps/activities/file.fit -> /activities/file.fit
        relative_path = path.replace(dropbox_prefix, "", 1)
        gcs_path = f"{gcs_prefix.rstrip('/')}/{relative_path.lstrip('/')}"
        upload_to_gcp_bucket(bucket_name, gcs_path, content, "string_path")
        copied_files += 1
    return copied_files


def check_signature():
    signature = request.headers.get('X-Dropbox-Signature')
    dbx_app_secret = DROPBOX_APP_SECRET

    if not hmac.compare_digest(signature, hmac.new(dbx_app_secret.encode(), request.data, hashlib.sha256).hexdigest()):
        expected_sig = hmac.new(dbx_app_secret.encode(), request.data, hashlib.sha256).hexdigest()
        logger.error(f"Expected signature: {expected_sig}")
        logger.error(f"Received signature: {signature}")
        logger.error("Invalid signature. Request ignored.")
        return Response("Forbidden", status=403)
    logger.debug(f"Request: {request.json}")
    return True


def connect_to_dropbox():
    """
    Connects to Dropbox and syncs file changes (.fit files) to GCS.
    Handles both initial sync and delta syncs using a cursor.
    """
    # Init predefined Firestore client
    dbc = DropBoxCursor("db_cursor")

    logger.info("MAIN PIPELINE STARTS")
    dbx = auth_dropbox()
    cursor = dbc.load_cursor()
    folder_path = DROPBOX_WATCHED_FOLDER
    all_entries = []

    try:
        # 1. GET ALL CHANGES (either delta or initial)
        if cursor:
            # DELTA SYNC: We have a cursor, get changes since then
            logger.debug(f"Continuing sync with cursor: {cursor[:15]}...")
            result = dbx.files_list_folder_continue(cursor)
            all_entries.extend(result.entries)

            # Added pagination loop for delta sync
            while result.has_more:
                logger.info("Fetching more changes...")
                result = dbx.files_list_folder_continue(result.cursor)
                all_entries.extend(result.entries)

            # The new cursor is from the last page of changes
            new_cursor = result.cursor

        else:
            # INITIAL SYNC: No cursor, list all files
            logger.info(f"No cursor found. Starting initial sync of: {folder_path}...")
            result = dbx.files_list_folder(path=folder_path, recursive=True)
            all_entries.extend(result.entries)

            # Pagination loop for an initial list
            while result.has_more:
                logger.info("Folder is large. Fetching more files...")
                result = dbx.files_list_folder_continue(result.cursor)
                all_entries.extend(result.entries)

            # Get the *correct* cursor for future changes
            logger.info("Getting latest cursor for future changes...")
            latest_cursor_result = dbx.files_list_folder_get_latest_cursor(
                path=folder_path,
                recursive=True,
                include_deleted=True
            )
            new_cursor = latest_cursor_result.cursor

    except dropbox.exceptions.ApiError as e:
        if e.error.is_path() and e.error.get_path().is_not_found():
            logger.error(f"Error: Path '{folder_path}' not found. Check capitalization.")
        elif e.error.is_path_reset():
            logger.warning("Cursor is invalid (folder moved/renamed?). Restarting with full sync.")
            dbc.save_cursor(None)  # Clear a bad cursor
            # re-run or alert here
        else:
            logger.error(f"Error: {e}")
        return False

    # 2. PROCESS ALL GATHERED ENTRIES
    if not all_entries:
        logger.info("No new changes found.")
        # We still save the new cursor to mark the "check" as complete
        if 'new_cursor' in locals():
            dbc.save_cursor(new_cursor)
        return True  # Not an error, just no work

    logger.info(f"--- Processing {len(all_entries)} total entries ---")

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
        logger.info(f"Found {len(deleted_entries)} deleted .fit files. Removing from GCS...")
        handle_deletions_in_gcs(deleted_entries)
        processed_files = True

    if fit_entries:
        logger.debug(f"Found {len(fit_entries)} new/modified .fit files. Syncing to GCS...")
        files = download_fit_files_from_dropbox(fit_entries, dbx)

        # Don't pass cursor to GCS function
        copied_files = upload_fit_files_to_gcs(files)
        logger.debug(f"Copied {copied_files} .fit files to GCS")

        # Only run a pipeline if new files were actually copied
        if copied_files > 0:
            run_pipeline_on_gcs(
                GCS_BUCKET_NAME,
                # THIS FOLDER CHANGE AT GCS_CLEAN_FOLDER
                GSC_ORIG_FIT_FOLDER)
        processed_files = True

    if not processed_files:
        logger.warning("No relevant .fit file changes found.")

    dbc.save_cursor(new_cursor)
    logger.debug(f"Sync complete. New cursor saved: {new_cursor[:15]}...")
    return True


if __name__ == "__main__":
    connect_to_dropbox()
