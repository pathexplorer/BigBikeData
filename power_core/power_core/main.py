import sys
import os
from gcp_actions.common_utils.init_config import InjectConfig
from gcp_actions.common_utils.handle_logs import run_handle_logs
from gcp_actions.secret_manager import SecretManagerClient
import logging

run_handle_logs()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 1. Load configuration
# ---------------------------------------------------------------------------
try:
    list_of_secret_env_vars = ["APP_JSON_KEYS"]
    list_of_sa_env_vars = [None]
    ic = InjectConfig(list_of_secret_env_vars, list_of_sa_env_vars)
    ic.load_and_inject_config()
    logger.debug("Configuration loaded successfully.")
except Exception as e:
    logger.critical(f"FATAL ERROR: Could not load configuration. {e}")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 2. Pre-flight: verify critical secrets are actually accessible AND contain
#    the required keys. Prevents "server starts but first request crashes".
# ---------------------------------------------------------------------------
_CRITICAL_SECRETS = [
    # (env_var_for_name, sa_env_var, required_keys)
    ("APP_JSON_KEYS",  None,                ["GCP_PROJECT_ID"]),
    ("SEC_DROPBOX",    "S_ACCOUNT_DROPBOX",  ["DROPBOX_APP_SECRET"]),
]

def _verify_secrets() -> None:
    """Fetch every critical secret and verify required keys exist. Exit if any fail."""
    project_id = os.environ.get("GCP_PROJECT_ID", "?")
    emulator_host = os.environ.get("SECRET_MANAGER_EMULATOR_HOST")
    mode = f"emulator at {emulator_host}" if emulator_host else "real GCP Secret Manager"

    failed = []
    for secret_env_var, sa_env_var, required_keys in _CRITICAL_SECRETS:
        secret_name = os.environ.get(secret_env_var)
        if not secret_name:
            failed.append((secret_env_var, "env var not set — add to local_config.json"))
            continue

        sa_email = os.environ.get(sa_env_var) if sa_env_var else None
        try:
            sm = SecretManagerClient(project_id, sa_email)
            payload = sm.get_secret_json(secret_name)
            missing_keys = [k for k in required_keys if k not in payload]
            if missing_keys:
                failed.append((
                    secret_env_var,
                    f"secret '{secret_name}' exists but is missing keys: {', '.join(missing_keys)}\n"
                    f"    → Seed real data into the emulator."
                ))
            else:
                logger.info(f"✅ Secret '{secret_name}' ({secret_env_var}) OK — {len(payload)} keys.")
        except Exception as e:
            failed.append((secret_env_var, str(e)))

    if failed:
        print(
            "\n" + "=" * 60 + "\n"
            "\033[31m❌  PRE-FLIGHT FAILED — Cannot access required secrets\033[0m\n"
            + "=" * 60 + "\n"
            f"Mode: {mode}\n\n"
            "The following secrets could not be verified:\n\n"
            + "\n".join(f"  • {name}\n    → {err}" for name, err in failed) +
            "\n\n💡  If using the emulator:\n"
            "    1. Ensure it's running:    podman ps | grep sm-emulator\n"
            "    2. Seed REAL tokens:       ./local_dev.sh seed  (requires keys.env)\n"
            "    3. Or seed manually:       see seed.py for the expected payload format\n"
            "    4. Check connectivity:     curl http://localhost:8083/health\n"
            "\n💡  If using real GCP:\n"
            "    Ensure Application Default Credentials are configured.\n"
            + "=" * 60 + "\n",
            file=sys.stderr,
        )
        sys.exit(1)

    logger.info("✅ Pre-flight check passed — all critical secrets are accessible and contain required keys.")

_verify_secrets()


# --- 3. Define the Application Factory ---
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
