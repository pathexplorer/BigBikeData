import base64
import json
import logging
from datetime import datetime, timedelta, timezone
from flask import request
from google.cloud import firestore
from google.cloud.firestore import SERVER_TIMESTAMP
from gcp_actions.client import get_any_client
from gcp_actions.firestore_box.json_manipulations import FirestoreMagic
from power_core.workshop.workers import ActivityProcessingPipeline

logger = logging.getLogger(__name__)

# Configuration for the different pipeline strategies
PIPELINE_CONFIG = {
    "private": {
        "required_fields": ["dropbox_path", "original_filename", "upload_id"],
        "collection": "dropbox_messages",
        "method": "run_full_pipeline",
        "pipeline_args": ["original_filename", "dropbox_path"]
    },
    "public": {
        "required_fields": ["file_data", "user_email", "original_filename", "upload_id"],
        "collection": "processed_messages",
        "method": "run_repair_flow",
        "pipeline_args": ["original_filename", "user_email", "file_data", "locale"]
    }
}


def check_and_mark_processed(idempotency_key: str, collection_name: str, ttl_hours: int = 24) -> bool:
    """
    Checks if a message is processed. Returns True if duplicate, False if new.
    """
    try:
        db = get_any_client("firestore")
        doc_ref = db.collection(collection_name).document(idempotency_key)
        doc = doc_ref.get()

        if doc.exists:
            processed_at = doc.to_dict().get('processed_at')
            logger.warning(f"Duplicate message: {idempotency_key} (processed at {processed_at})")
            return True

        doc_ref.set({
            'idempotency_key': idempotency_key,
            'processed_at': SERVER_TIMESTAMP,
            'expires_at': datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
        })
        logger.debug(f"✅ New message detected: {idempotency_key}")
        return False

    except Exception as e:
        logger.error(f"❌ Error checking idempotency: {e}")
        # Fail-safe: If DB fails, assume duplicate to prevent infinite retry loops on error
        return True


def execute_pipeline(pipeline_instance, method_name: str, upload_id: str, collection_name: str):
    """
    Executes the pipeline method and handles Firestore status updates (Success/Failure).
    """
    fm = FirestoreMagic(collection_name, upload_id)

    try:
        # Dynamically call the method (run_full_pipeline or run_repair_flow)
        runner = getattr(pipeline_instance, method_name)
        result = runner()

        success_payload = {
            'completed_at': firestore.SERVER_TIMESTAMP,
            'status': 'completed',
            'result': {'result': result} if result else {}
        }
        fm.update_firejson(success_payload)
        logger.debug(f"✅ Successfully processed {upload_id}")
        return "", 204

    except Exception as e:
        error_msg = str(e) or "Unknown error"
        logger.error(f"❌ Processing failed for {upload_id}: {error_msg}")

        fail_payload = {
            'failed_at': firestore.SERVER_TIMESTAMP,
            'status': 'failed',
            'error': error_msg
        }
        fm.update_firejson(fail_payload)
        # We return 200 to Pub/Sub to acknowledge receipt so it doesn't retry a logic error forever
        return "Processing failed", 200


def handle_message(style_pipeline: str):
    """
    Parses a Pub/Sub message and routes to the correct pipeline strategy.
    """
    envelope = request.get_json()
    if not envelope or 'message' not in envelope:
        logger.error("Invalid Pub/Sub message format.")
        return "Bad Request: Invalid Pub/Sub message", 400

    try:
        # 1. Parse Payload
        data_bytes = base64.b64decode(envelope['message']['data'])
        payload = json.loads(data_bytes.decode('utf-8'))

        # 2. Get Strategy Config
        config = PIPELINE_CONFIG.get(style_pipeline)
        if not config:
            logger.error(f"Unknown pipeline style: {style_pipeline}")
            return "Bad Request: Unknown pipeline style", 400

        # 3. Validate Fields
        missing = [f for f in config['required_fields'] if f not in payload]
        if missing:
            logger.error(f"Missing fields for {style_pipeline}: {missing}")
            return f"Bad Request: Missing {missing}", 400

        upload_id = payload['upload_id']

        # 4. Idempotency Check
        if check_and_mark_processed(upload_id, config['collection']):
            return "Already processed", 200

        # 5. Prepare Data (Special handling for Base64 file_data in Public flow)
        pipeline_kwargs = {k: payload.get(k) for k in config['pipeline_args']}
        pipeline_kwargs['pipeline_type'] = style_pipeline

        if style_pipeline == "public":
            try:
                pipeline_kwargs['file_data'] = base64.b64decode(payload['file_data'])
                pipeline_kwargs['locale'] = payload.get('locale', 'en')
            except Exception as e:
                logger.error(f"Base64 decode error: {e}")
                return "Bad Request: Invalid file data", 400

        logger.debug(f"Starting {style_pipeline} pipeline for {upload_id}")

        # 6. Instantiate and Execute
        pipeline = ActivityProcessingPipeline(**pipeline_kwargs)
        return execute_pipeline(pipeline, config['method'], upload_id, config['collection'])

    except Exception as e:
        logger.error(f"Critical error in handle_message: {e}", exc_info=True)
        return "Internal Server Error", 500