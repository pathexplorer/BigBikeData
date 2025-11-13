import os
from gcs.client import get_bucket
bucket = get_bucket()

def upload_blob_from_file(gcs_path: str, local_path: str) -> None:
    if not os.path.isfile(local_path):
        raise FileNotFoundError(f"Local file not found: {local_path}")
    if not gcs_path:
        raise ValueError("GCS path must not be empty")
    try:
        bucket.blob(gcs_path).upload_from_filename(local_path)
    except Exception as e:
        raise RuntimeError(f"Failed to upload {local_path} to {gcs_path}: {e}")

def download_blob_if_exists(blob_name: str, local_path: str) -> bool:
    if not blob_name:
        raise ValueError("Blob name must not be empty")
    if not local_path:
        raise ValueError("Local path must not be empty")
    blob = bucket.blob(blob_name)
    if not blob.exists():
        return False
    # Create folder if it doesn't exist
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    try:
        blob.download_to_filename(local_path)
        return True
    except Exception as e:
        raise RuntimeError(f"Failed to download '{blob_name}' to '{local_path}': {e}")

def delete_blob(blob_name):
    blob = bucket.blob(blob_name)
    if blob.exists():
        blob.delete()