import logging
import os
import shutil
import datetime
from fit2gpx import Converter
from gcp_actions.blob_manipulation import upload_to_gcp_bucket, download_from_gcp_bucket
from gcp_actions.client import get_env_and_cashed_it
from gcp_actions.firestore_as_swith import check_swith_status
from power_core.strava.upload import upload_fit_to_strava, poll_upload_status, update_gear
from power_core.strava.auth import update_strava_token_if_needed
from power_core.heatmap_gpx.append_function import append_gpx_via_compose
from power_core.workshop.instruments import convert_fit_to_csv, clean_gps
from power_core.utilites.email_sender import send_email
from power_core.utilites.generate import g_download_link
from power_core.project_env.config import GSC_ORIG_FIT_FOLDER

# Initialize global dependencies
CONVERTER = Converter()

class ActivityProcessingPipeline:
    """
    A class to manage the multi-stage processing of a .FIT activity file,
    including download, GPS cleaning, re-encoding, and upload to Strava/Heatmap.
    """
    def __init__(
            self,
            blob_path: str,
            bucket_name: str,
            bucket_name_output: str | None = None,
            user_email: str | None = None,
            original_filename: str | None = None
    ):
        """
        Initializes the pipeline with the source GCS blob path and sets up local paths.
        Args:
            blob_path: The full GCS path of the original .FIT file
                       (e.g., gs://bucket/path/to/file.fit).
        """
        self.path_to_buckets = None
        self.user_email = user_email
        self.original_filename = original_filename
        self.bucket_name_output = bucket_name_output
        self.bucket_name = bucket_name
        self.blob_path = blob_path
        self.filename = os.path.basename(blob_path)
        self.base_name = os.path.splitext(self.filename)[0]
        self.bike_model = None # To be determined in the cleaning stage

        # Local temporary file paths
        os.makedirs("/tmp", exist_ok=True)
        self.local_fit_path = f"/tmp/{self.filename}"
        self.local_unexplored_csv_path = f"/tmp/{self.base_name}.csv"
        self.local_fixed_csv_path = f"/tmp/{self.base_name}_fixed.csv"
        self.local_fixed_fit_path = f"/tmp/{self.base_name}_cleaned.fit"
        self.local_gpx_path = f"/tmp/{self.base_name}.gpx"

        # GCS upload paths
        self.gcs_orig_path = f"{GSC_ORIG_FIT_FOLDER}/{self.filename}"
        self.gcs_fixed_csv_path = f"csv_clean/{os.path.basename(self.local_fixed_csv_path)}"
        self.gcs_fixed_fit_path = f"fit_clean/{os.path.basename(self.local_fixed_fit_path)}"
        self.gcs_gpx_path = f"gpx/{os.path.basename(self.local_gpx_path)}"

        logging.info(f"Pipeline initialized for activity: {self.filename}")
        logging.info("-" * 40)

    def stage_01_download_fit(self, mode: str ):
        """
        Downloads the original .FIT file from GCS to the local temporary directory.
        """
        logging.debug("B", self.bucket_name)
        logging.debug("Q", self.gcs_orig_path)
        logging.debug("W", self.local_fit_path)
        logging.debug("Q", self.blob_path)

        user_project = None
        if mode == "personal":
            self.path_to_buckets = self.gcs_orig_path
        elif mode == "help_riders":
            self.path_to_buckets = self.blob_path
            # When helping riders, we might be accessing a "Requester Pays" bucket.
            # We need to specify our project to pay for the download.
            user_project = get_env_and_cashed_it("GCP_PROJECT_ID")

        logging.debug(f"🌍 Stage 01: Downloading FIT from GCS: {self.path_to_buckets}")
        try:
            download_from_gcp_bucket(
                self.bucket_name,
                self.path_to_buckets,
                self.local_fit_path,
                "blob",
                user_project=user_project
            )
            logging.info(f"   Success: .fit downloaded to VM at: {self.local_fit_path}")
        except Exception as e1:
            logging.error(f"   Error: Failed to download FIT. {e1}")
            raise

    def stage_02_fit_to_unexplored_csv(self):
        """
        Converts the local .FIT file to an 'unexplored' CSV for processing.
        """
        logging.debug(f"📊 Stage 02: Decoding FIT to CSV")
        try:
            convert_fit_to_csv(self.local_fit_path, self.local_unexplored_csv_path, mode='decode')
            logging.info("   Success: FIT decoded to CSV. Skipped saving the unexplored CSV.")
        except Exception as e2:
            logging.error(f"   Error: Failed to decode FIT to CSV. {e2}")
            raise

    def stage_03_clean_gps_data(self):
        """
        Cleans the unexplored CSV, fixes GPS problems, stores bike model,
        and uploads the fixed CSV to GCS.
        """
        logging.debug(f"🧹 Stage 03: Cleaning GPS data and uploading fixed CSV")
        try:
            self.bike_model = clean_gps(self.local_unexplored_csv_path, self.local_fixed_csv_path)
            upload_to_gcp_bucket(self.bucket_name, self.gcs_fixed_csv_path, self.local_fixed_csv_path, "filename")
            logging.debug(f"   Success: GPS cleaned (Bike Model: {self.bike_model}).")
            logging.info(f"   Uploaded fixed CSV to: {self.gcs_fixed_csv_path}")
        except Exception as e3:
            logging.error(f"   Error: Failed during GPS cleaning or CSV upload. {e3}")
            raise

    def stage_04_fixed_csv_to_fit(self, mode: str ):
        """
        Re-encodes the fixed CSV back into a clean .FIT file and uploads it to GCS.
        """
        logging.debug(f"🔄 Stage 04: Encoding fixed CSV back to FIT and uploading")
        user_project = None
        if mode == "personal":
            self.bucket_name = self.bucket_name
        elif mode == "help_riders":
            self.bucket_name = self.bucket_name_output
            user_project = get_env_and_cashed_it("GCP_PROJECT_ID")

        try:
            convert_fit_to_csv(self.local_fixed_csv_path, self.local_fixed_fit_path, mode='encode')
            upload_to_gcp_bucket(
                self.bucket_name,
                self.gcs_fixed_fit_path,
                self.local_fixed_fit_path,
                "filename",
                user_project=user_project
            )
            logging.info(f"   Success: Re-encoded FIT uploaded to: {self.gcs_fixed_fit_path}")
        except Exception as e4:
            logging.error(f"   Error: Failed to encode CSV to FIT or upload. {e4}")
            raise

    def stage_04_01_email_cleaned_fit(self):
        """
        Generates a download link for the cleaned file and emails it to the user.
        This stage is intended for the 'help_riders' flow.
        """
        if not (self.user_email and self.original_filename):
            logging.warning("   SKIPPED: Emailing, user_email or original_filename not provided.")
            return

        logging.debug(f"📧 Stage 04a: Generating download link and emailing to {self.user_email}")
        try:
            # Create the desired download filename, e.g., "original-ride_clean.fit"
            base_orig_name = os.path.splitext(self.original_filename)[0]
            download_filename = f"{base_orig_name}_clean.fit"

            # Get the service account to impersonate for signing the URL
            impersonate_sa = get_env_and_cashed_it("S_ACCOUNT_RUN")

            # Generate the temporary download link for the file in GCS
            download_link = g_download_link(
                bucket_name=self.bucket_name,
                blob_name=self.gcs_fixed_fit_path,
                download_filename=download_filename,
                impersonate_sa=impersonate_sa
            )

            # Create a unique timestamp to help prevent email trimming
            unique_ts = int(datetime.datetime.now().timestamp())

            # Create the email body and a unique subject
            subject = f"Your Cleaned Activity File is Ready: {self.original_filename}"
            html_body = f"""
            <html>
            <body>
                <!-- Hidden timestamp to prevent Gmail trimming -->
                <span style="display:none;font-size:0;color:transparent;">{unique_ts}</span>

                <h2 style="font-family: Arial, sans-serif;">Your Cleaned File is Ready</h2>
                <p style="font-family: Arial, sans-serif;">The cleaned version of <strong>{self.original_filename}</strong> is ready to be downloaded.</p>
                <p>
                    <a href="{download_link}" style="background-color: #4CAF50; color: white; padding: 14px 25px; text-align: center; text-decoration: none; display: inline-block; border-radius: 8px; font-family: Arial, sans-serif;">
                        Download Cleaned File
                    </a>
                </p>
                <p style="font-family: Arial, sans-serif; font-size: small; color: #555;">Please note: This link will expire in approximately one hour.</p>
                <p style="font-family: Arial, sans-serif;">Happy riding!</p>
            </body>
            </html>
            """

            # Send the email
            send_email(self.user_email, subject, html_body)
            logging.info(f"   Success: Emailed download link to {self.user_email}")

        except Exception as e5:
            logging.error(f"   Error: Failed to send the download link email. {e5}")
            raise

    def stage_05_upload_to_strava(self):
        """
        Uploads the cleaned FIT file to Strava if the environment switch is 'prod'.
        Also updates the activity's gear/bike model.
        """
        logging.debug(f"🚀 Stage 05: Strava Upload")
        current_mode = check_swith_status()
        if current_mode == "prod":
            try:
                access_token = update_strava_token_if_needed()
                upload_id = upload_fit_to_strava(access_token, self.local_fixed_fit_path)
                activity_id = poll_upload_status(upload_id, access_token)
                updated = update_gear(activity_id, access_token, self.bike_model)
                logging.info(f"   Success: Uploaded to Strava (Activity ID: {activity_id}). Gear updated: {updated}")
            except Exception as e6:
                logging.error(f"   Warning: Failed to upload or update Strava activity. {e6}")
        elif current_mode == "testing":
            logging.info(f"   SKIPPED: Uploading to STRAVA because current mode is '{current_mode}'.")
        else:
            logging.error(f"   SKIPPED: Unknown mode '{current_mode}'.")

    def stage_06_fit_to_gpx_and_heatmap(self):
        """
        Converts the fixed FIT to GPX, uploads the GPX to GCS, and updates the heatmap.
        """
        logging.debug(f"🔥 Stage 06: GPX Generation and Heatmap Update")
        try:
            CONVERTER.fit_to_gpx(self.local_fixed_fit_path, self.local_gpx_path)
            upload_to_gcp_bucket(self.bucket_name, self.gcs_gpx_path, self.local_gpx_path, "filename")
            logging.info(f"   Success: Uploaded GPX in GCS: {self.gcs_gpx_path}")

            # Update the heatmap, using the bike model identified in stage 3
            append_gpx_via_compose(self.local_gpx_path, self.bike_model, self.gcs_gpx_path)
            logging.info(f"   Success: Heatmap updated for bike model: {self.bike_model}")
        except Exception as e7:
            logging.error(f"   Error: Failed during GPX generation or heatmap update. {e7}")
            raise

    # -----------------------------------------------------------
    # --- Pipeline Execution Methods ---
    # -----------------------------------------------------------

    def run_full_pipeline(self):
        """
        Executes all six stages of the activity processing pipeline sequentially.
        """
        logging.info("\n\n=== Running main processing pipeline  ===")
        self.stage_01_download_fit("personal")
        self.stage_02_fit_to_unexplored_csv()
        self.stage_03_clean_gps_data()
        self.stage_04_fixed_csv_to_fit("personal")
        # Note: Strava upload depends on bike_model determined in stage 3
        self.stage_05_upload_to_strava()
        # Note: Heatmap depends on bike_model and fixed FIT from stage 4
        self.stage_06_fit_to_gpx_and_heatmap()
        logging.info("\n=== FULL Pipeline Complete ===")

    def run_repair_flow(self):
        """
        Executes a subset of stages: download, decode to csv, fix gps, re-encode to fit,
        and email the result.
        """
        logging.info("\n\n=== Help to some riders to fix his file ===")
        self.stage_01_download_fit("help_riders")
        self.stage_02_fit_to_unexplored_csv()
        self.stage_03_clean_gps_data()
        self.stage_04_fixed_csv_to_fit("help_riders")
        self.stage_04_01_email_cleaned_fit()
        logging.info("\n=== Riders .fit file is repaired and sent ===")


if __name__ == '__main__':
    # Example usage (mocking a blob path)
    # This requires the actual project_env.config and module imports to be configured.

    MOCK_BLOB_PATH = "gs://my-bucket/orig_fit/2025-11-15-103000-mock-ride.fit"

    try:
        # 1. Run the full pipeline
        # full_pipeline = ActivityProcessingPipeline(MOCK_BLOB_PATH, bucket_name)
        # full_pipeline.run_full_pipeline()

        # 2. Run the repair flow
        # repair_flow = ActivityProcessingPipeline(MOCK_BLOB_PATH)
        # repair_flow.run_repair_flow()

        logging.info("\n--- Example Execution Logic ---")
        logging.info("To run, uncomment one of the pipeline executions above.")
        logging.info("Note: This script requires external project modules (config, gcp_actions, strava, etc.) to run successfully.")

    except Exception as e8:
        logging.error(f"\nFATAL ERROR DURING PIPELINE EXECUTION: {e8}")
