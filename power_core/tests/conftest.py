"""Shared pytest setup: dummy env for config import and startup-lib path."""
import os
import sys
from pathlib import Path

# power_core.project_env.config exits at import when required vars are missing,
# so provide test dummies before any power_core import happens.
os.environ.setdefault("GCP_PROJECT_ID", "local-test-project")
os.environ.setdefault("APP_JSON_KEYS", "test-app-json-keys")
os.environ.setdefault("SEC_DROPBOX", "test-dropbox-secrets")
os.environ.setdefault("S_ACCOUNT_DROPBOX", "test-dropbox@test.iam.gserviceaccount.com")
os.environ.setdefault("S_ACCOUNT_RUN", "test-run@test.iam.gserviceaccount.com")
os.environ.setdefault("DROpbox_WEBHOOK_PATH", "test-hook-path")

_STARTUP_LIB = Path(__file__).resolve().parents[2] / "documentation" / "startup" / "lib"
if str(_STARTUP_LIB) not in sys.path:
    sys.path.insert(0, str(_STARTUP_LIB))
