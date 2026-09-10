"""Tests for pipeline filename strategy (workshop.workers, instruments).

Private-pipeline files come from the bike computer: plain ASCII, spaces
aside. Names keep their shape (spaces become underscores) so output
artifacts stay derivable from the input name; anything non-ASCII is
rejected downstream by the CLI safety check with a clear error.
"""
from power_core.workshop.instruments import is_safe_tmp_path
from power_core.workshop.workers import ActivityProcessingPipeline


def _private(filename):
    """Build a private-pipeline instance without touching any network."""
    return ActivityProcessingPipeline(
        original_filename=filename,
        dropbox_path=f"/apps/activities/{filename}",
        pipeline_type="private",
    )


def test_spaces_become_underscores_shape_kept():
    """Wahoo-style names pass through, spaces aside."""
    pipeline = _private("my ride.fit")
    assert pipeline.filename == "my_ride.fit"
    assert pipeline.local_fit_path == "/tmp/my_ride.fit"
    assert pipeline.original_filename == "my ride.fit"


def test_ascii_names_untouched():
    """Ordinary names map identically onto local paths."""
    pipeline = _private("wahoo_0001.fit")
    assert pipeline.filename == "wahoo_0001.fit"
    assert pipeline.base_name == "wahoo_0001"


def test_non_ascii_rejected_downstream():
    """Hand-made non-ASCII names fail the CLI safety check loudly."""
    pipeline = _private("problem17g3аt6a.fit")
    assert pipeline.filename == "problem17g3аt6a.fit"
    assert is_safe_tmp_path(pipeline.local_fit_path) is False
