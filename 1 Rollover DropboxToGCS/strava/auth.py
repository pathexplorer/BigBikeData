"""
Run before Fit file will be uploaded to strava
"""

import os
import time
import requests
from google.cloud import secretmanager

def get_secret(secret_id):
    client = secretmanager.SecretManagerServiceClient()
    project_id = os.getenv("GCP_PROJECT_ID")
    name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")

def update_secret(secret_id, new_value):
    client = secretmanager.SecretManagerServiceClient()
    project_id = os.getenv("GCP_PROJECT_ID")
    parent = f"projects/{project_id}/secrets/{secret_id}"

    client.add_secret_version(
        request={
            "parent": parent,
            "payload": {"data": new_value.encode("UTF-8")}
        }
    )

def update_strava_token_if_needed():
    client_id = os.getenv("STRAVA_CLIENT_ID")
    client_secret = os.getenv("STRAVA_CLIENT_SECRET")
    refresh_token = get_secret("strava_refresh_token")
    expires_at = int(get_secret("strava_expires_at"))  # stored as Unix timestamp

    now = int(time.time())
    if now < expires_at - 300:  # 5 minutes buffer
        return get_secret("strava_access_token")

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
    update_secret("strava_access_token", token_data["access_token"])
    update_secret("strava_expires_at", str(token_data["expires_at"]))

    # Saving refresh_token only if it changes
    if token_data["refresh_token"] != refresh_token:
        update_secret("strava_refresh_token", token_data["refresh_token"])

    return token_data["access_token"]
