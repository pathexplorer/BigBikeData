import config
import os
import hmac
import hashlib
import json
import dropbox
import gpxpy
import fitdecode
import pandas
import numpy
import lxml
import re
import io
import logging
import subprocess
import warnings
from fit2gpx import Converter
from dropbox.exceptions import AuthError #not necessary, but hide fake error warning
from dropbox.files import FileMetadata #add types, instead dropbox.files.FileMetadata, use only Fi.
from flask import Flask, request, Response, jsonify
from google.cloud import storage, secretmanager
from google.cloud.exceptions import NotFound
from checking_env import checking_env
from strava.auth import update_strava_token_if_needed
from strava.upload import upload_fit_to_strava, poll_upload_status, update_gear
from heatmap_gpx.append_function import append_gpx_via_compose
from datetime import datetime, timezone

# TODO it is testing feature or it neet ON permanently? Or simple disable message?
#checking_env()  # Formal test for existing secrets temporary OFF

# ---- Initialize Clients ----
app = Flask(__name__)
client = storage.Client()
bucket = client.bucket(config.GCS_BUCKET_NAME)
secret_client = secretmanager.SecretManagerServiceClient()
conv = Converter()
warnings.filterwarnings("ignore", category=UserWarning) # for ignore warn from fit 2 gpx

# ------- AUTHORIZATION -----------
# Fetches a secret from Google Secret Manager
def get_secret(secret_id, version_id="latest"):
    name = f"projects/{config.GCP_PROJECT_ID}/secrets/{secret_id}/versions/{version_id}"
    response = secret_client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8").strip()

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
def upload_to_gcs(path, content):
# storage.Client().bucket(GCS_BUCKET_NAME).blob(path).upload_from_string(content)
    blob = bucket.blob(path)
    blob.upload_from_string(content)
    print(f"File {path} loaded")

def download_fit_files_from_dropbox(entries, dbx):
    downloaded = []
    for entry in entries:
        if isinstance(entry, FileMetadata):
            print(f"Downloaded from Dropbox: {entry.path_lower}")
            metadata, res = dbx.files_download(entry.path_lower)
            downloaded.append((entry.path_lower, res.content))
    return downloaded

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

def run_pipeline_on_gcs(bucket_name: str, path_prefix, manifest_blob_path):
    """
    Start Second stage of pipeline
    """
    # 1. Get all files in folder in GCS
    all_files = list_gcs_files(bucket_name, path_prefix)
    # 2. Load mainfest of processing files
    processed_files = load_processed_manifest(manifest_blob_path)
    for blob_path in all_files:
        if blob_path not in processed_files:
            print(f"Now Processing {blob_path}")
            union_pipeline(blob_path)
            mark_as_processed(manifest_blob_path, blob_path)

def list_gcs_files(bucket_name, prefix):
    blobs = bucket.list_blobs(prefix=prefix)
    return [f'gs://{bucket_name}/{blob.name}' for blob in blobs]

def load_processed_manifest(manifest_blob_path):
    blob = bucket.blob(manifest_blob_path)
    try:
        return json.loads(blob.download_as_text())
    except NotFound:
        blob.upload_from_string("{}", content_type="application/json")
        return {}

def mark_as_processed(manifest_blob_path, file_path1):
    manifest = load_processed_manifest(manifest_blob_path)
    manifest[file_path1] = datetime.now(timezone.utc).isoformat()  #python 3.10 dependency instead .utcnow()
    blob = bucket.blob(manifest_blob_path)
    blob.upload_from_string(json.dumps(manifest), content_type='application/json')

def union_pipeline(blob_path):
    # extracting some data from original .FIT for Data Labeling
    # For ony files from Wahoo Roam, which name in format: 'YYYY-MM-DD-HHMMSS-elemnt... .fit'
    # timestamp_part = filename.split("-elemnt")[0]
    # dt = datetime.strptime(timestamp_part, "%Y-%m-%d-%H%M%S")
    # formatted = dt.strftime("%Y-%m-%d %H:%M:%S") # extracted timestamp of start activity
    # now = datetime.now(timezone.utc)
    # now_str = now.strftime("%Y-%m-%d %H:%M:%S") # current timestamp
# ----- load FIT to VM -----
    filename = os.path.basename(blob_path)
    path = f"{config.GSC_ORIG_FIT_FOLDER}/{filename}" # Exclude gs:// part from path: simple build new path from variables
    local_fit = f"/tmp/{filename}"
    os.makedirs("/tmp", exist_ok=True)
    blob = bucket.blob(path)
    blob.download_to_filename(local_fit)
    print(f".fit downloaded to VM: {blob_path} → {local_fit}")
