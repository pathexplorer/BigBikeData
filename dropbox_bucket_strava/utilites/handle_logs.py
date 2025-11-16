import logging
import os
from google.cloud.logging import Client as LogClient
from google.cloud.logging.handlers import CloudLoggingHandler
import warnings

def run_handle_logs():
    log_client = LogClient()
    IS_LOCAL = os.environ.get("K_SERVICE") is None

    root_log = logging.getLogger()
    root_log.setLevel(logging.INFO)

    warnings.filterwarnings("ignore", category=UserWarning)  # for ignore warn from fit 2 gpx
    if IS_LOCAL:
        # File handler
        file_handler = logging.FileHandler('my_log_file.log', mode='a')
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))
        # Add handlers
        root_log.addHandler(file_handler)
        root_log.addHandler(console_handler)
        # Disable propagation to avoid duplicate
        root_log.propagate = False
        print("Run locally")
    else:
        cloud_handler = CloudLoggingHandler(log_client)
        root_log.addHandler(cloud_handler)
        root_log.propagate = False
        print("Run in cloud")
    # # Increase noise
    for noisy_logger in ["telethon", "urllib3", "asyncio", "google.cloud"]:
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)
