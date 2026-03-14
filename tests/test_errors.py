"""Tests for error handling."""

import pytest
from fastapi import status

from src.build_triage.errors import (
    AnalysisError,
    BuildTriageError,
    ErrorCode,
    GitHubAPIError,
    LLMTimeoutError,
    LLMUnavailableError,
    LogTooLargeError,
    MissingLogsError,
    ParseError,
    RateLimitedError,
    ValidationError,
)


class TestErrorCode:
    """Tests for ErrorCode enum."""

    def test_all_codes_are_strings(self):
        """Verify all error codes are strings."""
        for code in ErrorCode:
            assert isinstance(code.value, str)

    def test_validation_codes_exist(self):
        """Verify validation error codes exist."""
        assert ErrorCode.INVALID_PAYLOAD
        assert ErrorCode.MISSING_LOGS
        assert ErrorCode.LOG_TOO_LARGE

    def test_service_codes_exist(self):
        """Verify service error codes exist."""
        assert ErrorCode.LLM_UNAVAILABLE
        assert ErrorCode.LLM_TIMEOUT
        assert ErrorCode.GITHUB_API_ERROR


class TestBuildTriageError:
    """Tests for base BuildTriageError."""

    def test_default_values(self):
        """Verify default error values."""
        error = BuildTriageError("Something went wrong")

        assert error.message == "Something went wrong"
        assert error.code == ErrorCode.INTERNAL_ERROR
        assert error.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert error.details == {}

    def test_custom_values(self):
        """Verify custom error values."""
        error = BuildTriageError(
            message="Custom error",
            code=ErrorCode.RATE_LIMITED,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details={"retry_after": 60},
        )

        assert error.message == "Custom error"
        assert error.code == ErrorCode.RATE_LIMITED
        assert error.status_code == 429
        assert error.details == {"retry_after": 60}

    def test_to_dict(self):
        """Verify error dict conversion."""
        error = BuildTriageError(
            message="Test error",
            code=ErrorCode.ANALYSIS_FAILED,
            details={"build_id": "123"},
        )

        result = error.to_dict()

        assert result == {
            "error": {
                "code": "ANALYSIS_FAILED",
                "message": "Test error",
                "details": {"build_id": "123"},
            }
        }

    def test_str_representation(self):
        """Verify string representation."""
        error = BuildTriageError("Test message")
        assert str(error) == "Test message"


class TestValidationError:
    """Tests for ValidationError."""

    def test_default_code(self):
        """Verify default error code."""
        error = ValidationError("Invalid input")

        assert error.code == ErrorCode.INVALID_PAYLOAD
        assert error.status_code == status.HTTP_400_BAD_REQUEST

    def test_with_details(self):
        """Verify error with details."""
        error = ValidationError(
            "Invalid field",
            details={"field": "logs", "reason": "too short"},
        )

        assert error.details["field"] == "logs"


class TestLogTooLargeError:
    """Tests for LogTooLargeError."""

    def test_message_format(self):
        """Verify error message format."""
        error = LogTooLargeError(size=100000, max_size=50000)

        assert "100000" in error.message
        assert "50000" in error.message
        assert error.code == ErrorCode.LOG_TOO_LARGE
        assert error.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE

    def test_details(self):
        """Verify error details."""
        error = LogTooLargeError(size=75000, max_size=50000)

        assert error.details["size"] == 75000
        assert error.details["max_size"] == 50000


class TestMissingLogsError:
    """Tests for MissingLogsError."""

    def test_default_message(self):
        """Verify default error message."""
        error = MissingLogsError()

        assert "logs" in error.message.lower()
        assert error.code == ErrorCode.MISSING_LOGS
        assert error.status_code == status.HTTP_400_BAD_REQUEST


class TestAnalysisError:
    """Tests for AnalysisError."""

    def test_error_code(self):
        """Verify error code."""
        error = AnalysisError("Failed to analyze")

        assert error.code == ErrorCode.ANALYSIS_FAILED
        assert error.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestLLMErrors:
    """Tests for LLM-related errors."""

    def test_llm_unavailable(self):
        """Verify LLM unavailable error."""
        error = LLMUnavailableError()

        assert error.code == ErrorCode.LLM_UNAVAILABLE
        assert error.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert "anthropic" in error.message

    def test_llm_unavailable_custom_provider(self):
        """Verify LLM unavailable with custom provider."""
        error = LLMUnavailableError(provider="openai")

        assert "openai" in error.message

    def test_llm_timeout(self):
        """Verify LLM timeout error."""
        error = LLMTimeoutError(timeout=30)

        assert error.code == ErrorCode.LLM_TIMEOUT
        assert error.status_code == status.HTTP_504_GATEWAY_TIMEOUT
        assert "30" in error.message
        assert error.details["timeout_seconds"] == 30


class TestParseError:
    """Tests for ParseError."""

    def test_default_message(self):
        """Verify default error message."""
        error = ParseError()

        assert "parse" in error.message.lower()
        assert error.code == ErrorCode.PARSE_ERROR

    def test_custom_message(self):
        """Verify custom error message."""
        error = ParseError("JSON malformed at position 42")

        assert "JSON malformed" in error.message


class TestGitHubAPIError:
    """Tests for GitHubAPIError."""

    def test_error_code(self):
        """Verify error code."""
        error = GitHubAPIError("Rate limited by GitHub")

        assert error.code == ErrorCode.GITHUB_API_ERROR
        assert error.status_code == status.HTTP_502_BAD_GATEWAY

    def test_github_status_in_details(self):
        """Verify GitHub status in details."""
        error = GitHubAPIError("Forbidden", status_code=403)

        assert error.details["github_status"] == 403


class TestRateLimitedError:
    """Tests for RateLimitedError."""

    def test_default_retry(self):
        """Verify default retry after."""
        error = RateLimitedError()

        assert error.code == ErrorCode.RATE_LIMITED
        assert error.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert error.details["retry_after_seconds"] == 60

    def test_custom_retry(self):
        """Verify custom retry after."""
        error = RateLimitedError(retry_after=120)

        assert error.details["retry_after_seconds"] == 120
