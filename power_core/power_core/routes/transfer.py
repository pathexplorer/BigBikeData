from power_core.dropbox_usage.get_from_dropbox import connect_to_dropbox
from power_core.dropbox_usage.utils import DropboxAuth
import logging
from power_core.routes.pubsub_handler import handle_message
from flask import Blueprint, request, jsonify, Response
from power_core.dropbox_usage.upload_to_dropbox import upload_custom_files_session
from power_core.project_env.config import PRIVATE_UPLOAD_TOKEN

logger = logging.getLogger(__name__)

bp1 = Blueprint("upload", __name__)
bp2 = Blueprint("transfer", __name__)
bp3 = Blueprint("public_processing", __name__)
bp_private = Blueprint("private_processing", __name__)

@bp2.route('/q50WoEoBoHoOoOoK0iBa216SztNO5R6c2vK0tb', methods=['POST'])
def dropbox_webhook():
    """
    Handles the webhook verification and triggers the sync process.
    This is the PRODUCER endpoint.
    """
    # 1. Verify the request is from Dropbox
    da = DropboxAuth()
    if not da.check_signature():
        return Response("Forbidden", status=403)
    logger.debug("✅ Webhook received. Signature is valid.")

    # 2. Trigger the main sync logic (which now publishes to Pub/Sub)
    try:
        success = connect_to_dropbox()
        if success:
            return jsonify({"status": "sync triggered"}), 200
        else:
            return jsonify({"status": "sync failed"}), 500
    except Exception as e:
        logger.error(f"Error triggering connect_to_dropbox: {e}", exc_info=True)
        return jsonify({"status": "internal error"}), 500

@bp2.route('/challenge', methods=['GET'])
def webhook_verification():
    """ Responds to the Dropbox webhook verification challenge."""
    challenge = request.args.get('challenge')
    if challenge:
        logger.info(f"Responding to Dropbox challenge: {challenge}")
        return Response(challenge, headers={'Content-Type': 'text/plain'})
    return "No challenge parameter", 400

@bp3.route('/pubsub-processing-handler', methods=['POST'])
def handle_pubsub_message():
    return handle_message("public")

@bp_private.route('/private-processing-handler', methods=['POST'])
def handle_private_message():
    return handle_message("private")

@bp1.route(f"/{PRIVATE_UPLOAD_TOKEN}", methods=["POST"])
def trigger_upload():
    logger.info("Uploading custom files session")
    data = request.get_json(force=True)
    gcs_folder = data.get("gcs_folder")
    if not gcs_folder:
        return jsonify({"error": "Missing 'gcs_folder'"}), 400
    if not gcs_folder.endswith("/"):
        gcs_folder += "/"
    result = upload_custom_files_session(gcs_folder)
    return jsonify(result)
