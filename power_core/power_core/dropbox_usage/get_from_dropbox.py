"""Dropbox sync entry point: list watched-folder changes and publish pointers to new FIT files to Pub/Sub."""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from gcp_actions.firestore_box.json_manipulations import FirestoreMagic
from gcp_actions.common_utils.timer import run_timer
from gcp_actions.pubsub import publish_to_pubsub
from power_core.project_env.config import (
    GCP_PROJECT_ID,
    DROPBOX_TOPIC_NAME,
    DROPBOX_WATCHED_FOLDER
)
from power_core.dropbox_usage.utils import DropboxAuth
from power_core.dropbox_usage.egress_transport import diagnose_egress
from dropbox.files import FileMetadata
import dropbox



logger = logging.getLogger(__name__)

# Marker lifecycle: fresh `published`/`failed` markers suppress immediate
# republish (async pipeline may still be working); stale ones are retried,
# which is the at-least-once guarantee. `completed` is terminal until TTL.
# `dead` is terminal after too many attempts and needs a human look.
RETRY_AFTER_HOURS = 1
MARKER_TTL_DAYS = 7
MAX_ATTEMPTS = 5

class DropBoxCursor:
    """Persists the Dropbox sync cursor in Firestore so incremental listing continues where it left off."""

    def __init__(self, db_cursor_doc: str):
        """Point the cursor store at the Firestore document identified by db_cursor_doc."""
        self.db_cursor_doc = db_cursor_doc
        self.client = FirestoreMagic("cursors", self.db_cursor_doc)

    @run_timer
    def load_cursor(self):
        """Return the stored Dropbox cursor, or None on the first run."""
        dict_cursor = self.client.load_firejson()
        return dict_cursor.get("cursor")

    @run_timer
    def save_cursor(self, cursor):
        """Persist the given cursor, or clear the document when it is empty."""
        if cursor:
            self.client.set_firejson({"cursor": cursor}, True)
        else:
            self.client.set_firejson({}, False)
            logger.warning("Overwrite by empty dict")

class DropboxFileMarkers:
    """Per-file publish markers in Firestore so retries neither lose nor duplicate files."""

    COLLECTION = "dropbox_files"

    def _record(self, file_key, status, upload_id, now, extra=None):
        """Build a marker document with TTL expiry."""
        record = {
            "status": status,
            "upload_id": upload_id,
            "updated_at": now.isoformat(),
            "expires_at": (now + timedelta(days=MARKER_TTL_DAYS)).isoformat(),
        }
        if extra:
            record.update(extra)
        return record

    def get(self, file_key):
        """Return the marker record, or {} when the file was never seen."""
        return FirestoreMagic(self.COLLECTION, file_key, {}).load_firejson() or {}

    def mark_published(self, file_key, upload_id, now,
                       dropbox_path=None, original_filename=None):
        """Record a successful pointer publish, counting the attempt."""
        current = self.get(file_key) or {}
        extra = {"attempts": current.get("attempts", 0) + 1}
        if dropbox_path is not None:
            extra["dropbox_path"] = dropbox_path
        if original_filename is not None:
            extra["original_filename"] = original_filename
        FirestoreMagic(self.COLLECTION, file_key).set_firejson(
            self._record(file_key, "published", upload_id, now, extra), False
        )

    def mark_final(self, file_key, status, upload_id=""):
        """Record a terminal pipeline outcome (completed/failed/dead)."""
        FirestoreMagic(self.COLLECTION, file_key).set_firejson(
            self._record(file_key, status, upload_id, datetime.now(timezone.utc)), True
        )

    def list_stale(self, now):
        """Return markers eligible for retry: stale published/failed with a path."""
        from gcp_actions.client import get_any_client
        stale = []
        docs = get_any_client("firestore").collection(self.COLLECTION).stream()
        for doc in docs:
            data = doc.to_dict() or {}
            if data.get("status") not in ("published", "failed"):
                continue
            if not data.get("dropbox_path"):
                continue
            if data.get("attempts", 0) > MAX_ATTEMPTS:
                continue
            try:
                updated = datetime.fromisoformat(data.get("updated_at", ""))
            except ValueError:
                updated = None
            if updated is None or (now - updated) >= timedelta(hours=RETRY_AFTER_HOURS):
                stale.append({"file_key": doc.id, **data})
        return stale


