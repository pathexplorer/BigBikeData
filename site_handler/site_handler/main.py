import sys
import os
from gcp_actions.common_utils.init_config import load_and_inject_config
from gcp_actions.common_utils.handle_logs import run_handle_logs
import logging


logger = logging.getLogger(__name__)
run_handle_logs()

# --- 1. Define the Application Factory ---
def create_app():
    """
    Application factory function.
    Initializes Flask application and registers blueprints.
    """
    # CRITICAL: Imports occur inside the factory, ensuring they only run
    # AFTER the configuration has been loaded in the startup script.

    from flask import Flask, render_template
    from werkzeug.middleware.proxy_fix import ProxyFix
    from site_handler.route_site.public_access import bp3 as frontend
    from site_handler.route_site.language import bp4 as language_bp
    from site_handler.route_site.defender import bp9 as defender
    from site_handler.route_site.app_config_module import set_or_get_app_secret

    from site_handler.utilites.babel_config import init_babel
    # --- Flask App Initialization ---

    flask_app = Flask(__name__)
    flask_app.config['SECRET_KEY'] = set_or_get_app_secret()
    # Initialize extensions
    init_babel(flask_app)

    # --- Global Error Handler ---
    @flask_app.errorhandler(500)
    def internal_server_error(e6):
        # This handler is triggered for any unhandled 500 error in the app.
        logger.error(f"Global 500 error handler triggered: {e6}")
        return render_template('500.html'), 500

    # Custom middleware to fix Host header for Firebase Hosting proxy
    class HostRewriteMiddleware:
        def __init__(self, app_instance):
            self.app = app_instance

        def __call__(self, environ, start_response):
            # If X-Forwarded-Host is present, use it to rewrite the Host header
            # This makes Flask think it's running on the public domain
            forwarded_host = environ.get('HTTP_X_FORWARDED_HOST')
            if forwarded_host:
                environ['HTTP_HOST'] = forwarded_host
                # Also update SERVER_NAME for proper URL generation
                environ['SERVER_NAME'] = forwarded_host.split(':')[0]
                if ':' in forwarded_host:
                    environ['SERVER_PORT'] = forwarded_host.split(':')[1]
            return self.app(environ, start_response)

    # --- Production-Only Configurations ---
    # Cloud Run sets The K_SERVICE environment variable.
    # If it's not present, we're running locally.
    if os.environ.get("K_SERVICE"):
        flask_app.wsgi_app = HostRewriteMiddleware(flask_app.wsgi_app)

        # Then apply ProxyFix for X-Forwarded-Proto
        # x_for=2 and x_host=1 (since we manually handle host above), x_proto=1 for a single HTTPS header
        flask_app.wsgi_app = ProxyFix(flask_app.wsgi_app, x_for=2, x_proto=1, x_host=1, x_prefix=1)
        flask_app.config.update(
            PREFERRED_URL_SCHEME='https',
            SESSION_COOKIE_NAME='__session',
            SESSION_COOKIE_SECURE=True,
            SESSION_COOKIE_SAMESITE='Lax',
            SESSION_COOKIE_HTTPONLY=True,
            SESSION_COOKIE_PATH='/'
        )

    # --- Blueprint Registration ---
    flask_app.register_blueprint(defender)
    flask_app.register_blueprint(frontend)
    flask_app.register_blueprint(language_bp)

    return flask_app

# --- 2. Application Startup Logic ---
try:
    list_of_secret_env_vars = ["APP_JSON_KEYS"]
    load_and_inject_config(list_of_secret_env_vars)
    logger.debug("Configuration loaded successfully from Secret Manager/Firestore.")

except Exception as e:
    # This catches errors in the config loading process (e.g., API failure, missing secrets)
    logger.critical(f"FATAL ERROR: Could not load configuration. {e}")
    sys.exit(1)

app = create_app()

# --- Main Execution ---
if __name__ == "__main__":
    app.run(debug=False, use_reloader=False, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
