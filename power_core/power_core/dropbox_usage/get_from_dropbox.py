import logging
import uuid
from gcp_actions.firestore_box.json_manipulations import FirestoreMagic
from gcp_actions.common_utils.timer import run_timer
from gcp_actions.pubsub import publish_to_pubsub
from power_core.project_env.config import (
    GCP_PROJECT_ID,
    DROPBOX_TOPIC_NAME,
    DROPBOX_WATCHED_FOLDER
)
from power_core.dropbox_usage.utils import DropboxAuth
from dropbox.files import FileMetadata
import dropbox



logger = logging.getLogger(__name__)

class DropBoxCursor:
    def __init__(self, db_cursor_doc: str):
        self.db_cursor_doc = db_cursor_doc
        self.client = FirestoreMagic("cursors", self.db_cursor_doc)

    @run_timer
    def load_cursor(self):
        dict_cursor = self.client.load_firejson()
        return dict_cursor.get("cursor")

    @run_timer
    def save_cursor(self, cursor):
        if cursor:
            self.client.set_firejson({"cursor": cursor}, True)
        else:
            self.client.set_firejson({})
            logger.warning("Overwrite by empty dict")

@run_timer
def connect_to_dropbox():

    dbc = DropBoxCursor("db_cursor")
    logger.info("Dropbox sync service started.")
    da = DropboxAuth()
    dbx = da.auth_dropbox()
    cursor = dbc.load_cursor()
    folder_path = DROPBOX_WATCHED_FOLDER
    all_entries = []
    try:
        if cursor:
            result = dbx.files_list_folder_continue(cursor)
        else:
            result = dbx.files_list_folder(path=folder_path, recursive=True, include_deleted=True)
        all_entries.extend(result.entries)
        while result.has_more:
            result = dbx.files_list_folder_continue(result.cursor)
            all_entries.extend(result.entries)
        new_cursor = result.cursor
    except dropbox.exceptions.ApiError as e:
        logger.error(f"Dropbox API Error: {e}")
        return False

    if not all_entries:
        logger.info("No new changes found.")
        if 'new_cursor' in locals():
            dbc.save_cursor(new_cursor)
        return True

    logger.info(f"--- Processing {len(all_entries)} total entries ---")
    fit_entries = [e for e in all_entries if isinstance(e, FileMetadata) and e.name.endswith(".fit")]
    if fit_entries:
        logger.info(f"Found {len(fit_entries)} new/modified .fit files. Publishing pointers to Pub/Sub...")
        for entry in fit_entries:
            upload_id = str(uuid.uuid4())
            message_payload = {
                'dropbox_path': entry.path_lower,
                'original_filename': entry.name,
                'upload_id': upload_id
            }
            try:
                publish_to_pubsub(DROPBOX_TOPIC_NAME, message_payload)
                logger.info(f"Published pointer for {entry.name} to {DROPBOX_TOPIC_NAME}.")
            except Exception as e:
                logger.error(f"Failed to publish pointer for {entry.name}: {e}")
    dbc.save_cursor(new_cursor)
    logger.debug("Sync complete. New cursor saved.")
    return True

if __name__ == "__main__":
    connect_to_dropbox()
