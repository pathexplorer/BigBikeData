from flask import Flask
from routes.upload_back import bp1 as upload_bp
from routes.transfer import bp2 as transfer_bp
from routes.public_access import bp3 as frontend
import os
from utilites.handle_logs import run_handle_logs

run_handle_logs()

app = Flask(__name__)

app.register_blueprint(upload_bp)
app.register_blueprint(transfer_bp)
app.register_blueprint(frontend)


# Cloud Run set PORT as it want. For testing code locally, already will be using 8080
# guinocorn ignores this row
if __name__ == "__main__":
   app.run(debug=True, use_reloader=False, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
