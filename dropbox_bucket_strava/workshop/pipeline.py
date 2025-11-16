import json
from datetime import datetime, timezone
from google.cloud.exceptions import NotFound
from workshop.class_of_workers import ActivityProcessingPipeline
from gcp_actions.client import get_bucket

bucket_name="GCS_BUCKET_NAME"
bucket = get_bucket(bucket_name)

def run_pipeline_on_gcs(bucket_name1: str, path_prefix, manifest_blob_path):
    """
    Start Second stage of pipeline
    """
    # 1. Get all files in folder in GCS
    all_files = list_gcs_files(bucket_name1, path_prefix)
    # 2. Load mainfest of processing files
    processed_files = load_processed_manifest(manifest_blob_path)
    for blob_path in all_files:
        if blob_path not in processed_files:
            print(f"Now Processing {blob_path}")
            full_pipeline = ActivityProcessingPipeline(blob_path, bucket_name)
            full_pipeline.run_full_pipeline()
            mark_as_processed(manifest_blob_path, blob_path)

def list_gcs_files(bucket_name1, prefix):
    blobs = bucket.list_blobs(prefix=prefix)
    return [f'gs://{bucket_name1}/{blob.name}' for blob in blobs]

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