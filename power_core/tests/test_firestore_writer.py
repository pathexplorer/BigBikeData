"""Regression tests for documentation/startup/lib/firestore_writer.py.

Covers the session bug where updateMask.fieldPaths went out as one
comma-joined value (Firestore 400) while curl failures stayed silent.
"""
import io
import json
import urllib.error
import urllib.parse

import pytest

import firestore_writer


class _FakeResponse:
    """Minimal urlopen stub returning a canned JSON body."""

    def __init__(self, body=b"{}"):
        self._body = body

    def read(self):
        """Return the canned body."""
        return self._body

    def __enter__(self):
        """Enter the response context."""
        return self

    def __exit__(self, *exc):
        """Exit the response context without suppressing errors."""
        return False


def _run_writer(monkeypatch, tmp_path, payload, *, error=None):
    """Run write_document with mocked transport; return the captured Request."""
    payload_file = tmp_path / "payload.json"
    payload_file.write_text(json.dumps(payload))
    captured = {}

    def fake_urlopen(request, *args, **kwargs):
        captured["request"] = request
        if error is not None:
            raise error
        return _FakeResponse()

    monkeypatch.setattr(firestore_writer.urllib.request, "urlopen", fake_urlopen)
    firestore_writer.write_document(
        str(payload_file), "test-project", "config/local/settings/data", token="t"
    )
    return captured["request"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("local", {"stringValue": "local"}),
        (5, {"integerValue": "5"}),
        (True, {"booleanValue": True}),
        (1.5, {"doubleValue": 1.5}),
        (None, {"nullValue": None}),
        ({"a": "b"}, {"mapValue": {"fields": {"a": {"stringValue": "b"}}}}),
        (["x"], {"arrayValue": {"values": [{"stringValue": "x"}]}}),
    ],
)
def test_value_conversion(value, expected):
    """Python values map onto Firestore typed Values."""
    assert firestore_writer.to_firestore_value(value) == expected


def test_update_mask_repeated_per_field(monkeypatch, tmp_path):
    """Each payload key gets its own updateMask.fieldPaths param (no commas)."""
    request = _run_writer(
        monkeypatch, tmp_path, {"EMAIL_MODE": "local", "LOGGING_LEVEL": "DEBUG"}
    )
    query = urllib.parse.urlparse(request.full_url).query
    assert urllib.parse.parse_qs(query) == {
        "updateMask.fieldPaths": ["EMAIL_MODE", "LOGGING_LEVEL"]
    }


def test_patch_method_and_auth_headers(monkeypatch, tmp_path):
    """Writes go out as authenticated JSON PATCH requests."""
    request = _run_writer(monkeypatch, tmp_path, {"EMAIL_MODE": "local"})
    assert request.get_method() == "PATCH"
    assert request.get_header("Content-type") == "application/json"
    assert request.get_header("Authorization") == "Bearer t"
    assert "/documents/config/local/settings/data" in request.full_url


def test_http_error_aborts_loudly(monkeypatch, tmp_path):
    """A failed write exits loudly instead of passing silently."""
    error = urllib.error.HTTPError(
        "http://x", 400, "Bad Request", {}, io.BytesIO(b'{"error": "bad"}')
    )
    with pytest.raises(SystemExit, match=r"Firestore write failed \(400\)"):
        _run_writer(monkeypatch, tmp_path, {"EMAIL_MODE": "local"}, error=error)
