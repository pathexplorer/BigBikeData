import base64
import json
from flask import Blueprint, request
from power_core.workshop.workers import ActivityProcessingPipeline
from power_core.project_env.config import GCS_PUB_INPUT_BUCKET, GCS_PUB_OUTPUT_BUCKET
from gcp_actions.firestore_as_swith import check_and_mark_processed
from gcp_actions.firestore_box.json_manipulations import FirestoreMagic
from google.cloud import firestore

import logging
logger = logging.getLogger(__name__)


bp3 = Blueprint("public_processing", __name__)

@bp3.route('/pubsub-processing-handler', methods=['POST'])
def handle_pubsub_message():
    """
    This is the internal-facing route that Pub/Sub will call.
    It parses the Pub/Sub message, extracts the payload, and starts the job.
    """
    envelope = request.get_json()

    if not envelope or 'message' not in envelope:
        logger.error("Error: Invalid Pub/Sub message format.")
        return "Bad Request: Invalid Pub/Sub message", 400

    # 2. Decode the message data
    # The data we published is in envelope['message']['data'], Base64-encoded.
    try:
        data_bytes = base64.b64decode(envelope['message']['data'])
        payload = json.loads(data_bytes.decode('utf-8'))

        logger.debug(f"Received PubSub payload: {payload}")

        file_data_b64 = payload.get('file_data')
        user_email = payload.get('user_email')
        logger.info(f"Get message from user: {user_email}")
        original_filename = payload.get('original_filename')
        logger.info(f"Request to process file: {original_filename}")
        upload_id = payload.get('upload_id')
        locale = payload.get('locale', 'en')

        if not all([file_data_b64, user_email, original_filename, upload_id]):
            logger.error("Error: Missing required fields in payload.")
            return "Bad Request: Missing data in payload", 400

        if check_and_mark_processed(upload_id):
            logger.warning(f"Skipping duplicate message: {upload_id}")
            return "Already processed", 200

        # Decode the file data from Base64
        try:
            file_data = base64.b64decode(file_data_b64)
        except (TypeError, ValueError) as e:
            logger.error(f"Error decoding file_data from Base64: {e}")
            return "Bad Request: Invalid Base64 data", 400

        # Start the actual processing
        repair_flow = ActivityProcessingPipeline(
            blob_path=None,  # No GCS path is needed
            bucket_name=GCS_PUB_INPUT_BUCKET,
            bucket_name_output=GCS_PUB_OUTPUT_BUCKET,
            user_email=user_email,
            original_filename=original_filename,
            locale=locale,
            file_data=file_data  # Pass the raw file data
        )
        fm = FirestoreMagic("processed_messages", upload_id)
        try:
            result = repair_flow.run_repair_flow()

            result_data = {'result': result}
            update_data = {
                'completed_at': firestore.SERVER_TIMESTAMP,
                'status': 'completed'
            }
            if result_data:
                update_data['result'] = result_data

            fm.update_firejson(result_data)
            logger.info(f"✅ Marked {upload_id} as completed")
            # mark_processing_complete(upload_id, result_data={'result': result})
        except Exception as e:
            logger.debug(f"Processing failed for {upload_id}: {e}")
            error_message = str(e)
            fail_update = {
                'failed_at': firestore.SERVER_TIMESTAMP,
                'status': 'failed',
                'error': error_message or 'Unknown error'
            }
            fm.update_firejson(fail_update)
            logger.error(f"❌ Marked {upload_id} as failed: {error_message}")
            # mark_processing_failed(upload_id, error_message=str(e))
            return "Processing failed", 200

        return "", 204

    except Exception as e:
        logger.error(f"Error processing message: {e}")
        return "Internal Server Error", 500
