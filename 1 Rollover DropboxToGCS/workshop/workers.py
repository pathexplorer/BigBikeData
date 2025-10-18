import os
import re
from project_env import config
from gcs.google_secret_manager import get_secret
from strava.upload import *
from strava.auth import update_strava_token_if_needed
import subprocess
from fit2gpx import Converter
from heatmap_gpx.append_function import append_gpx_via_compose
from gcs.client import get_bucket
import warnings

warnings.filterwarnings("ignore", category=UserWarning) # for ignore warn from fit 2 gpx
bucket = get_bucket()
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
    path = f"{config.GSC_ORIG_FIT_FOLDER}/{filename}" # Exclude gs:// part from path: simple build new path from variables
    local_fit = f"/tmp/{filename}"
    os.makedirs("/tmp", exist_ok=True)
    blob = bucket.blob(path)
    blob.download_to_filename(local_fit)
    print(f".fit downloaded to VM: {blob_path} → {local_fit}")
# ----- FIT >>> Unexplored CSV
    local_csv = f"/tmp/{filename.replace('.fit', '.csv')}"
    convert_fit_to_csv(local_fit, local_csv, mode='decode')
    #csv_gcs_path = f"csv/{os.path.basename(local_csv)}"
    #bucket.blob(csv_gcs_path).upload_from_filename(local_csv)
    #print(f"Uploaded unexplored CSV in bucket:{csv_gcs_path}")
    print("FIT decoded. Skipped saving the unexplored CSV in a bucket")
# ----- Clean unexplored CSV from gps problems
    name, ext = os.path.splitext(os.path.basename(local_csv))
    local_csv_fix = f"/tmp/{name}_fixed{ext}"
    bike_model = clean_gps(local_csv, local_csv_fix)
    fit_csv_gcs_path = f"csv_clean/{os.path.basename(local_csv_fix)}"
    bucket.blob(fit_csv_gcs_path).upload_from_filename(local_csv_fix)
    print(f"Fixed:{fit_csv_gcs_path}")
# ----- 3 phase explored CSV >>> FIT
    name1 = os.path.splitext(os.path.basename(local_csv))[0] # delete .extension
    local_fix_fit = f"/tmp/{name1}_ffixed.fit"
    convert_fit_to_csv(local_csv_fix, local_fix_fit, mode='encode')
    fix_fit_gcs_path = f"fit_clean/{os.path.basename(local_fix_fit)}"
    bucket.blob(fix_fit_gcs_path).upload_from_filename(local_fix_fit)
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
    bucket.blob(gpx_gcs_path).upload_from_filename(local_gpx)
    print(f"Uploaded GPX in GCS:{gpx_gcs_path}")
# ----- Create heatmap by bike
    append_gpx_via_compose(local_gpx, bike_model, gpx_gcs_path)



def convert_fit_to_csv(input_path, output_path, mode):
    flag = "-b" if mode == "decode" else "-c"
    subprocess.run(["java", "-jar", "FitCSVTool.jar", flag, input_path, output_path], check=True)

def label_bike(lines):
    mtb = ['ant_device_number,"4315"', 'ant_device_number,"33509"']
    gravel = ['ant_device_number,"2230"', 'ant_device_number,"9560"']
    for line in lines:
        if any(code in line for code in mtb):
            return 'b7647614'
        if any(code in line for code in gravel):
            return 'b8850168'
    return 'b0000000'

def clean_gps(input_path, output_path):
    """
    Processing CSV for clean from GPS problems, fix incorrect sensor serial number, getting bike model
    """
    # Finding lat, long and gps_accuracy
    pattern = re.compile(
       r'position_lat,"(-?\d+)",semicircles,position_long,"-?\d+",semicircles,'
    )
    with open(input_path, 'r', encoding='utf-8') as infile:
        lines = infile.readlines()
    bike_model = label_bike(lines)
    cleaned_lines = []
    for line in lines:
        if line.startswith("Data"):
            match = pattern.search(line)
            if match:
                lat_value = int(match.group(1))
                if lat_value < 0:
                    line = line.replace(match.group(0), "")  # Видаляємо фрагмент
            #for records before 01/10/2025
            line = re.sub(r'serial_number,"SN\.(\d+)"', r'serial_number,"\1"', line)
        cleaned_lines.append(line)
    with open(output_path, 'w', encoding='utf-8') as outfile:
        outfile.writelines(cleaned_lines)
    return bike_model
