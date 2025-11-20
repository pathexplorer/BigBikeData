import logging
import os
from google.cloud.logging import Client as LogClient
from google.cloud.logging.handlers import CloudLoggingHandler
import warnings


class CustomColorFormatter(logging.Formatter):
    """
    A custom formatter that applies ANSI colors to log messages based on level.
    """
    # Define color codes
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    BOLD_RED = "\033[31;1m"
    RESET = "\033[0m"

    # Default log format
    DEFAULT_FORMAT = "%(levelname)s - %(message)s (%(filename)s:%(lineno)d)"

    FORMATS = {
        logging.DEBUG: DEFAULT_FORMAT,
        logging.INFO: GREEN + DEFAULT_FORMAT + RESET,  # INFO message will be GREEN
        logging.WARNING: YELLOW + DEFAULT_FORMAT + RESET,
        logging.ERROR: RED + DEFAULT_FORMAT + RESET,
        logging.CRITICAL: BOLD_RED + DEFAULT_FORMAT + RESET
    }

    def format(self, record):
        # Retrieve the format string based on the log level
        log_fmt = self.FORMATS.get(record.levelno, self.DEFAULT_FORMAT)

        # Create a standard Formatter instance using the colorized format
        formatter = logging.Formatter(log_fmt)

        return formatter.format(record)





def run_handle_logs():
    log_client = LogClient()
    IS_LOCAL = os.environ.get("K_SERVICE") is None

    root_log = logging.getLogger()
    root_log.setLevel(logging.INFO)

    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.setLevel(logging.INFO)

    warnings.filterwarnings("ignore", category=UserWarning)  # for ignore warn from fit 2 gpx
    if IS_LOCAL:
        # File handler
        file_handler = logging.FileHandler('my_log_file.log', mode='a')
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(CustomColorFormatter())
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

