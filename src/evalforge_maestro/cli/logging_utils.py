"""CLI stderr-only logging helpers supporting human plain and --log-json telemetry."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import TextIO

from evalforge_maestro._canonical import scrub_secret_text


class _SecretScrubbingFormatter(logging.Formatter):
    def __init__(self, *, json_mode: bool) -> None:
        super().__init__()
        self._json_mode = json_mode

    def format(self, record: logging.LogRecord) -> str:
        msg = scrub_secret_text(record.getMessage())
        if record.exc_info:
            exc_text = scrub_secret_text(self.formatException(record.exc_info))
            msg = f"{msg}\n{exc_text}"
        if self._json_mode:
            payload = {
                "timestamp": datetime.now(UTC).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": msg,
            }
            return json.dumps(payload, ensure_ascii=False, allow_nan=False)
        return f"[{record.levelname}] {msg}"


class CLIStructuredLogger:
    """Isolated CLI logger streaming diagnostics solely to stderr without mutating root logger."""

    def __init__(
        self,
        *,
        level: str = "WARNING",
        log_json: bool = False,
        stream: TextIO | None = None,
    ) -> None:
        self._stream = stream if stream is not None else sys.stderr
        self._log_json = log_json
        self._level_name = level.upper()
        self._level = getattr(logging, self._level_name, logging.WARNING)
        self._formatter = _SecretScrubbingFormatter(json_mode=log_json)

    @property
    def stream(self) -> TextIO:
        """Return target diagnostic output stream (stderr by default)."""
        return self._stream

    def configure(self, *, level: str, log_json: bool) -> None:
        """Update severity threshold and JSON mode cleanly after config resolution."""
        self._level_name = level.upper()
        self._level = getattr(logging, self._level_name, logging.WARNING)
        self._log_json = log_json
        self._formatter = _SecretScrubbingFormatter(json_mode=log_json)

    def log(self, level: int, message: str) -> None:
        """Write one scrubbed diagnostic log line to stderr if level >= configured threshold."""
        if level < self._level:
            return
        record = logging.LogRecord(
            name="evalforge_maestro.cli",
            level=level,
            pathname="cli",
            lineno=0,
            msg=message,
            args=(),
            exc_info=None,
        )
        rendered = self._formatter.format(record)
        self._stream.write(rendered + "\n")
        self._stream.flush()

    def debug(self, message: str) -> None:
        """Emit DEBUG telemetry to stderr."""
        self.log(logging.DEBUG, message)

    def info(self, message: str) -> None:
        """Emit INFO telemetry to stderr."""
        self.log(logging.INFO, message)

    def warning(self, message: str) -> None:
        """Emit WARNING telemetry to stderr."""
        self.log(logging.WARNING, message)

    def error(self, message: str) -> None:
        """Emit ERROR diagnostic to stderr."""
        self.log(logging.ERROR, message)
