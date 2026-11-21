"""Lazy stdlib ThreadingHTTPServer wrapper exposing ServiceApplication over HTTP/1.1."""

from __future__ import annotations

import logging
from typing import Any

from evalforge_maestro._canonical import scrub_secret_text
from evalforge_maestro.service.app import ServiceApplication, validate_service_bind_policy
from evalforge_maestro.types import ServiceConfig, ServiceErrorResponse

_LOGGER = logging.getLogger(__name__)


def create_http_server(
    config: ServiceConfig,
    *,
    auth_token: str | None = None,
    judge_api_key: str | None = None,
    embedding_api_key: str | None = None,
) -> Any:
    """Create (without blocking) a ThreadingHTTPServer bound to config.host:config.port."""
    validate_service_bind_policy(config, auth_token=auth_token)
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    app = ServiceApplication(
        config,
        auth_token=auth_token,
        judge_api_key=judge_api_key,
        embedding_api_key=embedding_api_key,
    )

    class _EvalRequestHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _dispatch(self, method: str) -> None:
            raw_len = self.headers.get("Content-Length")
            content_len = 0
            if raw_len is not None:
                try:
                    content_len = int(raw_len)
                except ValueError:
                    err = ServiceErrorResponse(
                        status_code=400,
                        error_type="BadRequestError",
                        message="Invalid Content-Length header",
                    )
                    self._send(
                        400,
                        {"Content-Type": "application/json; charset=utf-8"},
                        err.model_dump_json().encode("utf-8"),
                    )
                    return
            if content_len > app.config.max_request_bytes:
                err = ServiceErrorResponse(
                    status_code=413,
                    error_type="PayloadTooLargeError",
                    message=(
                        f"Request Content-Length ({content_len}) exceeds "
                        f"max_request_bytes={app.config.max_request_bytes}"
                    ),
                )
                self._send(
                    413,
                    {"Content-Type": "application/json; charset=utf-8", "Connection": "close"},
                    err.model_dump_json().encode("utf-8"),
                )
                return

            body = self.rfile.read(content_len) if content_len > 0 else b""
            status, headers, resp_body = app.handle_request(
                method,
                self.path,
                body=body,
                headers=dict(self.headers.items()),
            )
            self._send(status, headers, resp_body)

        def _send(self, status: int, headers: dict[str, str], body: bytes) -> None:
            if headers.get("Connection", "").lower() == "close":
                self.close_connection = True
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            self._dispatch("GET")

        def do_POST(self) -> None:
            self._dispatch("POST")

        def do_PUT(self) -> None:
            self._dispatch("PUT")

        def do_DELETE(self) -> None:
            self._dispatch("DELETE")

        def log_message(self, format: str, *args: Any) -> None:
            _LOGGER.debug(scrub_secret_text(format % args if args else format))

    server = ThreadingHTTPServer((config.host, config.port), _EvalRequestHandler)
    server.daemon_threads = True
    return server


def serve_http(
    config: ServiceConfig,
    *,
    auth_token: str | None = None,
    judge_api_key: str | None = None,
    embedding_api_key: str | None = None,
) -> None:  # pragma: no cover - blocking serve loop tested via create_http_server
    """Start the HTTP evaluation service synchronously until interrupted."""
    server = create_http_server(
        config,
        auth_token=auth_token,
        judge_api_key=judge_api_key,
        embedding_api_key=embedding_api_key,
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()


__all__ = ["create_http_server", "serve_http"]
