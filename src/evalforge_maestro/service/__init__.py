"""Optional HTTP service wrapper delegating strictly to EvalForge Maestro library/storage."""

from __future__ import annotations

from evalforge_maestro.service.app import ServiceApplication, validate_service_bind_policy
from evalforge_maestro.service.server import create_http_server, serve_http

__all__ = [
    "ServiceApplication",
    "create_http_server",
    "serve_http",
    "validate_service_bind_policy",
]
