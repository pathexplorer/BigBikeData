import tempfile
from datetime import datetime, timezone
import json
from google.cloud import storage
import os
from google.cloud.exceptions import NotFound
import config
from dotenv import load_dotenv
from urllib.parse import urlparse

from config import GCS_BUCKET_NAME

load_dotenv(dotenv_path="../other/keys.env")

file_path = "../other/a.json"
if os.path.exists(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        data = f.read()
else:
    print("FILE NOT FOUND:", file_path)
# Client initialization with JSON credentials
client = storage.Client.from_service_account_json(file_path)
bucket = client.bucket(config.GCS_BUCKET_NAME)


# Connect to bucket
#bucket = client.get_bucket(GCS_BUCKET_NAME)
#for blob in bucket.list_blobs():
#    print("Files in bucket:", blob.name)
#
# def list_gcs_files(bucket_name, prefix):
#     blobs = bucket.list_blobs(prefix=prefix)
#     print("Blobs", blobs)
#     print("Pref", prefix)
#     return [f'gs://{bucket_name}/{blob.name}' for blob in blobs]
#
# rez = list_gcs_files(config.GCS_BUCKET_NAME, config.GSC_ORIG_FIT_FOLDER)
# local_fit = "D:/111/tt.txt"
# with open(local_fit, "w") as f:  # Save locally for java app (for loading from file, instead load from bites)
#     f.write('gs://wahoobucket/dropbox_sync/apps/wahoofitness/20.txt')
#
# print(rez)
# print(type(rez))

def run_pipeline_on_gcs(bucket_name: str, path_prefix, manifest_blob_path):
    """
    Start Second stage of pipeline
    :param bucket_name:
    :param path_prefix:
    :param manifest_blob_path:
    :return:
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
    path = f"{config.GSC_ORIG_FIT_FOLDER}/{filename}"
    print("New path",path)
    print(f"Processing {filename}")
    local_fit = f"/tmp/{filename}"
    print(f"Local fit is {local_fit} ")
    os.makedirs("/tmp", exist_ok=True)
    blob = bucket.blob(path)
    print(f"qqq {blob_path} qqq")
    print(f"eeeee {blob} qqq")
    blob.download_to_filename(local_fit)
    print(f"✅ Завантажено: {blob_path} → {local_fit}")






run_pipeline_on_gcs(config.GCS_BUCKET_NAME, config.GSC_ORIG_FIT_FOLDER, config.MAINFEST_GSC_PATH)
