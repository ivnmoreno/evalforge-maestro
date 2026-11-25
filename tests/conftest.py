"""Global hermetic test fixtures for EvalForge Maestro."""

from __future__ import annotations

import os
import socket
import threading
from collections.abc import Iterator
from typing import Any

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register CLI flags for optional fail-closed live Lean 4 oracle conformance testing."""
    parser.addoption(
        "--lean-live-oracle",
        action="store_true",
        default=False,
        help="Run Python-to-Lean conformance checks fail-closed against the compiled Lean oracle.",
    )
    parser.addoption(
        "--lean-oracle-bin",
        action="store",
        default="formal/.lake/build/bin/evalforge-gate-oracle",
        help="Path to the compiled evalforge-gate-oracle executable used with --lean-live-oracle.",
    )


_SENSITIVE_ENV_EXACT: tuple[str, ...] = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "AZURE_API_KEY",
    "COHERE_API_KEY",
    "MISTRAL_API_KEY",
    "GROQ_API_KEY",
    "TOGETHER_API_KEY",
    "LITELLM_API_KEY",
    "HUGGINGFACE_API_KEY",
    "HF_TOKEN",
)


@pytest.fixture(autouse=True)
def _hermetic_isolation(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Clear EVALFORGE_*/provider env vars and block outbound INET sockets by default."""
    for key in list(os.environ):
        if key.startswith("EVALFORGE_") or key in _SENSITIVE_ENV_EXACT:
            monkeypatch.delenv(key, raising=False)

    orig_connect = socket.socket.connect
    orig_connect_ex = socket.socket.connect_ex
    orig_socketpair = socket.socketpair
    socketpair_state = threading.local()

    def _in_socketpair() -> bool:
        return int(getattr(socketpair_state, "depth", 0)) > 0

    def _allowed_socketpair(*args: Any, **kwargs: Any) -> tuple[socket.socket, socket.socket]:
        # On Windows, asyncio ProactorEventLoop self-pipes call socketpair() over AF_INET loopback.
        depth = int(getattr(socketpair_state, "depth", 0))
        socketpair_state.depth = depth + 1
        try:
            return orig_socketpair(*args, **kwargs)
        finally:
            socketpair_state.depth = depth

    def _blocked_connect(self: socket.socket, address: Any) -> Any:
        if self.family in (socket.AF_INET, socket.AF_INET6) and not _in_socketpair():
            raise RuntimeError(
                f"Outbound network connection blocked in hermetic test suite: {address!r}"
            )
        return orig_connect(self, address)

    def _blocked_connect_ex(self: socket.socket, address: Any) -> int:
        if self.family in (socket.AF_INET, socket.AF_INET6) and not _in_socketpair():
            raise RuntimeError(
                f"Outbound network connection blocked in hermetic test suite: {address!r}"
            )
        return orig_connect_ex(self, address)

    def _blocked_create_connection(*args: Any, **kwargs: Any) -> socket.socket:
        raise RuntimeError(
            f"Outbound socket.create_connection blocked in hermetic test suite: {args!r}"
        )

    monkeypatch.setattr(socket, "socketpair", _allowed_socketpair)
    monkeypatch.setattr(socket.socket, "connect", _blocked_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", _blocked_connect_ex)
    monkeypatch.setattr(socket, "create_connection", _blocked_create_connection)
    yield
