"""Target system adapter implementations."""

from __future__ import annotations

from evalforge_maestro.adapters._trace_norm import normalize_agent_trace, normalize_tool_calls
from evalforge_maestro.adapters.agent import AgentAdapter
from evalforge_maestro.adapters.callable import CallableAdapter
from evalforge_maestro.adapters.docpipe import DocpipeAdapter
from evalforge_maestro.adapters.otel import ingest_otel_spans, load_otel_executions
from evalforge_maestro.adapters.rag import RAGAdapter
from evalforge_maestro.adapters.replay import ReplayAdapter

__all__ = [
    "AgentAdapter",
    "CallableAdapter",
    "DocpipeAdapter",
    "RAGAdapter",
    "ReplayAdapter",
    "ingest_otel_spans",
    "load_otel_executions",
    "normalize_agent_trace",
    "normalize_tool_calls",
]
