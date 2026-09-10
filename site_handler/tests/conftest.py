"""Shared pytest setup: deterministic ALLOWED_DOMAINS baseline for imports."""
import os

os.environ.setdefault("ALLOWED_DOMAINS", "localhost")
