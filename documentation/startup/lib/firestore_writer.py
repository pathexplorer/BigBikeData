#!/usr/bin/env python3
"""Write a plain-JSON document into Cloud Firestore via the REST API.

gcloud (580.0.0) does not ship a `gcloud firestore documents` command, so this
module performs the equivalent PATCH request directly. It converts a flat JSON
payload into Firestore's typed Value format.

CLI:
    python3 firestore_writer.py --payload PAYLOAD_JSON \
        --project PROJECT_ID --document-path COLLECTION/DOC[/...] [--token TOKEN]

If --token is omitted, it is obtained via `gcloud auth print-access-token`.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.parse

FIRESTORE_API = "https://firestore.googleapis.com/v1"


def to_firestore_value(value):
    """Convert a Python value into a Firestore Value object."""
    if isinstance(value, str):
        return {"stringValue": value}
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, int):
        return {"integerValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if value is None:
        return {"nullValue": None}
    if isinstance(value, dict):
        return {
            "mapValue": {
                "fields": {k: to_firestore_value(v) for k, v in value.items()}
            }
        }
    if isinstance(value, list):
        return {"arrayValue": {"values": [to_firestore_value(v) for v in value]}}
    return {"stringValue": str(value)}


def get_access_token():
    """Fetch an OAuth access token from the local gcloud login."""
    result = subprocess.run(
        ["gcloud", "auth", "print-access-token"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        sys.exit(f"gcloud auth failed: {result.stderr}")
    return result.stdout.strip()


def write_document(payload_path, project_id, document_path, token=None):
    """PATCH a Firestore document with the contents of payload_path."""
    with open(payload_path) as handle:
        data = json.load(handle)

    document = {
        "fields": {k: to_firestore_value(v) for k, v in data.items()}
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
        json.dump(document, tmp)
        tmp_path = tmp.name

    try:
        token = token or get_access_token()
        encoded_path = urllib.parse.quote(document_path, safe="/")
        url = (
            f"{FIRESTORE_API}/projects/{project_id}/databases/(default)/"
            f"documents/{encoded_path}"
            f"?updateMask.fieldPaths={','.join(data.keys())}"
        )
        result = subprocess.run(
            [
                "curl", "-sS", "-X", "PATCH",
                "-H", f"Authorization: Bearer {token}",
                "-H", "Content-Type: application/json",
                "-d", f"@{tmp_path}",
                url,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            sys.exit(f"Firestore write failed: {result.stderr}")
        return result.stdout
    finally:
        os.unlink(tmp_path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload", required=True, help="Path to plain JSON payload")
    parser.add_argument("--project", required=True, help="GCP project ID")
    parser.add_argument(
        "--document-path",
        required=True,
        help="Firestore document path, e.g. config/local/settings/data",
    )
    parser.add_argument("--token", help="OAuth token (default: fetch via gcloud)")
    args = parser.parse_args()

    write_document(args.payload, args.project, args.document_path, args.token)


if __name__ == "__main__":
    main()
