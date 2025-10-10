import dropbox
import requests
from dotenv import load_dotenv
import os

load_dotenv(dotenv_path="other/keys.env")

nAPP_KEY = os.environ["DROPBOX_APP_KEY"]
nAPP_SECRET = os.environ["DROPBOX_APP_SECRET"]
nREFRESH_TOKEN = os.environ["DROPBOX_REFRESH_TOKEN"]

test = '1'

#manual
def get_access_token():
    response = requests.post("https://api.dropbox.com/oauth2/token", data={
        "grant_type": "refresh_token",
        "refresh_token": nREFRESH_TOKEN,
    }, auth=(nAPP_KEY, nAPP_SECRET))
    response.raise_for_status()
    return response.json()["access_token"]

access_tokennn = get_access_token()
dbx = dropbox.Dropbox(oauth2_access_token=access_tokennn)
print("Showing credentials")
print(dbx.users_get_current_account())

#autorefresh
def refresh_tt():
    dbx = dropbox.Dropbox(
        app_key=nAPP_KEY,
        app_secret=nAPP_SECRET,
        oauth2_refresh_token=nREFRESH_TOKEN
    )
    print("Check autorefresh authorisation...")
    account = dbx.users_get_current_account()
    print("Connected to:", account.name.display_name)

if test == '1':
    refresh_tt()
else:
    get_access_token()
    print("Check MANUAL authorisation...")

# Check existing access to files and folders in root
result = dbx.files_list_folder("")
for entry in result.entries:
    print("Files in root folder:", entry.name)