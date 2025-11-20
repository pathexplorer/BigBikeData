"""
Handles the Flask SECRET_KEY by using either an environment variable (in production)
or the local OS keyring (for local development).
"""
import os
import secrets
from typing import Optional

# --- Environment Detection ---
# The K_SERVICE environment variable is set by Cloud Run.
IS_CLOUD_RUN = "K_SERVICE" in os.environ

# --- Keyring (Local) Configuration ---
try:
    import keyring
except ImportError:
    keyring = None

APP_SERVICE_NAME = "MyAppSessionKey"
APP_KEY_NAME = "SECRET_KEY"


def _get_secret_from_keyring() -> Optional[str]:
    """(Local Only) Retrieves the key from the OS Keyring."""
    if keyring is None:
        print("Warning: 'keyring' package not installed. Local secret storage is disabled.")
        return None
    return keyring.get_password(APP_SERVICE_NAME, APP_KEY_NAME)


def _generate_and_store_in_keyring() -> str:
    """(Local Only) Generates a new secret and stores it in the OS Keyring."""
    new_secret_key = secrets.token_hex(32)
    if keyring:
        keyring.set_password(APP_SERVICE_NAME, APP_KEY_NAME, new_secret_key)
        print("Info: New SECRET_KEY generated and stored in local Keyring.")
    else:
        # If keyring isn't installed, we use a temporary key for the session.
        print("Warning: 'keyring' not available. Using a temporary, non-persistent secret key.")
    return new_secret_key


def set_or_get_app_secret() -> str:
    """
    Determines the environment and fetches the SECRET_KEY accordingly.

    - In Cloud Run (production), it reads from the 'FLASK_SECRET_KEY' environment variable.
    - Locally, it uses the OS keyring, creating a key if one doesn't exist.
    """
    if IS_CLOUD_RUN:
        # --- Production Logic ---
        print("Info: Running in Cloud Run environment. Fetching secret from environment variable.")
        secret = os.environ.get("FLASK_SECRET_KEY")
        if not secret:
            raise ValueError("FATAL: FLASK_SECRET_KEY environment variable not set in production.")
        return secret
    else:
        # --- Local Development Logic ---
        print("Info: Running in local environment. Using OS keyring.")
        secret_key = _get_secret_from_keyring()
        if secret_key is None:
            return _generate_and_store_in_keyring()
        return secret_key
