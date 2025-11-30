# import os
# import logging
# from gcs.google_secret_manager import get_secret
#
# logging.basicConfig(level=logging.INFO) # hide useless warnings about local running
#
# list_of_secrets = ["dropbox-app-secret",
#                    "dropbox-app-key",
#                    "dropbox-refresh-token",
#                    "strava-refresh-token",
#                    "strava-expires-at",
#                    "strava-access-token"]
#
# def checking_env():
#     required_vars = [
#         "GCP_PROJECT_ID",
#         "GCS_BUCKET_NAME",
#     ]
#
#     for var in required_vars:
#         value = os.environ.get(var)
#         if not value:
#             print(EnvironmentError(f"Environment variable {var} is not set"))
#         logging.info(f"{var} starts from: {value[:4]}...")
#
#     logging.info(f"Checking the availability of secrets in Secret Manager")
#
#     for secret_id in list_of_secrets:
#         try:
#             secret_value = get_secret(secret_id)
#             print(f"The secret {secret_id} is available, starts from з: {secret_value[:4]}...")
#         except Exception as e:
#             raise RuntimeError(f"Failed to get the secret {secret_id}: {e}")
# checking_env()