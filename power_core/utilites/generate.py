import datetime
from gcp_actions.blob_manipulation import get_bucket
import os
from dotenv import load_dotenv

# Cloud Run assets K_SERVICE. If it is not present, is locally env
IS_LOCAL = os.environ.get("K_SERVICE") is None

if IS_LOCAL: # then load .env file
    dotenv_path = os.path.join(os.path.dirname(__file__), "../project_env/keys.env")
    load_dotenv(dotenv_path=dotenv_path, override=False)


def g_download_link(
    bucket_name: str, 
    blob_name: str, 
    expiration_minutes: int = 60,
    download_filename: str | None = None
) -> str:
    """
    Generates a temporary, secure download link for a private file,
    optionally specifying the download filename.
    """
    try:
        bucket = get_bucket(bucket_name)
        blob = bucket.blob(blob_name)

        # Prepare the content disposition header if a filename is provided
        disposition = None
        if download_filename:
            # This tells the browser to download the file with the specified name
            disposition = f'attachment; filename="{download_filename}"'

        signed_url = blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(minutes=expiration_minutes),
            method="GET",
            response_disposition=disposition  # Add the filename hint here
        )
        print(f"✅ Successfully generated signed URL for {blob_name}")
        return signed_url

    except Exception as e:
        print(f"❌ Failed to generate signed URL for {blob_name}: {e}")
    # For simplicity, returning a placeholder. In a real app, you'd want to handle this.
    return "about:blank"

if __name__ == "__main__":
    bb = os.getenv("GCS_PUB_OUTPUT_BUCKET")
    print(bb)
    gs = "gs://finegood-helpers-pure-and-use-w6d2k8/fit_clean/3dbe0914-d332-4865-bd1e-495dbda483db_ffixed.fit"
    print(gs)
    print(g_download_link(bb, gs))
