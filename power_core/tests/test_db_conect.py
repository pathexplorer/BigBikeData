"""Regression tests for PostgreSQL connectivity (database.db_conect).

Covers the session outage where connect_to_db() had no connect timeout:
against the unreachable dev PG host every webhook/pipeline init stalled
~127s (OS TCP timeout), breaking Dropbox/PubSub delivery deadlines.
"""
import pytest
import psycopg

from power_core.database import db_conect


class _FakeConn:
    """Stand-in connection recording the autocommit flag."""

    def __init__(self):
        """Create an unconfigured fake connection."""
        self.autocommit = False


def test_returns_none_on_operational_error(monkeypatch):
    """Unreachable DB degrades gracefully instead of raising."""
    def fail(**kwargs):
        raise psycopg.OperationalError("connection failed")

    monkeypatch.setattr(db_conect.psycopg, "connect", fail)
    assert db_conect.connect_to_db() is None


def test_connect_timeout_defaults_to_fast_fail(monkeypatch):
    """The driver gets a short connect timeout unless overridden."""
    captured = {}

    def record(**kwargs):
        captured.update(kwargs)
        return _FakeConn()

    monkeypatch.setattr(db_conect.psycopg, "connect", record)
    assert db_conect.connect_to_db() is not None
    assert captured["connect_timeout"] == 5

    db_conect.connect_to_db(timeout=2)
    assert captured["connect_timeout"] == 2


def test_forwards_env_credentials(monkeypatch):
    """Host/port/dbname/user/password come from the environment."""
    captured = {}

    def record(**kwargs):
        captured.update(kwargs)
        return _FakeConn()

    monkeypatch.setattr(db_conect.psycopg, "connect", record)
    monkeypatch.setenv("PG_HOST", "db.local")
    monkeypatch.setenv("PG_PORT", "5433")
    monkeypatch.setenv("PG_DATABASE", "testdb")
    monkeypatch.setenv("PG_USER", "tester")
    monkeypatch.setenv("PG_PASS", "secret")
    conn = db_conect.connect_to_db()
    assert conn.autocommit is True
    assert (captured["host"], captured["port"], captured["dbname"]) == (
        "db.local", "5433", "testdb",
    )
    assert (captured["user"], captured["password"]) == ("tester", "secret")
