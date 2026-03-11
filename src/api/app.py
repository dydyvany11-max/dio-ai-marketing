"""Backward-compatible app module.

Use `src.api.main:app` as the canonical entrypoint.
"""

from src.api.main import app, create_app

__all__ = ["app", "create_app"]
