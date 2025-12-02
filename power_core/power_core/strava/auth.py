"""
Running before a Fit file will be uploaded to strava
"""
import time, os, requests
from gcp_actions.secret_manager import SecretManagerClient
import logging
from power_core.project_env.config import (
    STRAVA_APP_ID,
    STRAVA_CLIENT_SECRET,
    STRAVA_ACCESS_TOKEN,
    STRAVA_REFRESH_TOKEN,
    EXPIRES_AT,
    GCP_PROJECT_ID,
    s_email_dropbox,
    SEC_DROPBOX
)

logger = logging.getLogger(__name__)

def update_strava_token_if_needed():
    """
    Get a new access token because it usually already expired (valid only 6 hours)
    Refresh token is persistent and doesn't need to periodically renew
    :return:  a new access token
    """

    client_id = STRAVA_APP_ID
    client_secret = STRAVA_CLIENT_SECRET
    refresh_token = STRAVA_REFRESH_TOKEN
    expires_at = int(EXPIRES_AT)  # stored as a Unix timestamp
    now = int(time.time())
    if now < expires_at - 300:  # 5-minute buffer
        return STRAVA_ACCESS_TOKEN

    # Token is expiring, updating
    url = "https://www.strava.com/oauth/token"
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }

    try:
        response = requests.post(url, data=data)
        response.raise_for_status()
        new_token_data = response.json()

        new_access_token = new_token_data["access_token"]
        new_expires_at = str(new_token_data["expires_at"])
        new_refresh_token = new_token_data["refresh_token"]

        # 4. Update the environment for the CURRENT running process
        os.environ['STRAVA_ACCESS_TOKEN'] = new_access_token
        os.environ['EXPIRES_AT'] = new_expires_at
        if new_refresh_token != refresh_token:
            os.environ['STRAVA_REFRESH_TOKEN'] = new_refresh_token

        logger.warning("Successfully updated Strava tokens in the current environment.")

        # 5. Persist the updated tokens back to Secret Manager
        # Initialize the client "just-in-time" for the write operation.
        sm = SecretManagerClient(GCP_PROJECT_ID, s_email_dropbox)
        secret_name = SEC_DROPBOX

        # Get the full, most recent secret dictionary to avoid race conditions
        secrets_dict = sm.get_secret_json(secret_name)

        # Update the dictionary with the new values
        secrets_dict["STRAVA_ACCESS_TOKEN"] = new_access_token
        secrets_dict["EXPIRES_AT"] = new_expires_at
        secrets_dict["STRAVA_REFRESH_TOKEN"] = new_refresh_token

        # Write the entire updated dictionary back
        sm.update_secret_json(secret_name, secrets_dict)
        logger.debug(f"Successfully persisted updated tokens to Secret Manager")

        return new_access_token

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to refresh Strava token: {e}")
        raise
    except Exception as e:
        logger.critical(f"An unexpected error occurred during token refresh and update: {e}")
        raise

if __name__ == "__main__":
    print("")



