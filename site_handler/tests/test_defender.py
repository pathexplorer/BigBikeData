"""Regression tests for the defender middleware (route_site.defender).

Covers the session outage where a missing ALLOWED_DOMAINS crashed the import
(None.split) and took the frontend down with 503s instead of failing closed.
"""
import importlib
import sys

import pytest
from flask import Flask

import site_handler.route_site.defender  # noqa: F401 (ensures sys.modules entry)
import site_handler.utilites.site_config as site_config

MODULE = "site_handler.route_site.defender"


@pytest.fixture()
def load_defender():
    """Reload defender with a forced ALLOWED_DOMAINS; restore module after."""
    original = site_config.ALLOWED_DOMAINS

    def load(value):
        site_config.ALLOWED_DOMAINS = value
        return importlib.reload(sys.modules[MODULE])

    yield load
    site_config.ALLOWED_DOMAINS = original
    importlib.reload(sys.modules[MODULE])


def _client(defender_module):
    """Test client with the defender blueprint guarding one dummy route."""
    app = Flask(__name__)
    app.register_blueprint(defender_module.bp9)

    @app.route("/")
    def index():
        """Dummy endpoint behind the middleware."""
        return "ok"

    return app.test_client()


def test_none_allowlist_imports_empty(load_defender):
    """Missing variable yields an empty allowlist instead of crashing import."""
    assert load_defender(None).ALLOWED_HOSTS == set()


def test_none_allowlist_blocks_everything(load_defender):
    """Empty allowlist fails closed: every host gets 403, service stays up."""
    client = _client(load_defender(None))
    assert client.get("/", headers={"Host": "example.com"}).status_code == 403


def test_allowlist_matching_is_case_and_port_insensitive(load_defender):
    """Parsing lowercases, strips, and drops empties; matching ignores port."""
    module = load_defender("Example.COM, localhost,")
    assert module.ALLOWED_HOSTS == {"example.com", "localhost"}
    client = _client(module)
    assert client.get("/", headers={"Host": "Example.COM:443"}).status_code == 200


def test_direct_run_app_access_stays_blocked(load_defender):
    """The run.app rule survives the hardening."""
    client = _client(load_defender("example.com"))
    response = client.get("/", headers={"Host": "x-uc.a.run.app"})
    assert response.status_code == 403
