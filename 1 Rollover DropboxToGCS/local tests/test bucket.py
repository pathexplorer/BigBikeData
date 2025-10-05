from google.cloud import storage
import os
from dotenv import load_dotenv

load_dotenv(dotenv_path="other/keys.env")

GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME")

file_path = "../other/a.json"
if os.path.exists(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        data = f.read()
else:
    print("FILE NOT FOUND:", file_path)
# Client initialization with JSON credentials
client = storage.Client.from_service_account_json(file_path)

# Connect to bucket
bucket = client.get_bucket(GCS_BUCKET_NAME)
for blob in bucket.list_blobs():
    print("Files in bucket:", blob.name)
