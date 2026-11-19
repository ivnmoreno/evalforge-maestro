"""Cold-start-safe CLI entrypoint package for evalforge-maestro."""

from __future__ import annotations

from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    """Execute the evalforge-maestro CLI and return a deterministic POSIX exit code."""
    from evalforge_maestro.cli.parser import parse_and_dispatch

    return parse_and_dispatch(argv)


__all__ = ["main"]
