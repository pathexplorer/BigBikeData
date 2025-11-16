import os
import warnings
from fit2gpx import Converter
from datetime import datetime, timezone

# --- External Dependencies (Assumed to be available in project_env) ---
# NOTE: These are imported globally as they were in the original script.
from project_env import config
from gcp_actions.blob_manipulation import upload_to_gcp_bucket, download_from_gcp_bucket
from gcp_actions.firestore_as_swith import check_swith_status
from strava.upload import upload_fit_to_strava, poll_upload_status, update_gear
from strava.auth import update_strava_token_if_needed
from heatmap_gpx.append_function import append_gpx_via_compose
from workshop.instruments import convert_fit_to_csv, clean_gps

# Initialize global dependencies
warnings.filterwarnings("ignore", category=UserWarning) # For ignoring warnings from fit2gpx
CONVERTER = Converter()


class ActivityProcessingPipeline:
    """
    A class to manage the multi-stage processing of a .FIT activity file,
    including download, GPS cleaning, re-encoding, and upload to Strava/Heatmap.
    """
    def __init__(self, blob_path: str, bucket_name: str):
        """
        Initializes the pipeline with the source GCS blob path and sets up local paths.

        Args:
            blob_path: The full GCS path of the original .FIT file
                       (e.g., gs://bucket/path/to/file.fit).
        """
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
        self.local_fixed_fit_path = f"/tmp/{self.base_name}_ffixed.fit"
        self.local_gpx_path = f"/tmp/{self.base_name}.gpx"

        # GCS upload paths
        self.gcs_orig_path = f"{config.GSC_ORIG_FIT_FOLDER}/{self.filename}"
        self.gcs_fixed_csv_path = f"csv_clean/{os.path.basename(self.local_fixed_csv_path)}"
        self.gcs_fixed_fit_path = f"fit_clean/{os.path.basename(self.local_fixed_fit_path)}"
        self.gcs_gpx_path = f"gpx/{os.path.basename(self.local_gpx_path)}"

        print(f"Pipeline initialized for activity: {self.filename}")
        print("-" * 40)

    def stage_01_download_fit(self):
        """
        Downloads the original .FIT file from GCS to the local temporary directory.
        """
        print(f"🌍 Stage 01: Downloading FIT from GCS: {self.gcs_orig_path}")
        try:
            download_from_gcp_bucket(self.bucket_name, self.gcs_orig_path, self.local_fit_path, "blob")
            print(f"   Success: .fit downloaded to VM at: {self.local_fit_path}")
        except Exception as e:
            print(f"   Error: Failed to download FIT. {e}")
            raise

    def stage_02_fit_to_unexplored_csv(self):
        """
        Converts the local .FIT file to an 'unexplored' CSV for processing.
        """
        print(f"📊 Stage 02: Decoding FIT to CSV")
        try:
            convert_fit_to_csv(self.local_fit_path, self.local_unexplored_csv_path, mode='decode')
            print("   Success: FIT decoded to CSV. Skipped saving the unexplored CSV.")
        except Exception as e:
            print(f"   Error: Failed to decode FIT to CSV. {e}")
            raise

    def stage_03_clean_gps_data(self):
        """
        Cleans the unexplored CSV, fixes GPS problems, stores bike model,
        and uploads the fixed CSV to GCS.
        """
        print(f"🧹 Stage 03: Cleaning GPS data and uploading fixed CSV")
        try:
            self.bike_model = clean_gps(self.local_unexplored_csv_path, self.local_fixed_csv_path)
            upload_to_gcp_bucket(self.bucket_name, self.gcs_fixed_csv_path, self.local_fixed_csv_path, "filename")
            print(f"   Success: GPS cleaned (Bike Model: {self.bike_model}).")
            print(f"   Uploaded fixed CSV to: {self.gcs_fixed_csv_path}")
        except Exception as e:
            print(f"   Error: Failed during GPS cleaning or CSV upload. {e}")
            raise

    def stage_04_fixed_csv_to_fit(self):
        """
        Re-encodes the fixed CSV back into a clean .FIT file and uploads it to GCS.
        """
        print(f"🔄 Stage 04: Encoding fixed CSV back to FIT and uploading")
        try:
            convert_fit_to_csv(self.local_fixed_csv_path, self.local_fixed_fit_path, mode='encode')
            upload_to_gcp_bucket(self.bucket_name, self.gcs_fixed_fit_path, self.local_fixed_fit_path, "filename")
            print(f"   Success: Re-encoded FIT uploaded to: {self.gcs_fixed_fit_path}")
        except Exception as e:
            print(f"   Error: Failed to encode CSV to FIT or upload. {e}")
            raise

    def stage_05_upload_to_strava(self):
        """
        Uploads the cleaned FIT file to Strava if the environment switch is 'prod'.
        Also updates the activity's gear/bike model.
        """
        print(f"🚀 Stage 05: Strava Upload")
        current_mode = check_swith_status()
        if current_mode == "prod":
            try:
                access_token = update_strava_token_if_needed()
                upload_id = upload_fit_to_strava(access_token, self.local_fixed_fit_path)
                activity_id = poll_upload_status(upload_id, access_token)
                updated = update_gear(activity_id, access_token, self.bike_model)
                print(f"   Success: Uploaded to Strava (Activity ID: {activity_id}). Gear updated: {updated}")
            except Exception as e:
                print(f"   Warning: Failed to upload or update Strava activity. {e}")
        elif current_mode == "testing":
            print(f"   SKIPPED: Uploading to STRAVA because current mode is '{current_mode}'.")
        else:
            print(f"   SKIPPED: Unknown mode '{current_mode}'.")

    def stage_06_fit_to_gpx_and_heatmap(self):
        """
        Converts the fixed FIT to GPX, uploads the GPX to GCS, and updates the heatmap.
        """
        print(f"🔥 Stage 06: GPX Generation and Heatmap Update")
        try:
            CONVERTER.fit_to_gpx(self.local_fixed_fit_path, self.local_gpx_path)
            upload_to_gcp_bucket(self.bucket_name, self.gcs_gpx_path, self.local_gpx_path, "filename")
            print(f"   Success: Uploaded GPX in GCS: {self.gcs_gpx_path}")

            # Update the heatmap, using the bike model identified in stage 3
            append_gpx_via_compose(self.local_gpx_path, self.bike_model, self.gcs_gpx_path)
            print(f"   Success: Heatmap updated for bike model: {self.bike_model}")
        except Exception as e:
            print(f"   Error: Failed during GPX generation or heatmap update. {e}")
            raise

    # -----------------------------------------------------------
    # --- Pipeline Execution Methods ---
    # -----------------------------------------------------------

    def run_full_pipeline(self):
        """
        Executes all six stages of the activity processing pipeline sequentially.
        """
        print("\n\n=== Running FULL Activity Processing Pipeline ===")
        self.stage_01_download_fit()
        self.stage_02_fit_to_unexplored_csv()
        self.stage_03_clean_gps_data()
        self.stage_04_fixed_csv_to_fit()
        # Note: Strava upload depends on bike_model determined in stage 3
        self.stage_05_upload_to_strava()
        # Note: Heatmap depends on bike_model and fixed FIT from stage 4
        self.stage_06_fit_to_gpx_and_heatmap()
        print("\n=== FULL Pipeline Complete ===")

    def run_repair_flow(self):
        """
        Executes a subset of stages: download, decode to csv, fix gps, and re-encode to fit.
        This is useful for cleaning and repairing problematic FIT files before final upload/processing.
        (Stages 1, 2, 3, 4)
        """
        print("\n\n=== Running REPAIR (Clean & Re-encode) Flow ===")
        self.stage_01_download_fit()
        self.stage_02_fit_to_unexplored_csv()
        self.stage_03_clean_gps_data()
        self.stage_04_fixed_csv_to_fit()
        print("\n=== REPAIR Flow Complete ===")


if __name__ == '__main__':
    # Example usage (mocking a blob path)
    # This requires the actual project_env.config and module imports to be configured.

    MOCK_BLOB_PATH = "gs://my-bucket/orig_fit/2025-11-15-103000-elemnt-mock-ride.fit"

    try:
        # 1. Run the full pipeline
        # full_pipeline = ActivityProcessingPipeline(MOCK_BLOB_PATH, bucketname)
        # full_pipeline.run_full_pipeline()

        # 2. Run the repair flow
        # repair_flow = ActivityProcessingPipeline(MOCK_BLOB_PATH)
        # repair_flow.run_repair_flow()

        print("\n--- Example Execution Logic ---")
        print("To run, uncomment one of the pipeline executions above.")
        print("Note: This script requires external project modules (config, gcp_actions, strava, etc.) to run successfully.")

    except Exception as e:
        print(f"\nFATAL ERROR DURING PIPELINE EXECUTION: {e}")