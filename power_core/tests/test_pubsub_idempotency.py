"""Regression tests for atomic Pub/Sub dedup (routes.pubsub_handler).

Covers the check-then-act race where get()+set() let two overlapping
deliveries of the same upload_id both win. The fix claims the marker with
DocumentReference.create(), so the loser gets AlreadyExists.
"""
from google.api_core.exceptions import AlreadyExists

from power_core.routes import pubsub_handler


class _Snap:
    """Minimal Firestore snapshot exposing to_dict()."""

    def __init__(self, data):
        """Wrap canned document data."""
        self._data = data

    def to_dict(self):
        """Return the canned data (or None for missing docs)."""
        return self._data


class _FakeDoc:
    """In-memory document with atomic-create semantics."""

    def __init__(self, store, doc_id):
        """Bind to the shared store."""
        self._store = store
        self._doc_id = doc_id

    def create(self, payload):
        """Create once; raise AlreadyExists like Firestore on conflicts."""
        if self._doc_id in self._store:
            raise AlreadyExists("document already exists")
        self._store[self._doc_id] = dict(payload)

    def get(self):
        """Return a snapshot of the stored (or missing) document."""
        return _Snap(self._store.get(self._doc_id))


class _FakeDB:
    """In-memory Firestore client subset (collection/document only)."""

    def __init__(self, store):
        """Share one store across documents."""
        self._store = store

    def collection(self, name):
        """Ignore collection routing; return self for document()."""
        return self

    def document(self, doc_id):
        """Return a fake document bound to the shared store."""
        return _FakeDoc(self._store, doc_id)


def test_first_claim_wins_second_is_duplicate(monkeypatch):
    """Sequential redelivery is detected without touching the pipeline."""
    store = {}
    monkeypatch.setattr(
        pubsub_handler, "get_any_client", lambda name: _FakeDB(store)
    )
    assert pubsub_handler.check_and_mark_processed("u1", "dropbox_messages") is False
    assert store["u1"]["idempotency_key"] == "u1"
    assert pubsub_handler.check_and_mark_processed("u1", "dropbox_messages") is True


def test_overlapping_claim_loser_gets_already_exists(monkeypatch):
    """A pre-existing marker (in-flight first delivery) blocks the second."""
    store = {"u2": {"idempotency_key": "u2", "processed_at": "t"}}
    monkeypatch.setattr(
        pubsub_handler, "get_any_client", lambda name: _FakeDB(store)
    )
    assert pubsub_handler.check_and_mark_processed("u2", "dropbox_messages") is True


def test_db_error_fails_closed(monkeypatch):
    """DB outage assumes duplicate so Pub/Sub doesn't retry forever."""
    def boom(name):
        raise RuntimeError("firestore down")

    monkeypatch.setattr(pubsub_handler, "get_any_client", boom)
    assert pubsub_handler.check_and_mark_processed("u3", "dropbox_messages") is True
