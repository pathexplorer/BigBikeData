"""
for future use
"""

import os
import requests
from flask import Flask, redirect, request, jsonify
from dotenv import load_dotenv
from google.cloud import secretmanager

load_dotenv(dotenv_path="../other/keys.env")
app = Flask(__name__)

DROPBOX_CLIENT_ID = os.getenv("DROPBOX_APP_KEY")
DROPBOX_CLIENT_SECRET = os.getenv("SECRET_DROPBOX_APP_SECRET")
DROPBOX_REDIRECT_URI = os.getenv("DROPBOX_REDIRECT_URI")

def store_refresh_token(secret_id: str, refresh_token: str, project_id: str):
    client = secretmanager.SecretManagerServiceClient()
    parent = f"projects/{project_id}"

    # Creating secret, if not exist
    try:
        client.create_secret(
            request={
                "parent": parent,
                "secret_id": secret_id,
                "secret": {
                    "replication": {"automatic": {}}
                },
            }
        )
    except Exception as e:
        if "AlreadyExists" not in str(e):
            raise

    # Add new version
    client.add_secret_version(
        request={
            "parent": f"{parent}/secrets/{secret_id}",
            "payload": {"data": refresh_token.encode("UTF-8")},
        }
    )


@app.route("/")
def index():
    auth_url = (
        "https://www.dropbox.com/oauth2/authorize"
        f"?client_id={DROPBOX_CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={DROPBOX_REDIRECT_URI}"
        f"&token_access_type=offline"
    )
    return redirect(auth_url)


@app.route("/oauth/callback")
def oauth_callback():
    code = request.args.get("code")
    if not code:
        return "No code provided", 400

    token_url = "https://api.dropboxapi.com/oauth2/token"
    data = {
        "code": code,
        "grant_type": "authorization_code",
        "client_id": DROPBOX_CLIENT_ID,
        "client_secret": DROPBOX_CLIENT_SECRET,
        "redirect_uri": DROPBOX_REDIRECT_URI,
    }

    response = requests.post(token_url, data=data)
    if response.status_code != 200:
        return f"Token exchange failed: {response.text}", 500

    token_data = response.json()
    refresh_token = token_data.get("refresh_token")
    access_token = token_data.get("access_token")

    # Зберегти в Secret Manager
    project_id = os.getenv("GCP_PROJECT_ID") #or get_project_id_from_metadata()
    store_refresh_token("dropbox-refresh-token", refresh_token, project_id)

    return jsonify({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "note": "Refresh token saved to Secret Manager."
    })


if __name__ == "__main__":
    app.run(debug=True)