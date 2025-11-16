from flask import Blueprint, request, Response, jsonify
from dropbox_usage.get_from_dropbox import check_signature
from project_env import config


bp2 = Blueprint("transfer", __name__)


@bp2.route(f'/{config.PRIVATE_ACCESS_TOKEN}', methods=['GET', 'POST'])
def webhook():
    print("PP",config.PRIVATE_ACCESS_TOKEN)
    # --- 1. Handle GET Request (Verification) ---
    if request.method == 'GET':
        # Webhook services often send a GET with a 'challenge' param for verification
        challenge = request.args.get('challenge')
        if challenge:
            print(f"☑️ Webhook Verification GET Request Received. Challenge: {challenge}")
            # MUST return the challenge string to verify
            return Response(challenge, status=200, mimetype='text/plain')

        # If no challenge, it's just a root GET request, return status OK
        return jsonify({"status": "listener active"}), 200

    # --- 2. Handle POST Request (Data Payload) ---
    elif request.method == 'POST':
        try:
            # check_signature() should raise an exception on failure
            # Your reusable function:
            signature_is_valid = check_signature()

            if signature_is_valid:
                print("✅ Webhook received. Signature is valid.")
                # Process the payload (e.g., store data, trigger pipeline)
                # payload = request.json
                # print(payload)

                return jsonify({"status": "success"}), 200
            else:
                print("❌ Webhook received. Signature check FAILED.")
                return jsonify({"status": "unauthorized"}), 401

        except Exception as e:
            # Include robust error handling as per your guidelines
            print(f"🚨 Error processing webhook: {e}")
            return jsonify({"status": "internal server error", "error": str(e)}), 500
    return None

    # This line should technically be unreachable if 'GET' and 'POST' are handled,
    # but for completeness in other cases:
#     return Response("Method Not Allowed", status=405)
# # GET: Used by Dropbox to verify the webhook endpoint.
# # POST: Receives notifications about file changes.
#     if request.method == 'GET':
#         # Dropbox verification challenge
#         challenge = request.args.get('challenge')
#         print("Challenge is OK")
#         return Response(challenge, mimetype='text/plain')
#     elif request.method == 'POST':
#         print("Webhook received. A file change was detected")
#         return check_signature()
#     return Response("Method Not Allowed", status=405)
