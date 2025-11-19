import base64
import json
from flask import Blueprint, request  # Response, jsonify
from power_core.workshop.class_of_workers import ActivityProcessingPipeline
from power_core.project_env.config import GCS_PUB_INPUT_BUCKET, GCS_PUB_OUTPUT_BUCKET

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
        print("Error: Invalid Pub/Sub message format.")
        return "Bad Request: Invalid Pub/Sub message", 400

    # 2. Decode the message data
    # The data we published is in envelope['message']['data'], Base64-encoded.
    try:
        data_bytes = base64.b64decode(envelope['message']['data'])
        payload = json.loads(data_bytes.decode('utf-8'))

        print(f"Received Pub/Sub payload: {payload}")

        # 3. Extract our custom fields from the payload
        gcs_path = payload.get('gcs_path')
        user_email = payload.get('user_email')
        original_filename = payload.get('original_filename')

        if not all([gcs_path, user_email, original_filename]):
            print("Error: Missing required fields in payload.")
            return "Bad Request: Missing data in payload", 400

        # 4. Start the actual processing
        # process_fit_file(gcs_path, user_email, original_filename)
        print(f"This bucket load in worker_class:", GCS_PUB_INPUT_BUCKET)
        repair_flow = ActivityProcessingPipeline(
            gcs_path,
            GCS_PUB_INPUT_BUCKET,
            GCS_PUB_OUTPUT_BUCKET,
            user_email,
            original_filename
        )
        try:
            repair_flow.run_repair_flow()
        except Exception as e:
            print(f"Error running pipeline: {e}")
            return f"Internal Server Error: {e}", 500
        # 5. Acknowledge the message
        # Return a 204 (No Content) to tell Pub/Sub "Success, don't resend."
        return "", 204

    except Exception as e:
        # If we fail (return 500), Pub/Sub will automatically retry the message.
        print(f"Error processing message: {e}")
        return f"Internal Server Error: {e}", 500
