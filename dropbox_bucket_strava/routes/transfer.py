from flask import Blueprint, request, Response
from dropbox_usage.get_from_dropbox import check_signature
from project_env.config import PRIVATE_ACCESS_TOKEN


bp2 = Blueprint("transfer", __name__)

@bp2.route(f'/${PRIVATE_ACCESS_TOKEN}', methods=['GET', 'POST'])
def webhook():
    print("Webhook received. A file change was detected")
# GET: Used by Dropbox to verify the webhook endpoint.
# POST: Receives notifications about file changes.
    if request.method == 'GET':
        # Dropbox verification challenge
        challenge = request.args.get('challenge')
        print("Challenge is OK")
        return Response(challenge, mimetype='text/plain')
    elif request.method == 'POST':
        print("Webhook received. A file change was detected")
        return check_signature()
    return Response("Method Not Allowed", status=405)