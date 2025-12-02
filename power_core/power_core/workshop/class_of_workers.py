from fit2gpx import Converter
from gcp_actions.blob_manipulation import upload_to_gcp_bucket, download_from_gcp_bucket
from gcp_actions.client import get_env_and_cashed_it
from gcp_actions.common_utils.timer import time_stage, show_table
from gcp_actions.firestore_as_swith import check_swith_status, create_download_record
from power_core.heatmap_gpx.append_function import append_gpx_via_compose
from power_core.project_env.config import GSC_ORIG_FIT_FOLDER, DONATION_HTML_SNIPPET_MONO, DONATION_HTML_SNIPPET_PRIVAT, FRONTEND_BASE_URL
from power_core.strava.auth import update_strava_token_if_needed
from power_core.strava.upload import upload_fit_to_strava, poll_upload_status, update_gear
from power_core.utilites.email_sender import send_email
from power_core.workshop.instruments import convert_fit_to_csv, cleaner_run, load_email_template
import datetime
import logging
import os


logger = logging.getLogger(__name__)

# Initialize global dependencies
CONVERTER = Converter()


class ActivityProcessingPipeline:
    """
    A class to manage the multi-stage processing of a .FIT activity file,
    including download, GPS cleaning, re-encoding, and upload to Strava/Heatmap.
    Error Handling: by timer.py
    """
    def __init__(
            self,
            blob_path: str,
            bucket_name: str,
            bucket_name_output: str | None = None,
            user_email: str | None = None,
            original_filename: str | None = None,
            locale: str = 'en'
    ):
        """
        Initializes the pipeline with the source GCS blob path and sets up local paths.
        Args:
            blob_path: The full GCS path of the original .FIT file
                       (e.g., gs://bucket/path/to/file.fit).
            locale: The user's language preference (e.g., 'en', 'uk'). Defaults to 'en'.
        """
        self.bad_lines = None
        self.path_to_buckets = None
        self.user_email = user_email
        self.original_filename = original_filename
        self.bucket_name_output = bucket_name_output
        self.bucket_name = bucket_name
        self.blob_path = blob_path
        self.locale = locale
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

        logger.debug(f"Pipeline initialized for activity: {self.filename}")

    def stage_01_download_fit(self, mode: str ):
        """
        Downloads the original .FIT file from GCS to the local temporary directory.
        """
        user_project = None
        if mode == "personal":
            self.path_to_buckets = self.gcs_orig_path
        elif mode == "help_riders":
            self.path_to_buckets = self.blob_path
            user_project = get_env_and_cashed_it("GCP_PROJECT_ID")

        logger.debug(f"🌍 Stage 01: Downloading FIT from GCS: {self.path_to_buckets}")
        download_from_gcp_bucket(
            self.bucket_name,
            self.path_to_buckets,
            self.local_fit_path,
            "blob",
            user_project=user_project
        )
        logger.debug(f"Success: .fit downloaded to VM at: {self.local_fit_path}")

    def stage_02_fit_to_unexplored_csv(self):
        """
        Converts the local .FIT file to an 'unexplored' CSV for processing.
        """
        convert_fit_to_csv(self.local_fit_path, self.local_unexplored_csv_path, mode='decode')
        logger.debug("FIT decoded to CSV.")
        logger.debug("Skipped saving the unexplored CSV.")


    def stage_03_clean_gps_data(self, pipeline: str):
        """
        Cleans the unexplored CSV, fixes GPS problems, stores a bike model,
        and uploads the fixed CSV to GCS.
        """
        self.bike_model, self.bad_lines = cleaner_run(self.local_unexplored_csv_path, self.local_fixed_csv_path, pipeline)

        if self.bad_lines > 0 or pipeline == "private":
            upload_to_gcp_bucket(self.bucket_name, self.gcs_fixed_csv_path, self.local_fixed_csv_path, "filename")
            logger.info(f"GPS cleaned (Bike Model: {self.bike_model}).")
            logger.debug(f"Uploaded fixed CSV to: {self.gcs_fixed_csv_path}")
        elif self.bad_lines == 0 and pipeline == "public":
            logger.info(f"However, there zero issues")
            pass

        return self.bad_lines

    def stage_04_fixed_csv_to_fit(self, mode: str ):
        """
        Re-encodes the fixed CSV back into a clean .FIT file and uploads it to GCS.
        """
        user_project = None
        upload_bucket = self.bucket_name_output if mode == "help_riders" else self.bucket_name

        if mode == "help_riders":
            user_project = get_env_and_cashed_it("GCP_PROJECT_ID")

        convert_fit_to_csv(self.local_fixed_csv_path, self.local_fixed_fit_path, mode='encode')
        upload_to_gcp_bucket(
            upload_bucket,
            self.gcs_fixed_fit_path,
            self.local_fixed_fit_path,
            "filename",
            user_project=user_project
        )
        logger.debug(f"Re-encoded FIT uploaded to: {upload_bucket}/{self.gcs_fixed_fit_path}")

    def stage_04_01_email_cleaned_fit(self, result: str):
        """
        Generates a proxy download link and emails it to the user.
        """
        if not (self.user_email and self.original_filename):
            logger.warning("Emailing skipped: user_email or original_filename not provided.")
            return

        unique_ts = int(datetime.datetime.now().timestamp())
        download_link = None
        email_context = {}

        # Load templates from files
        try:
            subject_template, body_template = load_email_template(self.locale, result)
        except Exception as e:
            logger.error(f"Failed to load email templates for locale '{self.locale}' and result '{result}': {e}")
            return

        subject = subject_template.format(original_filename=self.original_filename)

        if result == "find":
            logger.debug(f"Stage 04a: Generating download link and emailing to {self.user_email} in locale '{self.locale}'")
            base_orig_name = os.path.splitext(self.original_filename)[0]
            download_filename = f"{base_orig_name}_clean.fit"

            # Create a record in Firestore for the download
            try:
                download_id = create_download_record(
                    bucket_name=self.bucket_name_output,
                    blob_name=self.gcs_fixed_fit_path,
                    download_filename=download_filename,
                    expiration_hours=1
                )
                if not download_id:
                    logger.error(
                        f"Failed to create download record for GCS path: {self.gcs_fixed_fit_path}. Emailing 'find' result skipped.")
                    return

                # Construct the proxy URL
                download_link = f"{FRONTEND_BASE_URL}/download/{download_id}"
            except Exception as e:
                logger.error(
                    f"Error creating download record for {self.gcs_fixed_fit_path}: {e}. Emailing 'find' result skipped.")
                return
        elif result == "not_found":
            logger.debug(f"Stage 04a: Preparing 'not found' email to {self.user_email}.")

        else:
            logger.warning(f"Unknown result type '{result}'. Emailing skipped.")
            return
        # 4. --- Prepare Email Context and Body ---
        email_context = {
            "unique_ts": unique_ts,
            "original_filename": self.original_filename,
            "bad_lines": self.bad_lines,
            "download_link": download_link,  # Will be None if a result is 'not_found'
            "donation_section_mono": DONATION_HTML_SNIPPET_MONO,
            "donation_section_privat": DONATION_HTML_SNIPPET_PRIVAT
            }
        try:
            html_body = body_template.format(**email_context)
        except KeyError as e:
            logger.error(f"Template formatting failed. Missing key in context: {e}.")
            return
        # 5. --- Send Email with Error Handling ---
        try:
            send_email(self.user_email, subject, html_body)
            # the result is either "found" or "not_found"
            logger.debug(f"Successfully sent email for result '{result}' to {self.user_email}.")
        except Exception as e:
            logger.error(f"Failed to send email to {self.user_email} for result '{result}': {e}")


    def stage_05_upload_to_strava(self):
        """
        Uploads the cleaned FIT file to Strava if the environment switch is 'prod'.
        Also updates the activity's gear/bike model.
        """
        current_mode = check_swith_status()
        if current_mode == "prod":
            access_token = update_strava_token_if_needed()
            upload_id = upload_fit_to_strava(access_token, self.local_fixed_fit_path)
            activity_id = poll_upload_status(upload_id, access_token)
            updated = update_gear(activity_id, access_token, self.bike_model)
            logger.info(f"Uploaded to Strava (Activity ID: {activity_id}). Gear updated: {updated}")
        elif current_mode == "testing":
            logger.warning(f"Not uploading to STRAVA because current mode is '{current_mode}'.")
        else:
            logger.error(f"   SKIPPED: Unknown mode '{current_mode}'.")

    def stage_06_fit_to_gpx_and_heatmap(self):
        """
        Converts the fixed FIT to GPX, uploads the GPX to GCS, and updates the heatmap.
        """
        CONVERTER.fit_to_gpx(self.local_fixed_fit_path, self.local_gpx_path)
        upload_to_gcp_bucket(self.bucket_name, self.gcs_gpx_path, self.local_gpx_path, "filename")

        # Update the heatmap, using the bike model identified in stage 3
        append_gpx_via_compose(self.local_gpx_path, self.bike_model, self.gcs_gpx_path)
        logger.debug(f"Heatmap updated for bike model: {self.bike_model}")

    # -----------------------------------------------------------
    # --- Pipeline Execution Styles ---
    # -----------------------------------------------------------

    def run_full_pipeline(self):
        """
        Executes all six stages of the activity processing pipeline sequentially.
        """
        logger.info("Private pipeline running")
        all_stage_times = {}

        with time_stage("Stage 01_download_fit", all_stage_times):
            self.stage_01_download_fit("personal")

        with time_stage("Stage 02_fit_to_unexplored_csv", all_stage_times):
            self.stage_02_fit_to_unexplored_csv()

        with time_stage("Stage 03_clean_gps_data", all_stage_times):
            self.stage_03_clean_gps_data("private")

        with time_stage("Stage 04_fixed_csv_to_fit", all_stage_times):
            self.stage_04_fixed_csv_to_fit("personal")

        with time_stage("Stage 05_upload_to_strava", all_stage_times):
            self.stage_05_upload_to_strava()

        with time_stage("Stage 06_fit_to_gpx_and_heatmap", all_stage_times):
            self.stage_06_fit_to_gpx_and_heatmap()

        # Calculate the total time
        show_table(all_stage_times, "Private")


    def run_repair_flow(self):
        """
        For usage by the Frontend.
        Executes a subset of stages: download, decode to csv, fix gps, re-encode to fit,
        and email the result.
        """
        logger.info("Public pipeline started")
        all_stage_times = {}
        with time_stage("Stage 01_download_fit", all_stage_times):
            self.stage_01_download_fit("help_riders")

        with time_stage("Stage 02_fit_to_unexplored_csv", all_stage_times):
            self.stage_02_fit_to_unexplored_csv()

        with time_stage("Stage 03_clean_gps_data", all_stage_times):
            branching = self.stage_03_clean_gps_data("public")
        if branching > 0:

            with time_stage("Stage 04_fixed_csv_to_fit", all_stage_times):
                self.stage_04_fixed_csv_to_fit("help_riders")

            with time_stage("Stage_04_01_email_cleaned_fit", all_stage_times):
                self.stage_04_01_email_cleaned_fit("find")

        elif branching == 0:
            with time_stage("Stage_04_01_email_cleaned_fit", all_stage_times):
                self.stage_04_01_email_cleaned_fit("not_found")
            pass

        # Calculate the total time
        show_table(all_stage_times, "Public")

