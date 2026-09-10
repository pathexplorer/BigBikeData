"""Regression tests for the Dropbox webhook endpoint (routes.transfer).

Covers the session bug where Dropbox verification GET on the secret webhook
path returned 405 because the route accepted POST only.
"""
import os

import pytest
from flask import Flask

from power_core.routes.transfer import bp2

WEBHOOK_PATH = f"/{os.environ['DROpbox_WEBHOOK_PATH']}"


@pytest.fixture()
def client():
    """Flask test client with the transfer blueprint registered."""
    app = Flask(__name__)
    app.register_blueprint(bp2)
    client = app.test_client()
    client._webhook_rule = next(
        rule for rule in app.url_map.iter_rules() if rule.rule == WEBHOOK_PATH
    )
    return client


def test_webhook_rule_accepts_get_and_post(client):
    """The secret path must serve GET (challenge) without dropping POST (events)."""
    assert {"GET", "POST"} <= set(client._webhook_rule.methods)


def test_challenge_echo(client):
    """Dropbox verification challenge is echoed back as plain text."""
    response = client.get(f"{WEBHOOK_PATH}?challenge=abc123")
    assert response.status_code == 200
    assert response.data == b"abc123"
    assert response.content_type.startswith("text/plain")


def test_challenge_missing(client):
    """Challenge-less GET is rejected instead of crashing the handler."""
    assert client.get(WEBHOOK_PATH).status_code == 400
