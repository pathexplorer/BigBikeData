from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, send_from_directory, \
    session, abort
from flask_babel import _
import uuid
from gcp_actions.blob_manipulation import upload_to_gcp_bucket, generate_unique_filename
from gcp_actions.pubsub import publish_message
from gcp_actions.common_utils.local_runner import check_cloud_or_local_run
from site_handler.utilites.site_config import GCP_TOPIC_NAME, S_ACCOUNT_RUN
from gcp_actions.client import get_any_client
from gcp_actions.common_utils.generate import g_download_link
from datetime import datetime, timezone
from google.api_core import exceptions as google_exceptions


import logging
logger = logging.getLogger(__name__)

check_cloud_or_local_run()

bp3 = Blueprint('frontend', __name__, url_prefix='/')

# --- Configuration ---
ALLOWED_EXTENSIONS = {'fit'}
bucket = "GCS_PUB_INPUT_BUCKET"

def allowed_file(filename):
    """Helper to check file extension."""
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@bp3.route('/', methods=['GET'])
def index():
    """
    Serves the index.html file from the application root directory.
    """
    # current_app.logger.info(f"--- Index Route: Session Language = {session.get('language')} ---")
    # The '.' refers to the root directory of the application
    return render_template('index.html')

@bp3.route('/robots.txt')
def robots_txt():
    """Serves the robots.txt file from the static directory."""
    # Use the application's configured static folder, which is robust
    # and works in both local and deployed environments.
    static_folder = current_app.static_folder
    return send_from_directory(static_folder, 'robots.txt', mimetype='text/plain')

@bp3.route('/upload', methods=['POST'])
def handle_file_upload():
    """
    This route is called when the user clicks 'Submit' on the form
    from index.html.
    """
    upload_id = str(uuid.uuid4())

    if 'file' not in request.files:
        flash(_('No file part in the request.'), 'error')
        return redirect(url_for('frontend.index'))

    file = request.files['file']
    logger.info(f"Received file object: {file}")


    user_email = request.form.get('email_address')  # Example of getting other form data

    if not user_email:
        flash(_('Email address is required.'), 'error')
        return redirect(url_for('frontend.index'))

    if file.filename == '':
        flash(_('No file was selected.'), 'error')
        return redirect(url_for('frontend.index'))

    if not allowed_file(file.filename):
        flash(_('Invalid file type. Only .fit files are accepted.'), 'error')
        return redirect(url_for('frontend.index'))

    try:
        # Upload to GCS
        # 2. Robust File Size Measurement
        file_stream = file.stream

        # file.stream provides the file content without saving it to the local disk
        gen_unic = generate_unique_filename(file.filename, "riders_bucket")

        file_stream.seek(0)
        file_data = file_stream.read()
        content_type = 'application/octet-stream'

        gcs_unique_path = upload_to_gcp_bucket(bucket, gen_unic, file_data, "string_path", content_type)
        logger.debug(f"GCS unique path generated: {gcs_unique_path}")
        # Trigger Backend Pipeline via Pub/Sub
        # Publish the file location and user email for the workers to process
        message_data = {
            "gcs_path": gcs_unique_path,
            "user_email": user_email,
            "original_filename": file.filename,
            "upload_id": upload_id,
            "locale": session.get('language', 'en')

        }

        # Publish the message
        publish_message(GCP_TOPIC_NAME, message_data)

        # Clear the upload_id after a successful publication
        session.pop('upload_id', None)

        # 4. Success Redirect
        return redirect(url_for('frontend.success'))

    except ValueError as e:
        flash(_(f"Configuration Error: {e}"), 'error')
        current_app.logger.error(f"Configuration Error: {e}")
        return redirect(url_for('frontend.index'))

    except Exception as e:
        flash(_("An unexpected error occurred during upload or processing."), 'error')
        current_app.logger.error(f"Processing Error: {e}")
        return redirect(url_for('frontend.index'))

@bp3.route('/download/<uuid:download_id>', methods=['GET'])
def download_file(download_id):
    """
    Handles a download request by validating a UUID and generating a short-lived signed URL.
    """
    db = get_any_client("firestore")
    doc_ref = db.collection("download_links").document(str(download_id))
    
    try:
        doc = doc_ref.get()
        if not doc.exists:
            logger.warning(f"Download attempt with invalid ID: {download_id}")
            return render_template('404_expired.html', message=_("This download link is invalid or has been used.")), 404

        data = doc.to_dict()
        expires_at = data.get('expires_at')

        # Ensure expires_at is timezone-aware for correct comparison
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if datetime.now(timezone.utc) > expires_at:
            logger.warning(f"Download attempt with expired ID: {download_id}")
            return render_template('404_expired.html', message=_("This download link has expired.")), 404

        # Get the service account to impersonate, which has permission to create signed URLs.
        impersonate_sa = S_ACCOUNT_RUN
        logger.info(f"Get the service account to impersonate: {impersonate_sa}")

        # If valid, generate a very short-lived URL for the actual download
        signed_url = g_download_link(
            bucket_name=data['bucket_name'],
            blob_name=data['blob_name'],
            download_filename=data['download_filename'],
            expiration_minutes=1,
            impersonate_sa=impersonate_sa
        )
        
        return redirect(signed_url)

    except google_exceptions.NotFound as e:
        logger.error(f"File not found in GCS during download for ID {download_id}: {e}")
        return render_template('404_expired.html', message=_("The file for this link could not be found. It may have been deleted.")), 404
    
    except Exception as e:
        logger.error(f"Unexpected error during download process for ID {download_id}: {e}")
        abort(500)


@bp3.route('/success', methods=['GET'])
def success():
    """Shows a confirmation page with a proposal to open the main page again."""
    return render_template('success.html')
