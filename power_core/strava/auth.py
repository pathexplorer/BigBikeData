"""
Run before Fit file will be uploaded to strava
"""
import time
import requests
from power_core.project_env import config

from gcp_actions.secret_manager import SecretManagerClient

sm = SecretManagerClient(config.GCP_PROJECT_ID, config.s_email_strava)
secret_complex_name = config.SEC_STRAVA
secrets_dict = sm.get_secret_json(secret_complex_name)


def update_strava_token_if_needed():
    client_id = secrets_dict.get("STRAVA_APP_ID")
    client_secret = secrets_dict.get("STRAVA_CLIENT_SECRET")
    refresh_token = secrets_dict.get("STRAVA_REFRESH_TOKEN")

    expires_at = int(secrets_dict.get("EXPIRES_AT"))  # stored as Unix timestamp
    now = int(time.time())
    if now < expires_at - 300:  # 5 minutes buffer
        return secrets_dict.get("STRAVA_ACCESS_TOKEN")

    # Token is expiring, updating
    url = "https://www.strava.com/oauth/token"
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }

    response = requests.post(url, data=data)
    response.raise_for_status()
    token_data = response.json()

    # Saving access_token and expires_at

    if "STRAVA_ACCESS_TOKEN" in secrets_dict:
        secrets_dict["STRAVA_ACCESS_TOKEN"] = token_data["access_token"]

    # 2. Update the expiration timestamp, ensuring it is converted to a string
    if "EXPIRES_AT" in secrets_dict:
        # Use str() to enforce the required type for the JSON field value
        secrets_dict["EXPIRES_AT"] = str(token_data["expires_at"])


    sm.update_secret_json(secret_complex_name, secrets_dict)

    # Saving refresh_token only if it changes
    if token_data["refresh_token"] != refresh_token:
        secrets_dict["STRAVA_REFRESH_TOKEN"] = token_data["refresh_token"]
        sm.update_secret_json(secret_complex_name, secrets_dict)
    return token_data["access_token"]
