import dropbox
import io
import logging
import os
from project_env import config
from gcp_actions.client import get_bucket
from dropbox.files import FileMetadata #add types, instead dropbox.files.FileMetadata, use only Fi.
from dropbox_usage.get_from_dropbox import auth_dropbox
from flask import jsonify

bucket = get_bucket()

def upload_custom_files_session(gcs_folder: str):
    """
    curl -X POST https://{LINK}.app/upload_custom_files_session \
  -H "Content-Type: application/json" \
  -d '{"gcs_folder": "heatmap/"}'
    """
    blobs = list(bucket.list_blobs(prefix=gcs_folder))
    if not blobs:
        return jsonify({"error": "No files found in folder"}), 404
    dbx = auth_dropbox()
    uploaded = []

    for blob in blobs:
        if blob.name.endswith("/"):  # skip "folders"
            continue
        try:
            # Stream blob content in chunks
            data = blob.download_as_bytes() #dont use blob.open("rb")
            if not data:
                logging.warning(f"Blob is empty: {blob.name}")
                continue
            stream = io.BytesIO(data)
            first_chunk = stream.read(config.CHUNK_SIZE)
            if not first_chunk:
                logging.warning(f"First chunk empty: {blob.name}")
                continue

            session_start = dbx.files_upload_session_start(first_chunk)
            cursor = dropbox.files.UploadSessionCursor(session_id=session_start.session_id, offset=stream.tell())
            dropbox_path = f"/heatmap/{os.path.basename(blob.name)}"
            commit = dropbox.files.CommitInfo(path=dropbox_path, mode=dropbox.files.WriteMode.overwrite)

            while True:
                chunk = stream.read(config.CHUNK_SIZE)
                if not chunk:
                    dbx.files_upload_session_finish(b"", cursor, commit)
                    print("Break reached")
                    break
                if len(chunk) < config.CHUNK_SIZE:
                    dbx.files_upload_session_finish(chunk, cursor, commit)
                    print(f"Committed {len(chunk)} bytes")
                    break
                else:
                    dbx.files_upload_session_append_v2(chunk, cursor)
                    cursor.offset += len(chunk)
                    print(f"Else committed {len(chunk)} bytes")
            logging.info(f"Uploaded to Dropbox: {dropbox_path}")
            uploaded.append(dropbox_path)
            print("Results:", uploaded)
        except Exception as e:
            logging.error(f"Upload failed: {e}")
    return jsonify({"status": "completed", "uploaded_files": uploaded}), 200