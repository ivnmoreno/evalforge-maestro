"""Exception hierarchy for EvalForge Maestro."""

from __future__ import annotations


class EvalforgeError(Exception):
    """Base exception for all EvalForge Maestro errors."""


class ConfigurationError(EvalforgeError):
    """Raised when configuration values or options are invalid."""


class MissingExtraError(EvalforgeError):
    """Raised when an optional capability extra is required but not installed."""

    def __init__(
        self,
        message: str | None = None,
        *,
        extra: str | None = None,
        package: str | None = None,
    ) -> None:
        if message is None:
            pkg_hint = f" ({package})" if package else ""
            if extra:
                message = (
                    f"Optional dependency{pkg_hint} requires extra '[{extra}]'. "
                    f"Install with: pip install 'evalforge-maestro[{extra}]'"
                )
            else:
                message = f"Required optional dependency{pkg_hint} is not installed."
        super().__init__(message)
        self.extra = extra
        self.package = package


class DatasetError(EvalforgeError):
    """Raised when a dataset fails boundary parsing or schema validation."""

    def __init__(
        self,
        message: str,
        *,
        line_number: int | None = None,
        case_id: str | None = None,
        field: str | None = None,
    ) -> None:
        super().__init__(message)
        self.line_number = line_number
        self.case_id = case_id
        self.field = field


class EmptyDatasetError(DatasetError):
    """Raised when a dataset contains zero valid evaluation cases."""


class DuplicateCaseIdError(DatasetError):
    """Raised when a dataset contains a duplicate EvaluationCase identifier."""


class AdapterError(EvalforgeError):
    """Raised when a target adapter encounters an invalid configuration or boundary fault."""


class MetricError(EvalforgeError):
    """Raised when a metric configuration or evaluation contract fails."""


class ExecutionError(EvalforgeError):
    """Raised when evaluation orchestration cannot proceed safely."""


class MemoryLimitExceededError(ExecutionError):
    """Raised when resident memory exceeds configured soft-cap with abort policy."""


class StorageError(EvalforgeError):
    """Raised when local artifact persistence or path validation fails."""


class ImmutabilityError(StorageError):
    """Raised when attempting to overwrite or mutate an immutable committed run artifact."""
