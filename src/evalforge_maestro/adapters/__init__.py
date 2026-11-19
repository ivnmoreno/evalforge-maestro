"""Target system adapter implementations."""

from __future__ import annotations

from evalforge_maestro.adapters.callable import CallableAdapter
from evalforge_maestro.adapters.docpipe import DocpipeAdapter
from evalforge_maestro.adapters.rag import RAGAdapter
from evalforge_maestro.adapters.replay import ReplayAdapter

__all__ = ["CallableAdapter", "DocpipeAdapter", "RAGAdapter", "ReplayAdapter"]
