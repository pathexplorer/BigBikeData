import os
from google.cloud import storage
from dotenv import load_dotenv
load_dotenv(dotenv_path="../other/keys.env")
GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME")
GCS_CLOUD_PROJECT = os.environ.get("GCS_CLOUD_PROJECT")
GSC_HEATMAP_PATH = "heatmap"
file_path = "../other/a.json"
if os.path.exists(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        data = f.read()
else:
    print("FILE NOT FOUND:", file_path)
# Client initialization with JSON credentials
client = storage.Client.from_service_account_json(file_path)
bucket = client.bucket(GCS_BUCKET_NAME)

def list_gcs_files(prefix):
    blobs = bucket.list_blobs(prefix=prefix)
    return [f'{blob.name}' for blob in blobs]

ref = f"{GSC_HEATMAP_PATH}"

print(list_gcs_files(ref))
print(ref)