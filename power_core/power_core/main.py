import sys
import os
from gcp_actions.common_utils.init_config import load_and_inject_config
from gcp_actions.common_utils.handle_logs import run_handle_logs
import logging

# --- 0. Configure Logging and Load Config ---
# These MUST run before any other application imports to ensure
# logs and environment variables are set up correctly.
run_handle_logs()
logger = logging.getLogger(__name__)

try:
    list_of_secret_env_vars = ["APP_JSON_KEYS", "SEC_DROPBOX"]
    list_of_sa_env_vars = [None, "S_ACCOUNT_DROPBOX"]
    load_and_inject_config(list_of_secret_env_vars, list_of_sa_env_vars)
    logger.debug("Configuration loaded successfully.")
except Exception as e:
    logger.critical(f"FATAL ERROR: Could not load configuration. {e}")
    sys.exit(1)


# --- 1. Define the Application Factory ---
def create_app():
    """
    Application factory function.
    Initializes Flask application and registers blueprints.
    """
    # CRITICAL: Imports are inside the factory to prevent them from running
    # before the configuration is loaded.
    from flask import Flask
    from power_core.routes.upload_back import bp1 as upload_bp
    from power_core.routes.transfer import bp2 as transfer_bp
    from power_core.routes.public_user import bp3 as transfer_pubic

    app = Flask(__name__)

    # Register blueprints
    app.register_blueprint(upload_bp)
    app.register_blueprint(transfer_bp)
    app.register_blueprint(transfer_pubic)

    return app

# --- 2. Create the App Instance ---
app = create_app()

# --- 3. Main Execution ---
if __name__ == "__main__":
    app.run(debug=False, use_reloader=False, host="0.0.0.0", port=int(os.environ.get("PORT", 8081)))