def stable_file_id(entry):
    """Derive a stable file identity survivors across republishes."""
    if getattr(entry, "id", None) and getattr(entry, "rev", None):
        return f"{entry.id}:{entry.rev}"
    logger.warning(f"No Dropbox id/rev for {entry.name}; falling back to random id.")
    return str(uuid.uuid4())


def file_needs_publish(record, now):
    """Decide from a marker record whether a listed file needs a (re)publish."""
    if not record or not record.get("status"):
        return True
    if record.get("status") in ("completed", "dead"):
        return False
    if record.get("attempts", 0) > MAX_ATTEMPTS:
        return False
    try:
        updated = datetime.fromisoformat(record.get("updated_at", ""))
    except ValueError:
        return True
    return (now - updated) >= timedelta(hours=RETRY_AFTER_HOURS)


@run_timer
def connect_to_dropbox(dbx=None, cursor_store=None, marker_store=None, topic=None):
    """Incrementally list the watched Dropbox folder and publish each new FIT file to Pub/Sub."""
    cursor_store = cursor_store or DropBoxCursor("db_cursor")
    marker_store = marker_store or DropboxFileMarkers()
    topic = topic or DROPBOX_TOPIC_NAME
    logger.info("Dropbox sync service started.")
    if dbx is None:
        da = DropboxAuth()
        try:
            dbx = da.auth_dropbox()
        except Exception:
            diagnose_egress("api.dropboxapi.com")
            raise
    cursor = cursor_store.load_cursor()
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

    now = datetime.now(timezone.utc)
    publish_failures = 0
    if not all_entries:
        logger.info("No new changes found.")
    else:
        logger.info(f"--- Processing {len(all_entries)} total entries ---")
    fit_entries = [e for e in all_entries if isinstance(e, FileMetadata) and e.name.endswith(".fit")]
    if fit_entries:
        logger.info(f"Found {len(fit_entries)} new/modified .fit files. Publishing pointers to Pub/Sub...")
        for entry in fit_entries:
            file_key = stable_file_id(entry)
            record = marker_store.get(file_key)
            if record.get("attempts", 0) > MAX_ATTEMPTS and record.get("status") != "dead":
                marker_store.mark_final(file_key, "dead", record.get("upload_id", ""))
                logger.warning(f"Giving up on {entry.name} after repeated failures.")
                continue
            if not file_needs_publish(record, now):
                logger.info(f"Skipping already accounted {entry.name}.")
                continue
            upload_id = file_key
            message_payload = {
                'dropbox_path': entry.path_lower,
                'original_filename': entry.name,
                'upload_id': upload_id,
                'file_key': file_key,
            }
            try:
                publish_to_pubsub(topic, message_payload)
                logger.info(f"Published pointer for {entry.name} to {topic}.")
            except Exception as e:
                publish_failures += 1
                logger.error(f"Failed to publish pointer for {entry.name}: {e}")
                continue
            try:
                marker_store.mark_published(
                    file_key, upload_id, now,
                    dropbox_path=entry.path_lower,
                    original_filename=entry.name,
                )
            except Exception as e:
                publish_failures += 1
                logger.error(f"Pointer published but marker failed for {entry.name}: {e}")
    for stale in marker_store.list_stale(now):
        stale_payload = {
            'dropbox_path': stale["dropbox_path"],
            'original_filename': stale.get("original_filename", "unknown.fit"),
            'upload_id': stale.get("upload_id") or stale["file_key"],
            'file_key': stale["file_key"],
        }
        try:
            publish_to_pubsub(topic, stale_payload)
            marker_store.mark_published(
                stale["file_key"], stale_payload["upload_id"], now,
                dropbox_path=stale["dropbox_path"],
                original_filename=stale.get("original_filename"),
            )
            logger.info(f"Republished stale pointer for {stale['file_key']}.")
        except Exception as e:
            publish_failures += 1
            logger.error(f"Failed to republish pointer for {stale['file_key']}: {e}")
    if publish_failures:
        logger.error(f"{publish_failures} pointer(s) failed; keeping old cursor for retry.")
        return False
    cursor_store.save_cursor(new_cursor)
    logger.debug("Sync complete. New cursor saved.")
    return True

if __name__ == "__main__":
    connect_to_dropbox()
