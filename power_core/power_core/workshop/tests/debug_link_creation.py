import os
import sys
from gcp_actions.firestore_as_swith import create_download_record
from gcp_actions.client import get_env_and_cashed_it

# Add the project root to the Python path to allow imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

def test_create_link_record():
    """
    Simulates the backend creating a download record.
    This test verifies that the correct bucket and blob name are being written.
    """
    print("--- Running Backend Diagnostic (Part 1) ---")
    try:
        # --- CONFIGURATION ---
        # Manually set the bucket and blob name that we EXPECT to be correct.
        # This should be the bucket where the CLEANED file is.
        output_bucket_name = get_env_and_cashed_it("GCS_PUB_OUTPUT_BUCKET")
        mock_blob_name = "fit_clean/test-file-12345.fit"
        mock_download_filename = "my-test-ride.fit"

        print(f"Attempting to create record with:")
        print(f"  Bucket Name: {output_bucket_name}")
        print(f"  Blob Name:   {mock_blob_name}")
        
        # --- EXECUTION ---
        download_id = create_download_record(
            bucket_name=output_bucket_name,
            blob_name=mock_blob_name,
            download_filename=mock_download_filename,
            expiration_hours=1
        )

        # --- VERIFICATION ---
        print("\n✅ Successfully created Firestore document.")
        print(f"🔥 Download ID: {download_id}")
        print("\n--- ACTION REQUIRED ---")
        print("1. Go to the Google Cloud Console -> Firestore.")
        print(f"2. Open the 'download_links' collection.")
        print(f"3. Find the document with the ID: {download_id}")
        print("4. Verify that the 'bucket_name' field correctly matches your OUTPUT bucket.")
        print("5. Copy the Download ID for Part 2 of the test.")

    except Exception as e:
        print(f"\n❌ ERROR in Backend Diagnostic: {e}")
        print("   This may indicate a problem with Firestore permissions or environment variables.")

if __name__ == "__main__":
    test_create_link_record()
