"""Tests for Dropbox sync accountability (dropbox_usage.get_from_dropbox).

Covers the session finding: cursor advanced past publish failures (lost
files) and random upload ids (duplicates on replay). Stable file keys plus
markers make retries safe: no loss, no mass reprocessing.
"""
from datetime import datetime, timedelta, timezone

import pytest
from dropbox.files import DeletedMetadata, FileMetadata
from google.cloud.firestore import Increment

from power_core.dropbox_usage import get_from_dropbox as sync


def _fit(name, file_id="id:1", rev="015d7f8a9b"):
    """Build a fake .fit FileMetadata entry."""
    return FileMetadata(
        name=name, path_lower=f"/apps/activities/{name}",
        path_display=f"/Apps/activities/{name}", id=file_id, rev=rev,
    )


class _Result:
    """Canned list_folder result page."""

    def __init__(self, entries, cursor, has_more=False):
        """Store entries, next cursor, and pagination flag."""
        self.entries = entries
        self.cursor = cursor
        self.has_more = has_more


class _FakeDbx:
    """Scripted Dropbox client: first listing plus continue pages by cursor."""

    def __init__(self, first, continues=None):
        """Script the initial page and follow-up pages per cursor."""
        self._first = first
        self._continues = continues or {}

    def files_list_folder(self, path, recursive=True, include_deleted=True):
        """Return the scripted first page."""
        return self._first

    def files_list_folder_continue(self, cursor):
        """Return the scripted page for a cursor."""
        return self._continues[cursor]


class _FakeCursor:
    """In-memory cursor store."""

    def __init__(self, cursor=None):
        """Start with an optional stored cursor."""
        self.cursor = cursor

    def load_cursor(self):
        """Return the stored cursor."""
        return self.cursor

    def save_cursor(self, cursor):
        """Persist the cursor."""
        self.cursor = cursor


class _FakeMarkers:
    """In-memory file marker store."""

    def __init__(self, records=None, stale=None):
        """Start with optional pre-existing marker records and sweep backlog."""
        self.records = dict(records or {})
        self.published = []
        self._stale = list(stale or [])

    def get(self, file_key):
        """Return the marker record or {}."""
        return self.records.get(file_key, {})

    def mark_published(self, file_key, upload_id, now,
                       dropbox_path=None, original_filename=None):
        """Record a publish."""
        self.records[file_key] = {
            "status": "published", "upload_id": upload_id,
            "updated_at": now.isoformat(),
        }
        self.published.append(file_key)

    def list_stale(self, now):
        """Return the scripted sweep backlog."""
        return list(self._stale)

    def mark_final(self, file_key, status, upload_id=""):
        """Record a terminal outcome in the fake store."""
        record = self.records.get(file_key, {})
        record.update({"status": status, "upload_id": upload_id})
        self.records[file_key] = record


@pytest.fixture()
def publisher(monkeypatch):
    """Capture published messages; toggle failures per file name."""
    calls = []
    failures = set()

    def fake(topic, payload):
        if payload["original_filename"] in failures:
            raise RuntimeError("pubsub down")
        calls.append((topic, payload))

    monkeypatch.setattr(sync, "publish_to_pubsub", fake)
    return calls, failures


def _now():
    """Current UTC time for marker timestamps."""
    return datetime.now(timezone.utc)


def test_first_run_publishes_fits_with_stable_ids(publisher):
    """No cursor: full listing publishes .fit files keyed by id:rev."""
    calls, _ = publisher
    dbx = _FakeDbx(_Result([
        _fit("a.fit", "id:a", "015d7f8a9b"),
        _fit("notes.txt", "id:t", "015d7f8a9b"),
        DeletedMetadata(name="old.fit", path_lower="/apps/activities/old.fit"),
    ], "cursor-2"))
    cursor, markers = _FakeCursor(), _FakeMarkers()

    assert sync.connect_to_dropbox(dbx=dbx, cursor_store=cursor, marker_store=markers) is True

    assert len(calls) == 1
    topic, payload = calls[0]
    assert payload["upload_id"] == "id:a:015d7f8a9b"
    assert payload["file_key"] == "id:a:015d7f8a9b"
    assert cursor.cursor == "cursor-2"
    assert markers.records["id:a:015d7f8a9b"]["status"] == "published"