# ----- FIT >>> Unexplored CSV
    local_csv = f"/tmp/{filename.replace('.fit', '.csv')}"
    convert_fit_to_csv(local_fit, local_csv, mode='decode')
    #csv_gcs_path = f"csv/{os.path.basename(local_csv)}"
    #bucket.blob(csv_gcs_path).upload_from_filename(local_csv)
    #print(f"Uploaded unexplored CSV in bucket:{csv_gcs_path}")
    print("Skipped saving the unexplored CSV in a bucket")
# ----- Clean unexplored CSV from gps problems
    name, ext = os.path.splitext(os.path.basename(local_csv))
    local_csv_fix = f"/tmp/{name}_fixed{ext}"
    bike_model = clean_gps(local_csv, local_csv_fix)
    fit_csv_gcs_path = f"csv_clean/{os.path.basename(local_csv_fix)}"
    bucket.blob(fit_csv_gcs_path).upload_from_filename(local_csv_fix)
    print(f"Fixed:{fit_csv_gcs_path}")
# ----- 3 phase explored CSV >>> FIT
    name1 = os.path.splitext(os.path.basename(local_csv))[0]
    local_fix_fit = f"/tmp/{name1}_ffixed.fit"
    convert_fit_to_csv(local_csv_fix, local_fix_fit, mode='encode')
    fix_fit_gcs_path = f"fit_clean/{os.path.basename(local_fix_fit)}"
    bucket.blob(fix_fit_gcs_path).upload_from_filename(local_fix_fit)
    print(f"Uploaded fixed version in:{fix_fit_gcs_path}")
# ----- 4 phase: Push explored FIT to strava
    current_mode = get_secret("current-mode")
    if current_mode == "prod":
        access_token = update_strava_token_if_needed()
        upload_id = upload_fit_to_strava(access_token, local_fix_fit)
        activity_id = poll_upload_status(upload_id, access_token)
        updated = update_gear(activity_id, access_token, bike_model)
        print(f"Uploaded to Strava: {updated}")
    elif current_mode == "testing":
        print(f"SKIPPED uploading to STRAVA")
# ----- Convert explored FIT to GPX
    local_gpx = f"/tmp/{filename.replace('.fit', '.gpx')}"
    conv.fit_to_gpx(local_fix_fit, local_gpx)
    gpx_gcs_path = f"gpx/{os.path.basename(local_gpx)}"
    bucket.blob(gpx_gcs_path).upload_from_filename(local_gpx)
    print(f"Uploaded GPX in GCS:{gpx_gcs_path}")
# ----- Create heatmap by bike
    append_gpx_via_compose(local_gpx, bike_model, gpx_gcs_path)

def sync_dropbox():
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

def convert_fit_to_csv(input_path, output_path, mode):
    flag = "-b" if mode == "decode" else "-c"
    subprocess.run(["java", "-jar", "FitCSVTool.jar", flag, input_path, output_path], check=True)

def label_bike(lines):
    mtb = ['ant_device_number,"4315"', 'ant_device_number,"33509"']
    gravel = ['ant_device_number,"2230"', 'ant_device_number,"9560"']
    for line in lines:
        if any(code in line for code in mtb):
            return 'b7647614'
        if any(code in line for code in gravel):
            return 'b8850168'
    return 'b0000000'

def clean_gps(input_path, output_path):
    """
    Processing CSV for clean from GPS problems, fix incorrect sensor serial number, getting bike model
    """
    # Finding lat, long and gps_accuracy
    pattern = re.compile(
       r'position_lat,"(-?\d+)",semicircles,position_long,"-?\d+",semicircles,'
    )
    with open(input_path, 'r', encoding='utf-8') as infile:
        lines = infile.readlines()
    bike_model = label_bike(lines)
    cleaned_lines = []
    for line in lines:
        if line.startswith("Data"):
            match = pattern.search(line)
            if match:
                lat_value = int(match.group(1))
                if lat_value < 0:
                    line = line.replace(match.group(0), "")  # Видаляємо фрагмент
            #for records before 01/10/2025
            line = re.sub(r'serial_number,"SN\.(\d+)"', r'serial_number,"\1"', line)
        cleaned_lines.append(line)
    with open(output_path, 'w', encoding='utf-8') as outfile:
        outfile.writelines(cleaned_lines)
    return bike_model

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
        sync_dropbox()
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
