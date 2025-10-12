"""
Start local and only once
"""

import requests
from dotenv import load_dotenv
import os

load_dotenv(dotenv_path="../other/keys.env")

nAPP_KEY = os.environ["DROPBOX_APP_KEY"]
nAPP_SECRET = os.environ["DROPBOX_APP_SECRET"]
nCODE_FOR_GET_REFRESH = os.environ["CODE_FOR_GET_REFRESH"]

redirect_uri_ = input("Please enter your redirect uri in format http://site:port: ")


data = {
    "code": nCODE_FOR_GET_REFRESH,
    "grant_type": "authorization_code",
    "client_id": nAPP_KEY,
    "client_secret": nAPP_SECRET,
    "redirect_uri": redirect_uri_
}

response = requests.post("https://api.dropboxapi.com/oauth2/token", data=data)
print(response.json())
