# debug_utils.py
import os
import logging
import json

# Set up basic logging
logging.basicConfig(level=logging.INFO, format='%(message)s')


def log_runtime_env_vars(prefix=None):
    """
    Logs all environment variables, optionally filtered by a prefix.
    Sensitive variables (like secrets) should NOT be logged.
    """
    logged_vars = {}

    # Define a list of sensitive key substrings to skip
    SENSITIVE_KEYS = ['SECRET', 'PASSWORD', 'KEY', 'TOKEN', 'CREDENTIAL']

    for key, value in os.environ.items():
        # Check if the key contains any sensitive substring (case-insensitive)
        if any(sk in key.upper() for sk in SENSITIVE_KEYS):
            logged_vars[key] = f"***[OMITTED: {key}]***"
        elif prefix is None or key.startswith(prefix):
            logged_vars[key] = value

    # Log the collected variables in a structured format (JSON recommended for Cloud Logging)
    logging.info(json.dumps({
        "message": "RUNTIME ENVIRONMENT VARIABLES DUMP",
        "variables": logged_vars
    }))