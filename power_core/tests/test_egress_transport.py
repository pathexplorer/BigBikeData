"""Tests for resilient egress transport (dropbox_usage.egress_transport).

Covers the session finding: Dropbox DNS rotates edge IPs, some unreachable
from us-central1, so every resolved address must be tried with a short
timeout instead of relying on one slow system default.
"""
import socket

import pytest

from power_core.dropbox_usage import egress_transport as egress
from power_core.dropbox_usage import utils as dropbox_utils


class _FakeSocket:
    """Stub connection with a close method."""

    def close(self):
        """Pretend to close."""


def test_session_mounts_resilient_adapters():
    """Both schemes resolve through the resilient adapter."""
    session = egress.resilient_session()
    assert isinstance(session.get_adapter("https://api.dropboxapi.com"), egress.ResilientAdapter)
    assert isinstance(session.get_adapter("http://api.dropboxapi.com"), egress.ResilientAdapter)


def test_connect_resilient_skips_dead_addresses(monkeypatch):
    """Dead first addresses are skipped for a later live one."""
    infos = [
        (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2001:db8::1", 443, 0, 0)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.9", 443)),
    ]
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: infos)
    seen = []

    def fake_connect(address, timeout=None):
        seen.append((address, timeout))
        if ":" in address[0]:
            raise OSError(101, "Network is unreachable")
        return _FakeSocket()

    monkeypatch.setattr(socket, "create_connection", fake_connect)
    egress.connect_resilient("api.dropboxapi.com", 443, timeout=3)

    assert [ip for (ip, _), _ in seen] == ["2001:db8::1", "192.0.2.9"]
    assert all(t == 3 for _, t in seen)


def test_connect_resilient_reports_all_failures(monkeypatch):
    """Total outage raises one error listing every attempted address."""
    infos = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.9", 443)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.10", 443)),
    ]
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: infos)

    def fail(address, timeout=None):
        raise OSError(101, "Network is unreachable")

    monkeypatch.setattr(socket, "create_connection", fail)
    with pytest.raises(OSError, match=r"all 2 addresses failed.*192.0.2.9.*192.0.2.10"):
        egress.connect_resilient("api.dropboxapi.com", 443, timeout=1)


def test_https_connect_walks_addresses(monkeypatch):
    """The TLS connection dials the first reachable address, then wraps."""
    infos = [
        (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2001:db8::1", 443, 0, 0)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.9", 443)),
    ]
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: infos)
    dialed = []

    def fake_connect(address, timeout=None):
        dialed.append(address[0])
        if ":" in address[0]:
            raise OSError(101, "Network is unreachable")
        return _FakeSocket()

    real_resilient = egress.connect_resilient
    monkeypatch.setattr(
        egress, "connect_resilient",
        lambda host, port, timeout=8: real_resilient(host, port, timeout=timeout),
    )
    monkeypatch.setattr(socket, "create_connection", fake_connect)
    seen = {}

    class FakeContext:
        """Record the TLS wrap call."""

        def wrap_socket(self, sock, server_hostname=None):
            """Record arguments instead of performing TLS."""
            seen["wrapped"] = (sock, server_hostname)
            return ("wrapped-sock",)

    conn = egress._ResilientHTTPSConnection("api.dropboxapi.com", timeout=5)
    conn._context = FakeContext()
    conn.connect()

    assert dialed == ["2001:db8::1", "192.0.2.9"]
    assert seen["wrapped"][1] == "api.dropboxapi.com"


def test_parse_proc_net_route():
    """Route table text yields destination hex values."""
    text = (
        "Iface\tDestination\tGateway\tFlags\n"
        "eth0\t00000000\t0100800A\t0003\n"
        "eth0\t0000800A\t00000000\t0001\n"
    )
    assert egress.parse_proc_net_route(text) == ["00000000", "0000800A"]


def test_diagnose_egress_logs_per_ip_results(monkeypatch, caplog):
    """Diagnostics record DNS answers and per-address TCP outcomes."""
    import logging

    infos = [
        (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2001:db8::1", 443, 0, 0)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.9", 443)),
    ]
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: infos)

    def fake_connect(address, timeout=None):
        if ":" in address[0]:
            raise OSError(101, "Network is unreachable")
        return _FakeSocket()

    monkeypatch.setattr(socket, "create_connection", fake_connect)
    with caplog.at_level(logging.ERROR, logger="power_core.dropbox_usage.egress_transport"):
        egress.diagnose_egress("example.invalid")

    logged = caplog.text
    assert "TCP IPv6 2001:db8::1 FAIL" in logged
    assert "Network is unreachable" in logged
    assert "TCP IPv4 192.0.2.9 OK" in logged


def test_diagnose_egress_survives_dns_failure(monkeypatch, caplog):
    """DNS errors are logged, never raised."""
    import logging

    def fail(*args, **kwargs):
        raise socket.gaierror("no such host")

    monkeypatch.setattr(socket, "getaddrinfo", fail)
    with caplog.at_level(logging.ERROR, logger="power_core.dropbox_usage.egress_transport"):
        egress.diagnose_egress("example.invalid")
    assert "DNS failed" in caplog.text


def test_auth_dropbox_uses_resilient_session(monkeypatch):
    """Dropbox client construction carries the resilient session."""
    captured = {}

    class FakeSecrets:
        """Canned Secret Manager payload without network."""

        def __init__(self, *args, **kwargs):
            """Ignore constructor arguments."""

        def get_secret_json(self, name):
            """Return canned Dropbox credentials."""
            return {
                "DROPBOX_APP_KEY": "k",
                "DROPBOX_APP_SECRET": "s",
                "DROPBOX_REFRESH_TOKEN": "t",
            }

    class FakeDropbox:
        """Capture constructor kwargs without touching the network."""

        def __init__(self, **kwargs):
            """Record kwargs."""
            captured.update(kwargs)

        def users_get_current_account(self):
            """Pretend authentication succeeded."""
            return self

    monkeypatch.setattr(dropbox_utils, "SecretManagerClient", FakeSecrets)
    monkeypatch.setattr(dropbox_utils, "connect_to_db", lambda: None)
    monkeypatch.setattr(dropbox_utils.dropbox, "Dropbox", FakeDropbox)
    # DropboxAuth is lru_cache-wrapped; clear it for test isolation.
    dropbox_utils.DropboxAuth.cache_clear()

    assert isinstance(
        dropbox_utils.DropboxAuth().auth_dropbox(), FakeDropbox
    )
    adapter = captured["session"].get_adapter("https://api.dropboxapi.com")
    assert isinstance(adapter, egress.ResilientAdapter)
