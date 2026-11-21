"""Immutable local artifact persistence under .evalforge/."""

from __future__ import annotations

from evalforge_maestro.storage.local import LocalRunStore
from evalforge_maestro.storage.sqlite_index import SQLiteRunIndex

__all__ = ["LocalRunStore", "SQLiteRunIndex"]
