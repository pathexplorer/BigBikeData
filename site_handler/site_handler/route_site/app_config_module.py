import os
import logging
import keyring
from site_handler.utilites.site_config import FLASK_SECRET_KEY

logger = logging.getLogger(__name__)

def set_or_get_app_secret() -> str:
    """
    Retrieves the Flask SECRET_KEY with a secure order of precedence.

    1. Checks for the 'FLASK_SECRET_KEY' environment variable (the highest priority).
    2. If not found and running locally, uses the system keyring.
    3. If not found and in a cloud environment, it raises an error.
    """
    # 1. Prioritize Environment Variable
    secret_key = FLASK_SECRET_KEY
    if secret_key:
        logger.debug("Loaded FLASK_SECRET_KEY from environment variable.")
        return secret_key

    # 2. Check for Cloud Environment vs. Local
    # The K_SERVICE variable is a reliable indicator of a Cloud Run environment.
    is_cloud_environment = "K_SERVICE" in os.environ

    if is_cloud_environment:
        # In the cloud, the key MUST be in the environment.
        logger.critical("'FLASK_SECRET_KEY' is not set in the cloud environment.")
        raise ValueError("FLASK_SECRET_KEY is a mandatory environment variable for cloud deployments.")

    # 3. Fallback to Keyring for Local Development
    logger.info("FLASK_SECRET_KEY not in environment. Attempting to use local keyring...")
    try:
        secret_key = keyring.get_password("flask_app", "secret_key")
        if not secret_key:
            logger.warning("No secret key in keyring. Generating a new one for local development.")
            secret_key = os.urandom(24).hex()
            keyring.set_password("flask_app", "secret_key", secret_key)
            logger.info("New secret key stored in local keyring for future runs.")
        else:
            logger.info("Successfully loaded secret key from local keyring.")
        return secret_key
    except Exception as e:
        # If the keyring fails for any reason, raise an error.
        logger.critical(f"Keyring access failed: {e}. Cannot start without a secret key.")
        raise RuntimeError("Failed to get a secret key from keyring for local development.")
