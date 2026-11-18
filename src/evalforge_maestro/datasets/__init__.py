"""Dataset ingestion, schema validation, and canonical SHA-256 fingerprinting."""

from __future__ import annotations

from evalforge_maestro.datasets.docpipe_fixture import load_docpipe_fixture
from evalforge_maestro.datasets.engine import DatasetEngine, DatasetStreamResult

__all__ = ["DatasetEngine", "DatasetStreamResult", "load_docpipe_fixture"]
