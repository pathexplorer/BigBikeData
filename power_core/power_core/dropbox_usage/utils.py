import dropbox
from dropbox.exceptions import AuthError
from power_core.project_env.config import s_email_dropbox, SEC_DROPBOX, GCP_PROJECT_ID
import hmac, hashlib
from flask import request, Response
import logging
import os
from functools import lru_cache
from gcp_actions.common_utils.timer import run_timer
from gcp_actions.secret_manager import SecretManagerClient
from power_core.database.db_conect import connect_to_db
logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
@run_timer

class DropboxAuth:
    def __init__(self):


        sm = SecretManagerClient(GCP_PROJECT_ID, s_email_dropbox)
        current_secret_data = sm.get_secret_json(SEC_DROPBOX)

        # Inject the config into the environment
        for key, value in current_secret_data.items():
            os.environ[key] = str(value)
        logger.info(f"✅ Injected Dropbox And Strava {len(current_secret_data)} configuration keys  into environment.")
        self.DROPBOX_APP_KEY = os.environ.get("DROPBOX_APP_KEY")
        self.DROPBOX_APP_SECRET = os.environ.get("DROPBOX_APP_SECRET")
        self.DROPBOX_REFRESH_TOKEN = os.environ.get("DROPBOX_REFRESH_TOKEN")
        connect_to_db()

    def auth_dropbox(self):
            """
            Creates and authorizes a Dropbox client.
            This is the single source of truth for Dropbox authentication.
            """

            logger.debug("Attempting to authorize with Dropbox...")
            try:
                dbx = dropbox.Dropbox(
                    app_key=self.DROPBOX_APP_KEY,
                    app_secret=self.DROPBOX_APP_SECRET,
                    oauth2_refresh_token=self.DROPBOX_REFRESH_TOKEN
                )
                dbx.users_get_current_account()
                logger.debug("Dropbox authorization successful.")
                return dbx
            except AuthError as e:
                logger.error(f"Fatal Dropbox authorization error: {e}")
                raise

    @run_timer
    def check_signature(self) -> Response | bool:
        """
        Checks the Dropbox signature. Shorter than 0.01 s locally
        :return: True or Response 403
        """
        signature = request.headers.get('X-Dropbox-Signature')
        dbx_app_secret = self.DROPBOX_APP_SECRET
        if not hmac.compare_digest(signature, hmac.new(dbx_app_secret.encode(), request.data, hashlib.sha256).hexdigest()):
            logger.error("Invalid signature. Request ignored.")
            return Response("Forbidden", status=403)
        logger.debug(f"Request: {request.json}")
        return True

