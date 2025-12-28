import sys
import os
from gcp_actions.common_utils.init_config import InjectConfig
from gcp_actions.common_utils.handle_logs import run_handle_logs
import logging

run_handle_logs()
logger = logging.getLogger(__name__)

try:
    list_of_secret_env_vars = ["APP_JSON_KEYS"]
    list_of_sa_env_vars = [None]
    ic = InjectConfig(list_of_secret_env_vars, list_of_sa_env_vars)
    ic.load_and_inject_config()
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

    from flask import Flask
    from power_core.routes.transfer import bp1 as upload_bp
    from power_core.routes.transfer import bp2 as transfer_bp
    from power_core.routes.transfer import bp3 as transfer_pubic
    from power_core.routes.transfer import bp_private as transfer_private

    app = Flask(__name__)

    # Register blueprints
    app.register_blueprint(upload_bp)
    app.register_blueprint(transfer_bp)
    app.register_blueprint(transfer_pubic)
    app.register_blueprint(transfer_private)

    return app

# --- 2. Create the App Instance ---
app = create_app()

# --- 3. Main Execution ---
if __name__ == "__main__":
    app.run(debug=False, use_reloader=False, host="0.0.0.0", port=int(os.environ.get("PORT", 8081)))