def test_continue_run_publishes_only_new(publisher):
    """Stored cursor: only entries after it are published."""
    calls, _ = publisher
    dbx = _FakeDbx(
        _Result([], "cursor-1"),
        {"cursor-1": _Result([_fit("b.fit", "id:b", "015d7f8a9b")], "cursor-2")},
    )
    cursor = _FakeCursor("cursor-1")

    assert sync.connect_to_dropbox(
        dbx=dbx, cursor_store=cursor, marker_store=_FakeMarkers()) is True
    assert [p["original_filename"] for _, p in calls] == ["b.fit"]
    assert cursor.cursor == "cursor-2"


def test_completed_marker_skipped(publisher):
    """Already completed files are never republished."""
    calls, _ = publisher
    dbx = _FakeDbx(_Result([_fit("a.fit", "id:a", "015d7f8a9b")], "cursor-2"))
    markers = _FakeMarkers({"id:a:015d7f8a9b": {"status": "completed"}})

    assert sync.connect_to_dropbox(
        dbx=dbx, cursor_store=_FakeCursor(), marker_store=markers) is True
    assert calls == []


def test_fresh_published_marker_skipped(publisher):
    """In-flight files are not duplicated while the pipeline may run."""
    calls, _ = publisher
    dbx = _FakeDbx(_Result([_fit("a.fit", "id:a", "015d7f8a9b")], "cursor-2"))
    markers = _FakeMarkers({"id:a:015d7f8a9b": {
        "status": "published", "updated_at": _now().isoformat()}})

    assert sync.connect_to_dropbox(
        dbx=dbx, cursor_store=_FakeCursor(), marker_store=markers) is True
    assert calls == []


def test_stale_published_marker_republished(publisher):
    """Published-but-never-completed files are retried (try until processed)."""
    calls, _ = publisher
    dbx = _FakeDbx(_Result([_fit("a.fit", "id:a", "015d7f8a9b")], "cursor-2"))
    old = (_now() - timedelta(hours=2)).isoformat()
    markers = _FakeMarkers({"id:a:015d7f8a9b": {"status": "published", "updated_at": old}})

    assert sync.connect_to_dropbox(
        dbx=dbx, cursor_store=_FakeCursor(), marker_store=markers) is True
    assert [p["upload_id"] for _, p in calls] == ["id:a:015d7f8a9b"]


def test_publish_failure_keeps_cursor_and_retries(publisher):
    """A failed publish keeps the old cursor and leaves no marker behind."""
    calls, failures = publisher
    failures.add("a.fit")
    dbx = _FakeDbx(
        _Result([], "cursor-1"),
        {"cursor-1": _Result([_fit("a.fit", "id:a", "015d7f8a9b")], "cursor-2")},
    )
    cursor, markers = _FakeCursor("cursor-1"), _FakeMarkers()

    assert sync.connect_to_dropbox(
        dbx=dbx, cursor_store=cursor, marker_store=markers) is False
    assert cursor.cursor == "cursor-1"
    assert markers.records == {}

    failures.clear()
    assert sync.connect_to_dropbox(
        dbx=dbx, cursor_store=cursor, marker_store=markers) is True
    assert [p["upload_id"] for _, p in calls] == ["id:a:015d7f8a9b"]
    assert cursor.cursor == "cursor-2"


def test_stable_id_falls_back_to_random(publisher):
    """Entries without id/rev still publish instead of crashing."""
    calls, _ = publisher
    entry = FileMetadata(name="x.fit", path_lower="/apps/activities/x.fit")
    dbx = _FakeDbx(_Result([entry], "cursor-2"))

    assert sync.connect_to_dropbox(
        dbx=dbx, cursor_store=_FakeCursor(), marker_store=_FakeMarkers()) is True
    assert calls and calls[0][1]["upload_id"]


