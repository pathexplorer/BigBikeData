"""
Simple alternative of Secret manager, for non-sensitive data
"""


import keyring
import secrets
from typing import Optional

# Define the service name and key for your application's local secret
APP_SERVICE_NAME = "MyAppSessionKey"
APP_KEY_NAME = "SECRET_KEY"


def get_app_secret() -> Optional[str]:
    """Retrieves the application's SECRET_KEY from the OS Keyring."""
    # The keyring library provides a secure way to access OS-level credential storage.
    return keyring.get_password(APP_SERVICE_NAME, APP_KEY_NAME)


def set_or_get_app_secret() -> str:
    """
    Checks for the SECRET_KEY in the Keyring. If it doesn't exist,
    it generates a new one, stores it, and returns it.
    """
    secret_key = get_app_secret()

    if secret_key is None:
        # Generate a strong, random key (e.g., 64-character hex string)
        new_secret_key = secrets.token_hex(32) * 2

        # Store the new key securely in the OS Keyring
        keyring.set_password(APP_SERVICE_NAME, APP_KEY_NAME, new_secret_key)

        # Log or print a warning that a new key was generated (for development)
        print(f"Warning: New SECRET_KEY generated and stored in local Keyring.")
        return new_secret_key

    return secret_key

# Example Usage: Load the secret key into a web framework's config
# from flask import Flask
# app = Flask(__name__)
# app.config['SECRET_KEY'] = set_or_get_app_secret()