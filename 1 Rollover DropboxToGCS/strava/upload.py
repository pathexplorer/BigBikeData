import requests

def upload_fit_to_strava(access_token: str, fit_file_path: str) -> dict:
    url = "https://www.strava.com/api/v3/uploads"
    headers = {"Authorization": f"Bearer {access_token}"}
    files = {"file": open(fit_file_path, "rb")}
    data = {
        "data_type": "fit",
        "name": "Auto-uploaded FIT",
        "description": "Wuahahah! Uploaded via pipeline"
    }

    response = requests.post(url, headers=headers, files=files, data=data)
    response.raise_for_status()
    return response.json()