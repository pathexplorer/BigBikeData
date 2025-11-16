from flask import Blueprint, request, jsonify
from dropbox_usage.upload_to_dropbox import upload_custom_files_session
from project_env.config import PRIVATE_UPLOAD_TOKEN

bp1 = Blueprint("upload", __name__)

@bp1.route(f"/${PRIVATE_UPLOAD_TOKEN}", methods=["POST"])
def trigger_upload():
    print("Uploading custom files session")
    data = request.get_json(force=True)
    gcs_folder = data.get("gcs_folder")
    if not gcs_folder:
        return jsonify({"error": "Missing 'gcs_folder'"}), 400
    if not gcs_folder.endswith("/"):
        gcs_folder += "/"
    result = upload_custom_files_session(gcs_folder)
    return jsonify(result)
