"""
Initializing Dropbox App
For local run
"""
import requests
from flask import Flask, redirect, request, jsonify
from gcs.google_secret_manager import create_secret, update_secret, get_secret
from project_env import config

app = Flask(__name__)

DROPBOX_CLIENT_ID = get_secret("DROPBOX_APP_KEY")
DROPBOX_CLIENT_SECRET = get_secret("SECRET_DROPBOX_APP_SECRET")
DROPBOX_REDIRECT_URI = config.DROPBOX_REDIRECT_URI

def store_refresh_token(secret_id: str, refresh_token: str):
    create_secret(secret_id)
    # or add new version if it doesn't exist
    update_secret(secret_id, refresh_token)

@app.route("/")
def index():
    auth_url = (
        "https://www.dropbox.com/oauth2/authorize"
        f"?client_id={DROPBOX_CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={DROPBOX_REDIRECT_URI}"
        f"&token_access_type=offline"
    )
    print("Route / completed")
    return redirect(auth_url)

@app.route("/oauth/callback")
def oauth_callback():
    code = request.args.get("code")
    print(code) #DELETE
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
    print(response)
    if response.status_code != 200:
        return f"Token exchange failed: {response.text}", 500

    token_data = response.json()
    refresh_token = token_data.get("refresh_token")
    access_token = token_data.get("access_token")

    # Зберегти в Secret Manager
    store_refresh_token("dropbox-refresh-token", refresh_token)

    return jsonify({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "note": "Refresh token saved to Secret Manager."
    })

if __name__ == "__main__":
    app.run(debug=True)