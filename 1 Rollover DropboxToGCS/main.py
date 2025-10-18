from project_env import config
import os
import hmac
import hashlib
import dropbox
import io
import logging
from dropbox.files import FileMetadata #add types, instead dropbox.files.FileMetadata, use only Fi.
from flask import Flask, request, Response, jsonify
from gcs.google_secret_manager import get_secret
from dropbox_usage.get_from_dropbox import connect_to_dropbox,auth_dropbox
from gcs.client import get_bucket

# TODO it is testing feature or it neet ON permanently? Or simple disable message?
#checking_env()  # Formal test for existing secrets temporary OFF

# ---- Initialize Clients ----
app = Flask(__name__)
bucket = get_bucket()



# ----- Flask Routes ------
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
        dbx_app_secret = get_secret(config.SECRET_DROPBOX_APP_SECRET)
        #print(repr(dbx_app_secret))

        if not hmac.compare_digest(signature,hmac.new(dbx_app_secret.encode(), request.data, hashlib.sha256).hexdigest()):
            expected_sig = hmac.new(dbx_app_secret.encode(), request.data, hashlib.sha256).hexdigest()
            print(f"Expected signature: {expected_sig}")
            print(f"Received signature: {signature}")
            print("Invalid signature. Request ignored.")
            return '', 403

        #if 'list_folder' in request.json:
        #    print("Received a change notification")
        print("Request:",request.json)
        connect_to_dropbox()
        print("Webhook received. A file change was detected")

        return '', 200
    return '', 405  # Method Not Allowed

@app.route("/upload_to_dropbox_session", methods=["POST"])
def upload_to_dropbox_session():
    gcs_folder = request.json.get("gcs_folder")
    print(f"gcs_path={gcs_folder}") #DELETE
    if not gcs_folder:
        return jsonify({"error": "Missing gcs_folder"}), 400
    if not gcs_folder.endswith("/"):
        gcs_folder += "/"
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
    # Cloud Run set PORT as it want. For testing code locally, already will be using 8080
    # guinocorn ignores this row
#if __name__ == "__main__":
#    app.run(debug=False, use_reloader=False, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
