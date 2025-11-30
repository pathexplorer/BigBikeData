import base64
import json
from flask import Blueprint, request  # Response, jsonify
from power_core.workshop.class_of_workers import ActivityProcessingPipeline
from power_core.project_env.config import GCS_PUB_INPUT_BUCKET, GCS_PUB_OUTPUT_BUCKET
from gcp_actions.firestore_as_swith import check_and_mark_processed, mark_processing_complete, mark_processing_failed

import logging
logger = logging.getLogger(__name__)


bp3 = Blueprint("public_processing", __name__)

@bp3.route('/pubsub-processing-handler', methods=['POST'])
def handle_pubsub_message():
    """
    This is the internal-facing route that Pub/Sub (via Eventarc) will call.
    It parses the Pub/Sub message, extracts your payload, and starts the job.
    """
    # Get the full Pub/Sub message
    envelope = request.get_json()

    # 1. Check that this is a valid Pub/Sub message
    if not envelope or 'message' not in envelope:
        logger.error("Error: Invalid Pub/Sub message format.")
        return "Bad Request: Invalid Pub/Sub message", 400

    # 2. Decode the message data
    # The data we published is in envelope['message']['data'], Base64-encoded.
    try:
        data_bytes = base64.b64decode(envelope['message']['data'])
        payload = json.loads(data_bytes.decode('utf-8'))

        logger.debug(f"Received PubSub payload: {payload}")

        # 3. Extract our custom fields from the payload
        gcs_path = payload.get('gcs_path')
        user_email = payload.get('user_email')
        logger.info(f"Get message from user: {user_email}")
        original_filename = payload.get('original_filename')
        logger.info(f"Request to process file: {original_filename}")
        upload_id = payload.get('upload_id')
        locale = payload.get('locale', 'en') # Extract locale, default to 'en'


        if not all([gcs_path, user_email, original_filename, upload_id]):
            logger.error("Error: Missing required fields in payload.")
            return "Bad Request: Missing data in payload", 400

        if check_and_mark_processed(upload_id):
            logger.warning(f"Skipping duplicate message: {upload_id}")
            return "Already processed", 200


        # 4. Start the actual processing
        # process_fit_file(gcs_path, user_email, original_filename)
        logger.debug(f"This bucket load in worker_class: {GCS_PUB_INPUT_BUCKET}")
        repair_flow = ActivityProcessingPipeline(
            gcs_path,
            GCS_PUB_INPUT_BUCKET,
            GCS_PUB_OUTPUT_BUCKET,
            user_email,
            original_filename,
            locale=locale
        )
        try:
            result = repair_flow.run_repair_flow()
            mark_processing_complete(upload_id, result_data={'result': result})
        except Exception as e:
            logger.debug(f"Processing failed for {upload_id}: {e}")
            mark_processing_failed(upload_id, error_message=str(e))
            # Acknowledge the message to prevent Pub/Sub retries for this failure.
            return f"Processing failed: {e}", 200
        # 5. Acknowledge the message
        # Return a 204 (No Content) to tell Pub/Sub "Success, don't resend."
        return "", 204

    except Exception as e:
        # If we fail (return 500), Pub/Sub will automatically retry the message.
        logger.error(f"Error processing message: {e}")
        return f"Internal Server Error: {e}", 500
