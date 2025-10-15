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
from fit2gpx import Converter
from dropbox.exceptions import AuthError #not necessary, but hide fake error warning
from dropbox.files import FileMetadata #add types, instead dropbox.files.FileMetadata, use only Fi.
from flask import Flask, request, Response, jsonify
import logging
from google.cloud import storage, secretmanager
import subprocess
from checking_env import checking_env
import warnings
from strava.auth import update_strava_token_if_needed
from strava.upload import upload_fit_to_strava, poll_upload_status, update_gear
from heatmap_gpx.append_function import append_gpx_via_compose
#from datetime import datetime, timezone # for Data Labeling

# ---- Configuration ----
# GCP Project ID and Secret Names from Secret Manager
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME")  # Set as environment variable

# Dropbox and GCS configuration
SECRET_DROPBOX_APP_SECRET = "dropbox-app-secret"
SECRET_DROPBOX_REFRESH_TOKEN = "dropbox-refresh-token"
DROPBOX_APP_KEY = "dropbox-app-key"
DROPBOX_WATCHED_FOLDER = "/apps/wahoofitness" # The folder to monitor (case-insensitive)

#load heatmap, app route "upload to dropbox"
DROPBOX_HEATMAP = "heatmap"
GSC_HEATMAP_PATH = "heatmap"
HEATMAP_FILES = ['mtb.gpx','gravel.gpx']
CHUNK_SIZE = 8 * 1024 * 1024  # 8MB

CURSOR_BLOB = "tmp/dropbox_cursor.json"

# Formal test for existing secrets
# TODO it is testing feature or it neet ON permanently? Or simple disable message?
#checking_env() temporary OFF

# ---- Initialize Clients ----
app = Flask(__name__)
client = storage.Client()
bucket = client.bucket(GCS_BUCKET_NAME)
secret_client = secretmanager.SecretManagerServiceClient()
conv = Converter()
# for ignore warn from fit 2 gpx
warnings.filterwarnings("ignore", category=UserWarning)
# ---- GCS cursor ----
# Result is True or False
def load_cursor():
# 'loads' convert JSON into Dict, then reads key 'cursor'
# use '.get' instead 'loads(content)["cursor"]' because
# - if cursor doesn't exist, code is stops (KeyError)
# - must use try\except, instead simple check
# - in situation, where doesn't existing cursor is normal
    blob = bucket.blob(CURSOR_BLOB)
    if blob.exists():
        content = blob.download_as_text()
        return json.loads(content).get("cursor")
    else:
        print("Cursor doesn't exist. Creating...")
        return None

def save_cursor(cursor):
    blob = bucket.blob(CURSOR_BLOB)
    data = json.dumps({"cursor": cursor})
    blob.upload_from_string(data, content_type="application/json")

# ---- Loading file in GCS ----
def upload_to_gcs(path, content):
# This function also rewrite as:
# storage.Client().bucket(GCS_BUCKET_NAME).blob(path).upload_from_string(content)
    blob = bucket.blob(path)
    blob.upload_from_string(content)
    print(f"File {path} loaded")

# Fetches a secret from Google Secret Manager
def get_secret(secret_id, version_id="latest"):
    name = f"projects/{GCP_PROJECT_ID}/secrets/{secret_id}/versions/{version_id}"
    response = secret_client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8").strip()

def auth_dropbox():
    dbx_app_secret = get_secret(SECRET_DROPBOX_APP_SECRET)
    dbx_app_key = get_secret(DROPBOX_APP_KEY)
    dbx_refresh_token = get_secret(SECRET_DROPBOX_REFRESH_TOKEN)
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

