import requests
import time

class StravaUpload:
    def __init__(self, access_token, fit_file_path: str, bike_model: str):
        self.access_token = access_token
        self.headers = {"Authorization": f"Bearer {access_token}"}
        self.fit_file_path = fit_file_path
        self.bike_model = bike_model

    def _upload_fit_to_strava(self) -> dict:
        url = "https://www.strava.com/api/v3/uploads"
        files = {"file": open(self.fit_file_path, "rb")}
        data = {
            "data_type": "fit",
            #"name": "Auto-uploaded FIT",
            #"description": "Wuahahah! Uploaded via pipeline",
                }
        response = requests.post(url, headers=self.headers, files=files, data=data)
        response.raise_for_status()
        upload_id = response.json()["id"]
        return upload_id

    def _poll_upload_status(self):
        """
        :return: int
        """
        upload_id = self._upload_fit_to_strava

        url = f"https://www.strava.com/api/v3/uploads/{upload_id}"
        for _ in range(20):  # ~20 second wait
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            data = response.json()
            if data.get("activity_id"):
                return data["activity_id"]
            time.sleep(1)
        raise TimeoutError("Strava doesn't return activity_id in certain time")

    def upload_activity(self):
        """
        Run internal chain to upload activity and add gear id
        :return: response.json(), activity_id
        """
        activity_id = self._poll_upload_status
        url = f"https://www.strava.com/api/v3/activities/{activity_id}"
        payload = {"gear_id": self.bike_model}
        response = requests.put(url, headers=self.headers, data=payload)
        response.raise_for_status()
        return response.json(), activity_id











