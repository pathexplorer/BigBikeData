from datetime import datetime, timezone
from gcp_actions.client import get_bucket
from power_core.workshop.workers import ActivityProcessingPipeline
from gcp_actions.firestore_box.json_manipulations import FirestoreMagic
import logging

logger = logging.getLogger(__name__)


def list_gcs_files(bucket_name, path_prefix):
    client = get_bucket(bucket_name)
    blobs = client.list_blobs(prefix=path_prefix)
    return [f'{blob.name}' for blob in blobs]
    # return [f'gs://{bucket_name}/{blob.name}' for blob in blobs]


def run_pipeline_on_gcs(bucket_name: str, path_prefix):
    """
    Start the Second stage of a pipeline
    """
    fires = FirestoreMagic("cursors", "storage_cursor")
    # 1. Get all files in the folder in GCS
    all_files = list_gcs_files(bucket_name, path_prefix)

    # 2. Load the manifest of previously processing files
    processed_files = fires.load_firejson()
    logger.debug(f"Found {len(processed_files)} records")

    for blob_path in all_files:
        if blob_path not in processed_files:
            fp = ActivityProcessingPipeline(blob_path, bucket_name)
            fp.run_full_pipeline()
            logger.debug(f"Now Processing {blob_path}")
            # look_changes_files = fires.load_firejson()
            # logger.debug(f"Found {len(processed_files)} records after processing {blob_path}")
            processed_files[blob_path] = datetime.now(timezone.utc).isoformat()  #python 3.10 dependency instead .utcnow()
            fires.set_firejson(processed_files, True)
        else:
            logger.warning(f"This {blob_path} already exists")
            return


# if __name__ == '__main__':
#     # data = {}
#     fires1 = FirestoreMagic("cursors", "storage_cursor")
#     # DELETE FIELD
#     print(len(fires1.load_firejson()))
#     field = "2023-01-15-074849-elemnt roam d8c7-176-0.fit"
#     # field = "test"
#     fires1.delete_field_firejson(field)
#     print(len(fires1.load_firejson()))

    # processed_files = fires1.create_firejson("storage_cursor", data)

    # processed_files1 = fires1.load_firejson()
    # print(len(processed_files1))
    # print(type(processed_files))