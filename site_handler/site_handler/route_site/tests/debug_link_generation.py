import os
import sys
from gcp_actions.client import get_any_client, get_env_and_cashed_it
from gcp_actions.common_utils.generate import g_download_link
from urllib.parse import urlparse

# Add the project root to the Python path to allow imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

def test_generate_signed_url():
    """
    Simulates the frontend reading a record and generating a signed URL.
    This test will verify if the service has the correct permissions.
    """
    print("\n--- Running Frontend Diagnostic (Part 2) ---")
    
    # --- CONFIGURATION ---
    # PASTE THE DOWNLOAD ID you got from running Part 1 of the test.
    download_id = input("Please enter the Download ID from Part 1: ").strip()

    if not download_id:
        print("No Download ID provided. Exiting.")
        return

    try:
        # --- EXECUTION ---
        print(f"\nAttempting to read Firestore document: {download_id}")
        db = get_any_client("firestore")
        doc_ref = db.collection("download_links").document(download_id)
        doc = doc_ref.get()

        if not doc.exists:
            print(f"❌ ERROR: Document '{download_id}' not found in Firestore.")
            return

        data = doc.to_dict()
        bucket_name = data.get('bucket_name')
        blob_name = data.get('blob_name')
        
        print("Successfully read data from Firestore:")
        print(f"  Bucket Name: {bucket_name}")
        print(f"  Blob Name:   {blob_name}")

        print("\nNow, attempting to generate the signed URL by impersonating S_ACCOUNT_RUN...")
        impersonate_sa = get_env_and_cashed_it("S_ACCOUNT_RUN")
        
        signed_url = g_download_link(
            bucket_name=bucket_name,
            blob_name=blob_name,
            download_filename="test.fit",
            expiration_minutes=1,
            impersonate_sa=impersonate_sa
        )

        # --- VERIFICATION ---
        print("\n✅ Successfully generated a signed URL!")
        print(signed_url)

        parsed_url = urlparse(signed_url)
        hostname = parsed_url.hostname or ''
        if hostname == "storage.googleapis.com" or hostname.endswith(".storage.googleapis.com"):
            print("\n🔥 DIAGNOSIS: SUCCESS! The URL is a valid GCS link.")
            print("   This means your permissions and code are correct.")
            print("   The problem may lie elsewhere in the data being passed in production.")
        else:
            print("\n❌ DIAGNOSIS: FAILURE! The generated URL is NOT a valid GCS link.")
            print("   This strongly indicates a PERMISSIONS issue.")
            print("   The service account being impersonated likely lacks permissions on the OUTPUT bucket.")

    except Exception as e:
        print(f"\n❌ An unexpected error occurred: {e}")
        print("\n❌ DIAGNOSIS: FAILURE! An exception occurred during the process.")
        print("   This could be due to Firestore permissions, environment variables, or a code error.")


if __name__ == "__main__":
    test_generate_signed_url()