def test_marker_writes_use_explicit_merge(monkeypatch):
    """set_firejson must pass explicit merge (None crashes new firestore clients)."""
    calls = []
    written = []

    class FakeMagic:
        """Record FirestoreMagic interactions without network."""

        stored = {}

        def __init__(self, collection, doc_id, placeholder=None):
            """Record target coordinates."""
            calls.append(("init", collection, doc_id))
            self.doc_id = doc_id

        def load_firejson(self):
            """Return the canned record."""
            return dict(FakeMagic.stored.get(self.doc_id, {}))

        def set_firejson(self, data, merge=None):
            """Record the write mode and persist the canned record."""
            calls.append(("set", merge))
            written.append(dict(data))
            FakeMagic.stored[self.doc_id] = dict(data)

    monkeypatch.setattr(sync, "FirestoreMagic", FakeMagic)
    store = sync.DropboxFileMarkers()
    store.mark_published("k", "u", _now())
    store.mark_final("k", "completed", "u")
    modes = [entry[1] for entry in calls if entry[0] == "set"]
    assert modes == [True, True]
    # Attempts ride a server-side Increment: no read-modify-write, no lost counts.
    assert isinstance(written[0]["attempts"], Increment)


def _sweep_markers(monkeypatch):
    """Real marker store backed by the recording FakeMagic."""
    calls = []

    class SweepMagic:
        """Persist canned records without network."""

        stored = {}

        def __init__(self, collection, doc_id, placeholder=None):
            """Point at a canned document."""
            self.doc_id = doc_id

        def load_firejson(self):
            """Return the canned record."""
            return dict(SweepMagic.stored.get(self.doc_id, {}))

        def set_firejson(self, data, merge=None):
            """Persist the canned record, resolving server increments like Firestore."""
            prev = SweepMagic.stored.get(self.doc_id, {})
            resolved = {}
            for key, value in data.items():
                if isinstance(value, Increment):
                    resolved[key] = prev.get(key, 0) + 1
                else:
                    resolved[key] = value
            if merge:
                merged = dict(prev)
                merged.update(resolved)
                SweepMagic.stored[self.doc_id] = merged
            else:
                SweepMagic.stored[self.doc_id] = resolved

    monkeypatch.setattr(sync, "FirestoreMagic", SweepMagic)
    return sync.DropboxFileMarkers(), SweepMagic


def test_marker_attempts_increment(monkeypatch):
    """Republishes count attempts so hopeless files can go dead."""
    store, magic = _sweep_markers(monkeypatch)
    magic.stored["k"] = {"status": "failed", "attempts": 2}
    store.mark_published("k", "u", _now(), dropbox_path="/a.fit",
                         original_filename="a.fit")
    saved = magic.stored["k"]
    assert saved["attempts"] == 3
    assert saved["dropbox_path"] == "/a.fit"
    assert saved["status"] == "published"


def test_mark_published_writes_without_read(monkeypatch):
    """No read-modify-write: the count must not depend on a prior read."""
    class NoReadMagic:
        """Fail the test if the marker path reads before writing."""

        def __init__(self, collection, doc_id, placeholder=None):
            """Bind to the canned document."""
            self.doc_id = doc_id

        def load_firejson(self):
            """Reads are the race; they must not happen."""
            raise AssertionError("mark_published must not read before writing")

        def set_firejson(self, data, merge=None):
            """The merge write must carry a server-side increment."""
            assert merge is True
            assert isinstance(data["attempts"], Increment)

    monkeypatch.setattr(sync, "FirestoreMagic", NoReadMagic)
    sync.DropboxFileMarkers().mark_published("k", "u", _now())


def test_sweep_republishes_stale_failed(publisher):
    """Stale failed markers with a path are republished with the same id."""
    calls, _ = publisher
    stale = [{
        "file_key": "id:s:015d7f8a9b", "dropbox_path": "/apps/activities/s.fit",
        "original_filename": "s.fit", "upload_id": "id:s:015d7f8a9b",
        "status": "failed",
        "updated_at": (_now() - timedelta(hours=3)).isoformat(),
    }]
    dbx = _FakeDbx(_Result([], "cursor-1"),
                   {"cursor-1": _Result([], "cursor-2")})
    cursor = _FakeCursor("cursor-1")
    markers = _FakeMarkers(stale=stale)

    assert sync.connect_to_dropbox(
        dbx=dbx, cursor_store=cursor, marker_store=markers) is True
    assert [(p["upload_id"], p["file_key"]) for _, p in calls] == [("id:s:015d7f8a9b", "id:s:015d7f8a9b")]
    assert cursor.cursor == "cursor-2"


