import os
from google.cloud import secretmanager
import logging

logging.basicConfig(level=logging.INFO)

#--- Local part STARTS --- testing only
#from dotenv import load_dotenv
#load_dotenv(dotenv_path="other/keys.env")
#os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "other/a.json"
#--- Local part ENDS ---

SECRET_DROPBOX_APP_SECRET = "dropbox-app-secret"
SECRET_DROPBOX_REFRESH_TOKEN = "dropbox-refresh-token"

def checking_env():
    required_vars = [
        "DROPBOX_APP_KEY",
        "GCP_PROJECT_ID",
        "GCS_BUCKET_NAME"
    ]

    for var in required_vars:
        value = os.environ.get(var)
        if not value:
            raise EnvironmentError(f"Environment variable {var} is not set")
        logging.info(f"{var} starts from: {value[:4]}...")

    logging.info(f"Checking the availability of secrets in Secret Manager")
    project_id = os.environ.get("GCP_PROJECT_ID")
    secret_client = secretmanager.SecretManagerServiceClient()

    for secret_env_var in [SECRET_DROPBOX_APP_SECRET, SECRET_DROPBOX_REFRESH_TOKEN]:
        secret_id = secret_env_var
        secret_path = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
        try:
            response = secret_client.access_secret_version(request={"name": secret_path})
            secret_value = response.payload.data.decode("UTF-8").strip()
            logging.info(f"The secret {secret_id} is available, starts from з: {secret_value[:4]}...")
        except Exception as e:
            raise RuntimeError(f"Failed to get the secret {secret_id}: {e}")
