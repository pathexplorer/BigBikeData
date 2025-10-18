"""
Run before Fit file will be uploaded to strava
"""
import time
import requests
from gcs.google_secret_manager import get_secret, update_secret

def update_strava_token_if_needed():
    client_id = get_secret("strava-client-id")
    client_secret = get_secret("strava-client-secret")
    refresh_token = get_secret("strava-refresh-token")
    expires_at = int(get_secret("strava-expires-at"))  # stored as Unix timestamp

    now = int(time.time())
    if now < expires_at - 300:  # 5 minutes buffer
        return get_secret("strava-access-token")

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
    update_secret("strava-access-token", token_data["access_token"])
    update_secret("strava-expires-at", str(token_data["expires_at"]))

    # Saving refresh_token only if it changes
    if token_data["refresh_token"] != refresh_token:
        update_secret("strava-refresh-token", token_data["refresh_token"])
    return token_data["access_token"]