# if __name__ == '__main__':
    # Example usage (mocking a blob path)
    # This requires the actual project_env.config and module imports to be configured.
    # from gcp_actions.common_utils.init_config import load_and_inject_config
    # from gcp_actions.common_utils.handle_logs import run_handle_logs
    # import logging
    # import sys
    # from power_core.project_env.config import GCS_BUCKET_NAME
    # os.environ['LOGGING_LEVEL'] = 'DEBUG'
    # try:
    #     list_of_secret_env_vars = ["APP_JSON_KEYS", "SEC_DROPBOX"]
    #     list_of_sa_env_vars = [None, "S_ACCOUNT_DROPBOX"]
    #     load_and_inject_config(list_of_secret_env_vars, list_of_sa_env_vars)
    #     logger.debug("Configuration loaded successfully.")
    # except Exception as e:
    #     logger.critical(f"FATAL ERROR: Could not load configuration. {e}")
    #     sys.exit(1)
    #
    # run_handle_logs()
    # logger = logging.getLogger(__name__)
    #
    #
    # MOCK_BLOB_PATH = f"gs://{GCS_BUCKET_NAME}/test_data/problem_fit with space-ROAM238-10_2025-09-22.fit"
    #
    # try:
    #     # 1. Run the full pipeline
    #     full_pipeline = ActivityProcessingPipeline(MOCK_BLOB_PATH, GCS_BUCKET_NAME)
    #     full_pipeline.run_full_pipeline()
    #
    #     # 2. Run the repair flow
    #     # repair_flow = ActivityProcessingPipeline(MOCK_BLOB_PATH)
    #     # repair_flow.run_repair_flow()
    #
    #     logger.info("\n--- Example Execution Logic ---")
    #     logger.info("To run, uncomment one of the pipeline executions above.")
    #     logger.info("Note: This script requires external project modules (config, gcp_actions, strava, etc.) to run successfully.")
    #
    # except Exception as e8:
    #     logger.error(f"\nFATAL ERROR DURING PIPELINE EXECUTION: {e8}")