def test_sweep_failure_keeps_cursor(publisher):
    """A failed sweep republish keeps the old cursor for the next run."""
    calls, failures = publisher
    failures.add("s.fit")
    stale = [{
        "file_key": "id:s:015d7f8a9b", "dropbox_path": "/apps/activities/s.fit",
        "original_filename": "s.fit", "upload_id": "id:s:015d7f8a9b",
        "status": "failed",
        "updated_at": (_now() - timedelta(hours=3)).isoformat(),
    }]
    dbx = _FakeDbx(_Result([], "cursor-1"),
                   {"cursor-1": _Result([], "cursor-2")})
    cursor = _FakeCursor("cursor-1")

    assert sync.connect_to_dropbox(
        dbx=dbx, cursor_store=cursor,
        marker_store=_FakeMarkers(stale=stale)) is False
    assert cursor.cursor == "cursor-1"
    assert calls == []


def test_list_stale_filters(monkeypatch):
    """The sweep returns only retryable markers with a path."""
    now = _now()
    old = (now - timedelta(hours=3)).isoformat()
    fresh = now.isoformat()
    docs = [
        ("k-done", {"status": "completed", "updated_at": old,
                    "dropbox_path": "/a.fit"}),
        ("k-fresh", {"status": "published", "updated_at": fresh,
                     "dropbox_path": "/b.fit"}),
        ("k-stale", {"status": "published", "updated_at": old,
                     "dropbox_path": "/c.fit"}),
        ("k-failed", {"status": "failed", "updated_at": old,
                      "dropbox_path": "/d.fit"}),
        ("k-nopath", {"status": "failed", "updated_at": old}),
        ("k-dead", {"status": "failed", "updated_at": old,
                    "dropbox_path": "/e.fit", "attempts": 99}),
        ("k-badts", {"status": "failed", "updated_at": "nope",
                     "dropbox_path": "/f.fit"}),
    ]

    class FakeDoc:
        """Canned Firestore document."""

        def __init__(self, doc_id, data):
            """Store id and payload."""
            self.id = doc_id
            self._data = data

        def to_dict(self):
            """Return the payload."""
            return dict(self._data)

    class FakeCollection:
        """Stream canned documents."""

        def stream(self):
            """Yield every canned document."""
            return [FakeDoc(doc_id, data) for doc_id, data in docs]

    class FakeClient:
        """Serve the canned collection."""

        def collection(self, name):
            """Return the canned collection."""
            assert name == "dropbox_files"
            return FakeCollection()

    monkeypatch.setattr("gcp_actions.client.get_any_client",
                        lambda *a, **k: FakeClient())
    found = {entry["file_key"] for entry in sync.DropboxFileMarkers().list_stale(now)}
    assert found == {"k-stale", "k-failed", "k-badts"}


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        (None, True),
        ({}, True),
        ({"status": "completed"}, False),
        ({"status": "dead"}, False),
        ({"status": "failed", "attempts": 99}, False),
        ({"status": "published", "updated_at": "not-a-date"}, True),
    ],
)
def test_needs_publish_edge_cases(record, expected):
    """Empty/broken records publish; terminal/exhausted ones never do."""
    assert sync.file_needs_publish(record, _now()) is expected


def test_exhausted_file_marked_dead(publisher):
    """Hopeless files are marked dead instead of retried forever."""
    calls, _ = publisher
    dbx = _FakeDbx(_Result([_fit("a.fit", "id:a", "015d7f8a9b")], "cursor-2"))
    markers = _FakeMarkers({"id:a:015d7f8a9b": {
        "status": "failed", "attempts": 99,
        "updated_at": (_now() - timedelta(hours=9)).isoformat()}})

    assert sync.connect_to_dropbox(
        dbx=dbx, cursor_store=_FakeCursor(), marker_store=markers) is True
    assert calls == []
    assert markers.records["id:a:015d7f8a9b"]["status"] == "dead"


def test_needs_publish_fresh_vs_stale():
    """Fresh markers suppress; stale published/failed markers retry."""
    now = _now()
    fresh = (now - timedelta(minutes=30)).isoformat()
    stale = (now - timedelta(hours=2)).isoformat()
    assert sync.file_needs_publish({"status": "published", "updated_at": fresh}, now) is False
    assert sync.file_needs_publish({"status": "published", "updated_at": stale}, now) is True
    assert sync.file_needs_publish({"status": "failed", "updated_at": fresh}, now) is False
    assert sync.file_needs_publish({"status": "failed", "updated_at": stale}, now) is True