def sync_dropbox():
    """
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
    if cursor:
        result = dbx.files_list_folder_continue(cursor)
        print("Continue with cursor")
    else:
        result = dbx.files_list_folder(path="", recursive=True) # recursive: all subfolders
        print("Start from root Dropbox")

    synced_files = 0

# 'files_download' return Tuple with two elements (FileMetadata, requests.models.Response),
# therefore we need UNPACKING it and creating two
# variables for handling: metadata and res. But in this code metadata not used.
# If by mistake, write "res = dbx...", that creating tuple without unpacking,
# and in next steps must use 'res[1]'
    for entry in result.entries:
        if isinstance(entry, FileMetadata):
            print(f"Downloaded from Dropbox:{entry.path_lower}")
            metadata, res = dbx.files_download(entry.path_lower)
            #Create path's
            filename = os.path.basename(entry.path_lower)
            local_fit = f"/tmp/{filename}"
            gcs_path = f"dropbox_sync{entry.path_lower}"
            # Save locally for java app (for loading from file, instead load from bites)
            # file save in local_fit var, path set in UPPER variable, local_fit
            with open(local_fit, "wb") as f:
                f.write(res.content)

            # using method .content from response lib. Loading from bytes
            upload_to_gcs(gcs_path, res.content)
            print(f"Uploaded in GCS:{gcs_path}")
            synced_files += 1
            # TODO Parting one pipeline fot two prosess: get all files from dropbox and then start process in bucket
        # extracting some data from original .FIT for Data Labeling
            # For ony files from Wahoo Roam, which name in format: 'YYYY-MM-DD-HHMMSS-elemnt... .fit'
            # timestamp_part = filename.split("-elemnt")[0]
            # dt = datetime.strptime(timestamp_part, "%Y-%m-%d-%H%M%S")
            # formatted = dt.strftime("%Y-%m-%d %H:%M:%S") # extracted timestamp of start activity
            # now = datetime.now(timezone.utc)
            # now_str = now.strftime("%Y-%m-%d %H:%M:%S") # current timestamp

    # ----- FIT >>> CSV
            local_csv = f"/tmp/{filename.replace('.fit', '.csv')}"
            convert_fit_to_csv(local_fit, local_csv, mode='decode')
            csv_gcs_path = f"csv/{os.path.basename(local_csv)}"
            bucket.blob(csv_gcs_path).upload_from_filename(local_csv)
            print(f"Uploaded CSV in GCS:{csv_gcs_path}")
    # ----- Clean csv(fit) from gps problems
            name, ext = os.path.splitext(os.path.basename(local_csv))
            local_csv_fix = f"/tmp/{name}_fixed{ext}"
            bike_model = clean_gps(local_csv, local_csv_fix)
            fit_csv_gcs_path = f"csv_clean/{os.path.basename(local_csv_fix)}"
            bucket.blob(fit_csv_gcs_path).upload_from_filename(local_csv_fix)
            print(f"Fixed:{fit_csv_gcs_path}")
    # ----- 3 phase CSV >>> FIT
            name1 = os.path.splitext(os.path.basename(local_csv))[0]
            local_fix_fit = f"/tmp/{name1}_ffixed.fit"
            convert_fit_to_csv(local_csv_fix, local_fix_fit, mode='encode')
            fix_fit_gcs_path = f"fit_clean/{os.path.basename(local_fix_fit)}"
            bucket.blob(fix_fit_gcs_path).upload_from_filename(local_fix_fit)
            print(f"Uploaded fixed version in:{fix_fit_gcs_path}")
    # ----- 4 phase fixed FIT to strava
            current_mode = get_secret("current-mode")
            if current_mode == "prod":
                access_token = update_strava_token_if_needed()
                upload_id = upload_fit_to_strava(access_token, local_fix_fit)
                activity_id = poll_upload_status(upload_id, access_token)
                updated = update_gear(activity_id, access_token, bike_model)
                print(f"Uploaded to Strava: {updated}")
            elif current_mode == "testing":
                print(f"OFF function Strava uploading")
    # ----- Convert fit to gpx
            local_gpx = f"/tmp/{filename.replace('.fit', '.gpx')}"
            conv.fit_to_gpx(local_fix_fit, local_gpx)
            gpx_gcs_path = f"gpx/{os.path.basename(local_gpx)}"
            bucket.blob(gpx_gcs_path).upload_from_filename(local_gpx)
            print(f"Uploaded GPX in GCS:{gpx_gcs_path}")
    # ----- Create heatmap by bike
            append_gpx_via_compose(local_gpx, bike_model)
        save_cursor(result.cursor)
    print(f"Cursor Dropbox saved:{result.cursor}")
    return f"Synced {synced_files} files"

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
    return ''

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
        dbx_app_secret = get_secret(SECRET_DROPBOX_APP_SECRET)
        #print(repr(dbx_app_secret))

        if not hmac.compare_digest(signature,hmac.new(dbx_app_secret.encode(), request.data, hashlib.sha256).hexdigest()):
            expected_sig = hmac.new(dbx_app_secret.encode(), request.data, hashlib.sha256).hexdigest()
            print(f"Expected signature: {expected_sig}")
            print(f"Received signature: {signature}")
            print("Invalid signature. Request ignored.")
            return '', 403

        #if 'list_folder' in request.json:
        #    print("Received a change notification")
        sync_dropbox()
        print("Webhook received. A file change was detected")

        return '', 200
    return '', 405  # Method Not Allowed

@app.route("/upload_to_dropbox_session", methods=["POST"])
def upload_to_dropbox_session():
    gcs_path = GSC_HEATMAP_PATH
    print(f"gcs_path={gcs_path}") #DELETE
    if not gcs_path:
        return jsonify({"error": "Missing gcs_path"}), 400

    try:
        dbx = auth_dropbox()
        results = []
        for hm_name in HEATMAP_FILES:
            dropbox_path = f"/{DROPBOX_HEATMAP}/{hm_name}"
            print(f"dropbox_path={dropbox_path}")
            blob = bucket.blob(f"{gcs_path}/{hm_name}")
            print(f"blob={blob}")  # DELETE
            if not blob.exists():
                logging.warning(f"Blob not found: {gcs_path}")
                results.append({"file": hm_name, "status": "not found"})
                return jsonify({"error": "Blob not found"}), 404

            # Stream blob content in chunks

            data = blob.download_as_bytes() #dont use blob.open("rb")
            if not data:
                logging.warning(f"Blob is empty: {blob.name}")
                continue
            stream = io.BytesIO(data)
            first_chunk = stream.read(CHUNK_SIZE)
            if not first_chunk:
                logging.warning(f"First chunk empty: {blob.name}")
                continue

            session_start = dbx.files_upload_session_start(first_chunk)
            cursor = dropbox.files.UploadSessionCursor(session_id=session_start.session_id, offset=stream.tell())
            commit = dropbox.files.CommitInfo(path=dropbox_path, mode=dropbox.files.WriteMode.overwrite)

            while True:
                chunk = stream.read(CHUNK_SIZE)
                if not chunk:
                    dbx.files_upload_session_finish(b"", cursor, commit)
                    print("Break reached")
                    break
                if len(chunk) < CHUNK_SIZE:
                    dbx.files_upload_session_finish(chunk, cursor, commit)
                    print(f"Committed {len(chunk)} bytes")
                    break
                else:
                    dbx.files_upload_session_append_v2(chunk, cursor)
                    cursor.offset += len(chunk)
                    print(f"Else committed {len(chunk)} bytes")
            logging.info(f"Uploaded to Dropbox: {dropbox_path}")
            results.append({"file": hm_name, "status": "uploaded", "dropbox_path": dropbox_path})
            print("Results:", results)
        return jsonify({"results": results}), 200
    except Exception as e:
        logging.error(f"Upload failed: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    # Cloud Run set PORT as it want. For testing code locally, already will be using 8080
    # guinocorn ignores this row
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))