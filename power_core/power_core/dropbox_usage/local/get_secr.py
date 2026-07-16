"""
Initializing Dropbox App
For local run
"""
import requests
from flask import Flask, redirect, request, jsonify
from gcp_actions.secret_manager import SecretManagerClient
from power_core.project_env import config
from urllib.parse import urlencode

app = Flask(__name__)
sa_email_dd = config.s_email_dropbox
project_idd = config.GCP_PROJECT_ID

sm = SecretManagerClient(project_idd,sa_email_dd)
secrets_db_dict = sm.get_secret_json(config.SEC_DROPBOX)

DROPBOX_CLIENT_ID = secrets_db_dict.get("DROPBOX_APP_KEY")
DROPBOX_CLIENT_SECRET = secrets_db_dict.get("DROPBOX_APP_SECRET")
DROPBOX_REDIRECT_URI = config.DROPBOX_REDIRECT_URI



@app.route("/")
def index():
    params = {
        "client_id": DROPBOX_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": DROPBOX_REDIRECT_URI,
        "token_access_type": "offline",
        "scope": "account_info.read files.content.read files.content.write files.metadata.read files.metadata.write"
    }
    auth_url = "https://www.dropbox.com/oauth2/authorize?" + urlencode(params)
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

    # Save in secret manager
    if "DROPBOX_REFRESH_TOKEN" in secrets_db_dict:
        secrets_db_dict["DROPBOX_REFRESH_TOKEN"] = token_data["refresh_token"]

    sm.update_secret_json(config.SEC_DROPBOX, secrets_db_dict)


    return jsonify({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "note": "Refresh token saved to Secret Manager."
    })

if __name__ == "__main__":
    app.run(debug=False)