"""Base error hierarchy for GEF AI Data Quality Bus."""


class BaseError(Exception):
    """Base error with structured context."""

    def __init__(
        self,
        code: str,
        message: str,
        context: dict | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.context = context or {}
        self.cause = cause

    def __str__(self) -> str:
        base = f"[{self.code}] {self.message}"
        if self.context:
            base += f" | context={self.context}"
        if self.cause:
            base += f" | cause={self.cause}"
        return base


class ValidationError(BaseError):
    """Invalid input, proto syntax, schema violations."""


class NotFoundError(BaseError):
    """Proto file not found, missing field reference."""


class DataAccessError(BaseError):
    """ChromaDB failures, file system errors."""


class ProcessingError(BaseError):
    """LLM API failures, agent pipeline errors."""
