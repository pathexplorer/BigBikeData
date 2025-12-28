from fit2gpx import Converter
from gcp_actions.blob_manipulation import StorageManipulations
from gcp_actions.common_utils.timer import time_stage, log_duration_table
from power_core.dropbox_usage.utils import DropboxAuth
from power_core.heatmap_gpx.append_function import append_gpx_via_compose
from power_core.project_env.config import GCS_BUCKET_NAME, GCS_PUB_OUTPUT_BUCKET
from power_core.strava.auth import update_strava_token_if_needed
from power_core.strava.upload import StravaUpload
from power_core.workshop.instruments import convert_fit_to_csv, cleaner_run, write_email_with_link
from typing import Literal
import logging, os, uuid

logger = logging.getLogger(__name__)


CONVERTER = Converter()

class ActivityProcessingPipeline:
    """
    A class to manage the multi-stage processing of a .FIT activity file.
    Can be triggered from GCS, an HTTP request with file data, or a Pub/Sub message with a Dropbox path.
    """
    type Locale = Literal["en", "uk"]
    def __init__(
            self,
            original_filename: str,
            locale: Locale = 'en',
            user_email: str | None = None,
            file_data: bytes | None = None,
            dropbox_path: str | None = None,
            pipeline_type: str | None = None
    ):
        """
        Initializes the pipeline with the source GCS blob path or direct file data.
        :param file_data: Raw bytes of the file, if not downloading from GCS.
        :param locale: The user's language preference
        :param pipeline_type: runs one from two styles of a pipeline
        """

        self.bucket_name = GCS_BUCKET_NAME
        self.bucket_name_output = GCS_PUB_OUTPUT_BUCKET
        self.user_email = user_email
        self.original_filename = original_filename

        self.locale = locale
        self.file_data = file_data
        self.dropbox_path = dropbox_path
        self.pipeline_type = pipeline_type

        # --- Filename Generation Strategy ---
        if self.pipeline_type == 'private':
            # For the private pipeline, use the original filename, replacing spaces.
            safe_filename = self.original_filename.replace(' ', '_')
            self.filename = safe_filename
            self.base_name, _ = os.path.splitext(safe_filename)
        else:
            # For the public pipeline, use a unique ID to ensure no collisions.
            self._unique_prefix = str(uuid.uuid4())
            _, ext = os.path.splitext(self.original_filename)
            allowed_exts = {'.fit', '.csv'}
            if ext.lower() not in allowed_exts:
                ext = '.fit'
            self.filename = f"{self._unique_prefix}{ext}"
            self.base_name = self._unique_prefix

        self.bad_lines = None
        self.bike_model = None

        # Local temporary file paths are now based on the chosen filename
        os.makedirs("/tmp", exist_ok=True)
        self.local_fit_path = f"/tmp/{self.filename}"
        self.local_unexplored_csv_path = f"/tmp/{self.base_name}.csv"
        self.local_fixed_csv_path = f"/tmp/{self.base_name}_fixed.csv"
        self.local_fixed_fit_path = f"/tmp/{self.base_name}_cleaned.fit"
        self.local_gpx_path = f"/tmp/{self.base_name}.gpx"

        # GCS upload paths
        self.gcs_fixed_csv_path = f"csv_clean/{os.path.basename(self.local_fixed_csv_path)}"
        self.gcs_fixed_fit_path = f"fit_clean/{os.path.basename(self.local_fixed_fit_path)}"
        self.gcs_gpx_path = f"gpx/{os.path.basename(self.local_gpx_path)}"

        logger.info(f"Pipeline initialized for activity '{self.filename}' (Type: {self.pipeline_type})")


    def stage_01_download_fit(self):
        """
        Downloads the original .FIT file from Dropbox
        or writes it from memory if file_data is present.
        """
        # --- Private Pipeline
        if self.dropbox_path:
            logger.debug(f"Stage 1: Downloading FIT from Dropbox: {self.dropbox_path}")
            try:
                da = DropboxAuth()
                dbx = da.auth_dropbox()
                dbx.files_download_to_file(self.local_fit_path, self.dropbox_path)
                logger.debug(f"Success: .fit downloaded from Dropbox to VM at: {self.local_fit_path}")
            except Exception as e:
                logger.error(f"Failed to download from Dropbox: {e}")
                raise
            return

        # ---- Public Pipeline
        if self.file_data:
            logger.debug(f"Stage 1: Writing FIT from memory to: {self.local_fit_path}")
            with open(self.local_fit_path, 'wb') as f:
                f.write(self.file_data)
            logger.debug(f"Success: .fit written to VM at: {self.local_fit_path}")
            return

        logger.debug(f"Success: .fit downloaded to VM at: {self.local_fit_path}")

    def stage_02_fit_to_unexplored_csv(self):
        """
        Converts the local .FIT file to an 'unexplored' CSV for processing.
        """
        convert_fit_to_csv(self.local_fit_path, self.local_unexplored_csv_path, mode='decode')
        logger.debug("FIT decoded to CSV.")
        logger.debug("Skipped saving the unexplored CSV.")


    def stage_03_clean_gps_data(self):
        """
        Cleans the unexplored CSV, fixes GPS problems, stores a bike model,
        and uploads the fixed CSV to GCS.
        """
        self.bike_model, self.bad_lines = cleaner_run(
            self.local_unexplored_csv_path,
            self.local_fixed_csv_path,
            self.pipeline_type
        )
        if self.bad_lines > 0 or self.pipeline_type == "private":
            up_csv = StorageManipulations(
                self.bucket_name,
                self.gcs_fixed_csv_path,
                self.local_fixed_csv_path)
            up_csv.upload_to_gcp_bucket("filename")

            logger.info(f"GPS cleaned (Bike Model: {self.bike_model}).")
            logger.debug(f"Uploaded fixed CSV to: {self.gcs_fixed_csv_path}")
        elif self.bad_lines == 0 and self.pipeline_type == "public":
            logger.info("No GPS issues found, skipping fixed CSV upload.")
        return self.bad_lines

    def stage_04_fixed_csv_to_fit(self):
        """
        Re-encodes the fixed CSV back into a clean .FIT file and uploads it to GCS.
        """
        upload_bucket = self.bucket_name_output if self.pipeline_type == "public" else self.bucket_name

        convert_fit_to_csv(
            self.local_fixed_csv_path,
            self.local_fixed_fit_path,
            mode='encode'
        )
        up_fit = StorageManipulations(
            upload_bucket,
            self.gcs_fixed_fit_path,
            self.local_fixed_fit_path,
        )
        up_fit.upload_to_gcp_bucket("filename")
        logger.debug(f"Re-encoded FIT uploaded to: {upload_bucket}/{self.gcs_fixed_fit_path}")

    def stage_04_01_email_cleaned_fit(self, result: str):
        """ Generates a proxy download link and emails it to the user."""
        write_email_with_link(
            self.locale,
            result,
            self.original_filename,
            self.bucket_name_output,
            self.gcs_fixed_fit_path,
            self.bad_lines,
            self.user_email
        )

    def stage_05_upload_to_strava(self):
        """
        Uploads the cleaned FIT file to Strava if the environment switch is 'prod'.
        Also updates the activity's gear/bike model.
        """
        current_mode = os.environ.get("STRAVA_UPLOAD")
        if current_mode == "enable":
            access_token = update_strava_token_if_needed()
            su = StravaUpload(
                access_token,
                self.local_fixed_fit_path,
                self.bike_model
            )
            updated, activity_id = su.upload_activity()
            logger.info(f"Uploaded to Strava (Activity ID: {activity_id}). Gear updated: {updated}")
        elif current_mode == "disable":
            logger.warning(f"Not uploading to STRAVA because current mode is '{current_mode}'.")
        else:
            logger.warning(f"STRAVA UPLOAD SKIPPED: Mode is '{current_mode}'.")

    def stage_06_fit_to_gpx(self):
        """ Converts the fixed FIT to GPX and uploads it to GCS."""
        CONVERTER.fit_to_gpx(
            self.local_fixed_fit_path,
            self.local_gpx_path
        )

        # Storage Audit: for appending by compose method
        up_gpx = StorageManipulations(
            self.bucket_name,
            self.gcs_gpx_path,
            self.local_gpx_path,
        )
        up_gpx.upload_to_gcp_bucket("filename")

    def stage_07_heatmap(self):
        """ Updates the heatmap using the bike model identified in stage 3."""
        append_gpx_via_compose(self.local_gpx_path, self.bike_model, self.gcs_gpx_path)
        logger.debug(f"Heatmap updated for bike model: {self.bike_model}")

    def run_full_pipeline(self):
        """ Executes all stages of the private activity processing pipeline."""
        logger.info("Private pipeline running")
        all_stage_times = {}
        with time_stage("1 Download FIT", all_stage_times):
            self.stage_01_download_fit()
        with time_stage("2 FIT to CSV", all_stage_times):
            self.stage_02_fit_to_unexplored_csv()
        with time_stage("3 Clean GPS data", all_stage_times):
            self.stage_03_clean_gps_data()
        with time_stage("4 CSV to FIT", all_stage_times):
            self.stage_04_fixed_csv_to_fit()
        with time_stage("5 Upload to Strava", all_stage_times):
            self.stage_05_upload_to_strava()
        with time_stage("6 FIT to GPX", all_stage_times):
            self.stage_06_fit_to_gpx()
        with time_stage("7 Append to Heatmap", all_stage_times):
            self.stage_07_heatmap()
        log_duration_table(all_stage_times, "Private")

    def run_repair_flow(self):
        """ Executes the public-facing repair flow for users."""
        logger.info("Public pipeline started")
        all_stage_times = {}
        with time_stage("1 Download FIT", all_stage_times):
            self.stage_01_download_fit()
        with time_stage("2 FIT to CSV", all_stage_times):
            self.stage_02_fit_to_unexplored_csv()
        with time_stage("3 Clean GPS data", all_stage_times):
            branching = self.stage_03_clean_gps_data()
        with time_stage("4 CSV to FIT", all_stage_times):
            self.stage_04_fixed_csv_to_fit()
        if branching > 0:
            with time_stage("4-a Send results in email", all_stage_times):
                self.stage_04_01_email_cleaned_fit("find")
        else:
            with time_stage("4-b Send info email", all_stage_times):
                self.stage_04_01_email_cleaned_fit("not_found")
        log_duration_table(all_stage_times, "Public")
