"""Custom exceptions and error handling for Build Triage AI."""

from enum import Enum
from typing import Any

import structlog
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse

logger = structlog.get_logger()


class ErrorCode(str, Enum):
    """Standardized error codes for API responses."""

    # Validation errors (4xx)
    INVALID_PAYLOAD = "INVALID_PAYLOAD"
    MISSING_LOGS = "MISSING_LOGS"
    LOG_TOO_LARGE = "LOG_TOO_LARGE"
    INVALID_BUILD_STATUS = "INVALID_BUILD_STATUS"

    # Authentication errors
    INVALID_TOKEN = "INVALID_TOKEN"
    MISSING_TOKEN = "MISSING_TOKEN"

    # Rate limiting
    RATE_LIMITED = "RATE_LIMITED"

    # Analysis errors (5xx)
    ANALYSIS_FAILED = "ANALYSIS_FAILED"
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
    LLM_TIMEOUT = "LLM_TIMEOUT"
    PARSE_ERROR = "PARSE_ERROR"

    # External service errors
    GITHUB_API_ERROR = "GITHUB_API_ERROR"
    LOG_FETCH_FAILED = "LOG_FETCH_FAILED"

    # Internal errors
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"


class BuildTriageError(Exception):
    """Base exception for Build Triage errors."""

    def __init__(
        self,
        message: str,
        code: ErrorCode = ErrorCode.INTERNAL_ERROR,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to API response format."""
        return {
            "error": {
                "code": self.code.value,
                "message": self.message,
                "details": self.details,
            }
        }


class ValidationError(BuildTriageError):
    """Raised when request validation fails."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            code=ErrorCode.INVALID_PAYLOAD,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details,
        )


class LogTooLargeError(BuildTriageError):
    """Raised when log content exceeds maximum size."""

    def __init__(self, size: int, max_size: int):
        super().__init__(
            message=f"Log size ({size} bytes) exceeds maximum ({max_size} bytes)",
            code=ErrorCode.LOG_TOO_LARGE,
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            details={"size": size, "max_size": max_size},
        )


class MissingLogsError(BuildTriageError):
    """Raised when no logs are provided and cannot be fetched."""

    def __init__(self):
        super().__init__(
            message="No logs provided and logs_url fetch failed",
            code=ErrorCode.MISSING_LOGS,
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class AnalysisError(BuildTriageError):
    """Raised when build analysis fails."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            code=ErrorCode.ANALYSIS_FAILED,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details,
        )


class LLMUnavailableError(BuildTriageError):
    """Raised when LLM service is unavailable."""

    def __init__(self, provider: str = "anthropic"):
        super().__init__(
            message=f"LLM provider '{provider}' is unavailable",
            code=ErrorCode.LLM_UNAVAILABLE,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details={"provider": provider},
        )


class LLMTimeoutError(BuildTriageError):
    """Raised when LLM request times out."""

    def __init__(self, timeout: int):
        super().__init__(
            message=f"LLM request timed out after {timeout} seconds",
            code=ErrorCode.LLM_TIMEOUT,
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            details={"timeout_seconds": timeout},
        )


class ParseError(BuildTriageError):
    """Raised when LLM response cannot be parsed."""

    def __init__(self, message: str = "Failed to parse LLM response"):
        super().__init__(
            message=message,
            code=ErrorCode.PARSE_ERROR,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class GitHubAPIError(BuildTriageError):
    """Raised when GitHub API request fails."""

    def __init__(self, message: str, status_code: int = 500):
        super().__init__(
            message=message,
            code=ErrorCode.GITHUB_API_ERROR,
            status_code=status.HTTP_502_BAD_GATEWAY,
            details={"github_status": status_code},
        )


class RateLimitedError(BuildTriageError):
    """Raised when rate limit is exceeded."""

    def __init__(self, retry_after: int = 60):
        super().__init__(
            message="Rate limit exceeded",
            code=ErrorCode.RATE_LIMITED,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details={"retry_after_seconds": retry_after},
        )


async def error_handler(request: Request, exc: BuildTriageError) -> JSONResponse:
    """Global exception handler for BuildTriageError."""
    logger.error(
        "request_error",
        error_code=exc.code.value,
        message=exc.message,
        path=str(request.url.path),
        details=exc.details,
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
    )


async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handler for unexpected exceptions."""
    logger.exception(
        "unexpected_error",
        path=str(request.url.path),
        error=str(exc),
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": ErrorCode.INTERNAL_ERROR.value,
                "message": "An unexpected error occurred",
            }
        },
    )


def setup_error_handlers(app):
    """Register error handlers with FastAPI app."""
    app.add_exception_handler(BuildTriageError, error_handler)
    app.add_exception_handler(Exception, generic_error_handler)
