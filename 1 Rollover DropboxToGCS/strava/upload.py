import requests
import time

def upload_fit_to_strava(access_token: str, fit_file_path: str) -> dict:

    url = "https://www.strava.com/api/v3/uploads"
    headers = {"Authorization": f"Bearer {access_token}"}
    files = {"file": open(fit_file_path, "rb")}
    data = {
        "data_type": "fit",
        #"name": "Auto-uploaded FIT",
        #"description": "Wuahahah! Uploaded via pipeline",
            }
    response = requests.post(url, headers=headers, files=files, data=data)
    response.raise_for_status()
    upload_id = response.json()["id"]
    return upload_id

def poll_upload_status(upload_id, access_token):
    url = f"https://www.strava.com/api/v3/uploads/{upload_id}"
    headers = {"Authorization": f"Bearer {access_token}"}

    for _ in range(20):  # ~20 second wait
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        if data.get("activity_id"):
            return data["activity_id"]
        time.sleep(1)

    raise TimeoutError("Strava doesn't return activity_id in certain time")

def update_gear(activity_id: int, access_token: str, bike_model: str):
    url = f"https://www.strava.com/api/v3/activities/{activity_id}"
    headers = {"Authorization": f"Bearer {access_token}"}
    payload = {"gear_id": bike_model}

    response = requests.put(url, headers=headers, data=payload)
    response.raise_for_status()
    return response.json()











