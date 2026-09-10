"""Static guards for container build inputs (power_core).

Covers the session build failures: absolute host paths in requirements
(invisible inside the Docker context) and the nonexistent `libpq` package.
"""
import re
from pathlib import Path

POWER_CORE = Path(__file__).resolve().parents[1]


def _lines(name):
    """Read a build input file as stripped lines."""
    return (POWER_CORE / name).read_text().splitlines()


def test_requirements_have_no_absolute_paths():
    """Every requirements entry must resolve inside the build context."""
    bad = [
        line.strip()
        for line in _lines("requirements.txt")
        if line.strip() and not line.strip().startswith("#")
        and (line.strip().startswith("/") or "/home/" in line or "/root/" in line)
    ]
    assert bad == []


def test_requirements_use_relative_gcp_actions():
    """The shared lib must be referenced relatively (vendored into context)."""
    refs = [line.strip() for line in _lines("requirements.txt") if "gcp_actions" in line]
    assert refs and all(
        ref == "./gcp_actions" or ref.endswith("/gcp_actions[processing-worker]")
        or ref.startswith(("./gcp_actions", "-e ./gcp_actions"))
        for ref in refs
    )


def test_dockerfile_has_no_bare_libpq():
    """The builder needs libpq-dev; bare `libpq` is not a real apt package."""
    content = (POWER_CORE / "Dockerfile").read_text()
    assert "libpq-dev" in content
    bare = [
        line
        for line in content.splitlines()
        if re.fullmatch(r"\s*libpq\s*(\\|&&)?\s*", line)
    ]
    assert bare == []
