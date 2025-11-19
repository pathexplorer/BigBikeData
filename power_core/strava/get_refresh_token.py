"""
Base setting for first run
"""
from flask import Flask, redirect, request, jsonify
import requests
from power_core.project_env import config

from gcp_actions.secret_manager import SecretManagerClient

sm = SecretManagerClient(config.GCP_PROJECT_ID, config.s_email_strava)

app = Flask(__name__)

# Credentials
secrets_dict = sm.get_secret_json(config.SEC_STRAVA)

CLIENT_ID = secrets_dict.get("STRAVA_APP_ID")
CLIENT_SECRET = secrets_dict.get("STRAVA_CLIENT_SECRET")

REDIRECT_URI = config.STRAVA_REDIRECT_URI


@app.route("/")
def home():
    auth_url = (
        f"https://www.strava.com/oauth/authorize"
        f"?client_id={CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={REDIRECT_URI}"
        f"&approval_prompt=force"
        f"&scope=activity:write,activity:read_all"
    )

    return f'<a href="{auth_url}">Authorize with Strava</a>'

@app.route("/exchange_token")
def exchange_token():
    code = request.args.get("code")
    if not code:
        return "Missing code", 400

    token_url = "https://www.strava.com/oauth/token"
    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code"
    }

    response = requests.post(token_url, data=payload)
    if response.status_code != 200:
        return f"Token exchange failed: {response.text}", 500

    token_data = response.json()
    return jsonify({
        "access_token": token_data["access_token"],
        "refresh_token": token_data["refresh_token"],
        "expires_at": token_data["expires_at"]
    })

if __name__ == "__main__":
    app.run(debug=True)