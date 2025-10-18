"""
Append one file to one in binary mode for economy
After all, delete original GPX file of activity
"""
from google.cloud import storage
import os
import re
import json
from project_env import config


def strip_source_content(file_path: str) -> str | None:
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    if len(lines) <= 2:
        print("")  # недостатньо рядків для обрізання
        return None
    # Delete first, second and last rows
    stripped_lines = lines[2:-1]
    with open(file_path, "w", encoding="utf-8") as f:
        f.writelines(stripped_lines)
    return "".join(stripped_lines)

def chose_branch(bike_model):
    # Assign gear_id to heatmap names
    return {
        'b7647614': ['mtb', 'mtb_index.txt','mtb_compose_state.json'],
        'b8850168': ['gravel', 'gravel_index.txt','gravel_compose_state.json'],
        'b0000000': ['unknown', 'unknown_index.txt','unknown_compose_state.json'],
    }.get(bike_model)

def extract_first_time_tag(file_path: str) -> str | None:
    time_pattern = re.compile(r"<time>(.*?)</time>")
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            match = time_pattern.search(line)
            if match:
                return match.group(1)
    return None

def download_blob_if_exists(bucket, blob_name, local_path):
    blob = bucket.blob(blob_name)
    if blob.exists():
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        blob.download_to_filename(local_path)
        return True
    return False

def upload_blob(bucket, local_path, blob_name):
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(local_path)

def delete_blob(bucket, blob_name):
    blob = bucket.blob(blob_name)
    if blob.exists():
        blob.delete()

def append_gpx_via_compose(local_gpx: str, bike_model: str, gpx_gcs_path):
    max_compose = 32
    client = storage.Client()
    bucket = client.bucket(config.GCS_BUCKET_NAME)

    # Forming name list for branch
    branch = chose_branch(bike_model)
    if branch is None:
        print(f"Unknown bike_model: {bike_model}")
        return
    gpx_name, index_name, compose_name = branch

    # Local path
    local_index_path = os.path.join(config.LOCAL_TMP, index_name)
    # Path's in the bucket

    index_blob_name = f"heatmap/{index_name}"
    state_blob_name = f"heatmap/{compose_name}"
    fragment_blob_name = f"heatmap/fragments/{os.path.basename(local_gpx)}"

    # Load state of number cycles
    local_state_path = f"/tmp/{compose_name}"
    state_blob = bucket.blob(state_blob_name)
    if state_blob.exists():
        state_blob.download_to_filename(local_state_path)
        with open(local_state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    else:
        ver='00'
        state = {
            "main_blob_name": f"heatmap/{gpx_name}_v{ver}.gpx",
            "compose_count": 0,
            "version": 0
        }
    main_blob_name = state["main_blob_name"]
    compose_count = state["compose_count"]
    version = state["version"]

    # Loading index
    indexed_dates = set()
    if download_blob_if_exists(bucket, index_blob_name, local_index_path):
        with open(local_index_path, "r", encoding="utf-8") as f:
            indexed_dates = set(line.strip() for line in f)

    # Extract date
    first_date = extract_first_time_tag(local_gpx)
    if not first_date:
        print(f"File '{local_gpx}' not include tag <time>.")
        return

    if first_date in indexed_dates:
        print(f"Date {first_date} already in the index. File not added.")
        return

    # Update index locally
    os.makedirs(os.path.dirname(local_index_path), exist_ok=True)
    with open(local_index_path, "a", encoding="utf-8") as f:
        f.write(first_date + "\n")
    print("Index activities created.")
    # Strip GPX file: first, second and last rows
    strip_source_content(local_gpx)

    # Loaded fragment to bucket
    upload_blob(bucket, local_gpx, fragment_blob_name)

    # Union
    fragment_blob = bucket.blob(fragment_blob_name)
    if not fragment_blob.exists():
        print(f"Error: Fragment '{fragment_blob_name}' doesn't exist.")
        return
    main_blob = bucket.blob(main_blob_name)
    if not main_blob.exists():
        print(f"Heatmap file doesn't exist. Creating empty blob with XML header. His compose version is 0")
        main_blob_path = os.path.join(config.LOCAL_TMP, os.path.basename(main_blob_name))
        os.makedirs(os.path.dirname(main_blob_path), exist_ok=True)
        with open(main_blob_path, "w", encoding="utf-8") as f:
            f.write("""<?xml version="1.0" encoding="UTF-8"?>
        <gpx version="1.1" creator="SPipeline">
         """)
        upload_blob(bucket, main_blob_path, main_blob_name)
        print(f"Heatmap file created:'{main_blob_name}'.")

    main_blob.compose([main_blob, fragment_blob])
    compose_count += 1
    print(f"Fragment '{fragment_blob_name}' added to '{main_blob_name}'.")

    # If the limit is reached - create new version
    if compose_count >= max_compose:
        version += 1
        new_main_blob_name = f"heatmap/{gpx_name}_v{version:02d}.gpx"
        bucket.blob(new_main_blob_name).compose([main_blob])
        try:
            bucket.blob(main_blob_name).delete()
            print(f"Previous version '{main_blob_name}' deleted.")
        except Exception as e:
            print(f"Unable to delete '{main_blob_name}': {e}")
        main_blob_name = new_main_blob_name
        compose_count = 1  # the first compose already gone
        print(f"Create new version: '{main_blob_name}'")

    # Update state json
    state = {
        "main_blob_name": main_blob_name,
        "compose_count": compose_count,
        "version": version
    }
    with open(local_state_path, "w", encoding="utf-8") as f:
        json.dump(state, f)
    state_blob.upload_from_filename(local_state_path)
    print(f"State updated: compose_count={compose_count}, version={version}")

    # Upload updating index in bucket
    upload_blob(bucket, local_index_path, index_blob_name)

    # Delete fragment
    delete_blob(bucket, fragment_blob_name)
    print(f"Fragment '{fragment_blob_name}' deleting after union.")

    # Delete GPX from bucket. But I need single file for GIS analyze later. So, it will be deleted after this analyze (coming soon...)
    # delete_blob(bucket, gpx_gcs_path)
    # print(f"Fragment '{gpx_gcs_path}' deleting after union.")

