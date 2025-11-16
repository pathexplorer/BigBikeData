from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from gcp_actions.blob_manipulation import upload_to_gcp_bucket, generate_unique_filename
from gcp_actions.pubsub import publish_message
from project_env.config import GCS_PUBLIC_BUCKET
import os

bp3 = Blueprint('frontend', __name__, url_prefix='/')

# --- Configuration ---
# In a real app, these would come from environment variables
ALLOWED_EXTENSIONS = {'fit'}
PUB_SUB_TOPIC = 'fit-file-processing-topic'
bucket="GCS_PUBLIC_BUCKET"

def allowed_file(filename):
    """Helper to check file extension."""
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS



@bp3.route('/', methods=['GET'])
def index():
    """
    Shows the main page with the file upload form.
    Flask will look for 'index.html' in a folder named 'templates'.
    """
    return render_template('index.html')


@bp3.route('/upload', methods=['POST'])
def handle_file_upload():
    """
    This route is called when the user clicks 'Submit' on the form
    from index.html.
    """
    if 'file' not in request.files:
        flash('No file part in the request.')
        return redirect(url_for('frontend.index'))

    file = request.files['file']
    user_email = request.form.get('email_address')  # Example of getting other form data

    if not user_email:
        flash('Email address is required.')
        return redirect(url_for('frontend.index'))

    if file.filename == '':
        flash('No file was selected.')
        return redirect(url_for('frontend.index'))

    if not allowed_file(file.filename):
        flash('Invalid file type. Only .fit files are accepted.')
        return redirect(url_for('frontend.index'))

    try:
        # Upload to GCS
        # file.stream provides the file content without saving it to local disk
        gen_unic = generate_unique_filename(file.filename, "riders_bucket")
        # gcs_unique_path = upload_file_to_gcs(file.stream, file.filename)

        gcs_unique_path = upload_to_gcp_bucket(bucket, gen_unic, file.stream, "file")

        # Trigger Backend Pipeline via Pub/Sub
        # Publish the file location and user email for the workers to process
        message_data = {
            "gcs_path": gcs_unique_path,
            "user_email": user_email,
            "original_filename": file.filename
        }
        # Publish the message (you would need the actual Pub/Sub client here)
        publish_message(PUB_SUB_TOPIC, message_data)

        # 4. Success Redirect
        return redirect(url_for('frontend.success'))

    except ValueError as e:
        # Catch configuration errors (like missing bucket name)
        flash(f"Configuration Error: {e}")
        current_app.logger.error(f"Configuration Error: {e}")
        return redirect(url_for('frontend.index'))

    except Exception as e:
        # Catch any other unexpected errors during upload or publish
        flash("An unexpected error occurred during upload or processing.")
        current_app.logger.error(f"Processing Error: {e}")
        return redirect(url_for('frontend.index'))



@bp3.route('/success', methods=['GET'])
def success():
    """Shows a confirmation page."""
    return "Thank you! Your file is being processed. We will email the result."
    # return render_template('success.html')