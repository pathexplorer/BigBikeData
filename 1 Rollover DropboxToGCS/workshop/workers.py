import os
from project_env import config
from gcs.google_secret_manager import get_secret
from gcs.blob_manipulation import upload_blob_from_file, download_blob_if_exists
from strava.upload import *
from strava.auth import update_strava_token_if_needed
from fit2gpx import Converter
from heatmap_gpx.append_function import append_gpx_via_compose
import warnings
from workshop.instruments import convert_fit_to_csv, clean_gps

warnings.filterwarnings("ignore", category=UserWarning) # for ignore warn from fit 2 gpx
conv = Converter()

def union_pipeline(blob_path):
# extracting some data from original .FIT for Data Labeling
    # For ony files from Wahoo Roam, which name in format: 'YYYY-MM-DD-HHMMSS-elemnt... .fit'
    # timestamp_part = filename.split("-elemnt")[0]
    # dt = datetime.strptime(timestamp_part, "%Y-%m-%d-%H%M%S")
    # formatted = dt.strftime("%Y-%m-%d %H:%M:%S") # extracted timestamp of start activity
    # now = datetime.now(timezone.utc)
    # now_str = now.strftime("%Y-%m-%d %H:%M:%S") # current timestamp
# ----- load FIT to Virtual Machine(AKA "local") -----
    filename = os.path.basename(blob_path)
    local_fit = f"/tmp/{filename}"
    os.makedirs("/tmp", exist_ok=True)
    path = f"{config.GSC_ORIG_FIT_FOLDER}/{filename}" # Exclude gs:// part from path: simple build new path from variables
    download_blob_if_exists(path, local_fit)
    print(f".fit downloaded to VM: {local_fit}")
# ----- FIT >>> Unexplored CSV
    local_csv = f"/tmp/{filename.replace('.fit', '.csv')}"
    convert_fit_to_csv(local_fit, local_csv, mode='decode')
    print("FIT decoded. Skipped saving the unexplored CSV in a bucket")
    #csv_gcs_path = f"csv/{os.path.basename(local_csv)}"
    #upload_blob_from_file(csv_gcs_path, local_csv)
    #print(f"Uploaded unexplored CSV in bucket:{csv_gcs_path}")
# ----- Clean unexplored CSV from gps problems
    name, ext = os.path.splitext(os.path.basename(local_csv))
    local_csv_fix = f"/tmp/{name}_fixed{ext}"
    bike_model = clean_gps(local_csv, local_csv_fix)
    fit_csv_gcs_path = f"csv_clean/{os.path.basename(local_csv_fix)}"
    upload_blob_from_file(fit_csv_gcs_path, local_csv_fix)
    print(f"Fixed:{fit_csv_gcs_path}")
# ----- 3 phase explored CSV >>> FIT
    name1 = os.path.splitext(os.path.basename(local_csv))[0] # delete .extension
    local_fix_fit = f"/tmp/{name1}_ffixed.fit"
    convert_fit_to_csv(local_csv_fix, local_fix_fit, mode='encode')
    fix_fit_gcs_path = f"fit_clean/{os.path.basename(local_fix_fit)}"
    upload_blob_from_file(fix_fit_gcs_path, local_fix_fit)
    print(f"Uploaded fixed version in:{fix_fit_gcs_path}")
# ----- 4 phase: Push explored FIT to strava
    current_mode = get_secret("current-mode")
    if current_mode == "prod":
        access_token = update_strava_token_if_needed()
        upload_id = upload_fit_to_strava(access_token, local_fix_fit)
        activity_id = poll_upload_status(upload_id, access_token)
        updated = update_gear(activity_id, access_token, bike_model)
        print(f"Uploaded to Strava: {updated}")
    elif current_mode == "testing":
        print(f"SKIPPED uploading to STRAVA")
# ----- Convert explored FIT to GPX
    local_gpx = f"/tmp/{filename.replace('.fit', '.gpx')}"
    conv.fit_to_gpx(local_fix_fit, local_gpx)
    gpx_gcs_path = f"gpx/{os.path.basename(local_gpx)}"
    upload_blob_from_file(gpx_gcs_path, local_gpx)
    print(f"Uploaded GPX in GCS:{gpx_gcs_path}")
# ----- Create heatmap by bike
    append_gpx_via_compose(local_gpx, bike_model, gpx_gcs_path)