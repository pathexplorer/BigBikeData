from flask import Flask
from route_site.public_access import bp3 as frontend
import os
from utilites.handle_logs import run_handle_logs
from utilites.app_config_module import set_or_get_app_secret

run_handle_logs()

app = Flask(__name__)
app.config['SECRET_KEY'] = set_or_get_app_secret()

app.register_blueprint(frontend)


if __name__ == "__main__":
   app.run(debug=True, use_reloader=False, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
