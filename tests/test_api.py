"""Tests for FastAPI endpoints."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from src.build_triage.main import app
from src.build_triage.models import AnalysisResult, FailureCategory


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    def test_health_returns_ok(self, client):
        """Verify health endpoint returns OK status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "timestamp" in data


class TestAnalyzeEndpoint:
    """Tests for manual analysis endpoint."""

    @patch("src.build_triage.main.analyzer")
    def test_analyze_valid_logs(self, mock_analyzer, client):
        """Verify analyze endpoint with valid logs."""
        mock_result = AnalysisResult(
            category=FailureCategory.CODE_ERROR,
            summary="Missing import statement",
            root_cause="ModuleNotFoundError: No module named 'foo'",
            confidence=0.92,
            suggestions=[],
            relevant_lines=["ImportError: No module named 'foo'"],
        )
        mock_analyzer.analyze = AsyncMock(return_value=mock_result)

        response = client.post(
            "/analyze",
            json={
                "logs": "error: ModuleNotFoundError: No module named 'foo'",
                "context": "Python build",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["category"] == "code_error"
        assert data["confidence"] == 0.92

    def test_analyze_empty_logs_rejected(self, client):
        """Verify empty logs are rejected."""
        response = client.post("/analyze", json={"logs": ""})
        assert response.status_code == 422  # Validation error

    def test_analyze_logs_too_long_rejected(self, client):
        """Verify logs exceeding max length are rejected."""
        # Model has max_length=100000
        response = client.post("/analyze", json={"logs": "x" * 100001})
        assert response.status_code == 422


class TestWebhookEndpoint:
    """Tests for webhook endpoint."""

    @patch("src.build_triage.main.analyzer")
    @patch("src.build_triage.main.github_client")
    def test_webhook_with_inline_logs(self, mock_gh, mock_analyzer, client):
        """Verify webhook processes inline logs."""
        mock_result = AnalysisResult(
            category=FailureCategory.TEST_FAILURE,
            summary="Test assertion failed",
            root_cause="Expected 5 but got 4",
            confidence=0.85,
        )
        mock_analyzer.analyze = AsyncMock(return_value=mock_result)
        mock_gh.post_pr_comment = AsyncMock(return_value=True)

        response = client.post(
            "/webhook/build-failure",
            json={
                "build_id": "build-123",
                "repo": "owner/repo",
                "branch": "main",
                "commit_sha": "abc123def",
                "status": "failed",
                "logs": "FAILED test_math.py::test_add - assert 4 == 5",
                "pr_number": 42,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["category"] == "test_failure"

    def test_webhook_invalid_status_rejected(self, client):
        """Verify invalid build status is rejected."""
        response = client.post(
            "/webhook/build-failure",
            json={
                "build_id": "build-123",
                "repo": "owner/repo",
                "branch": "main",
                "commit_sha": "abc123",
                "status": "invalid_status",
            },
        )
        assert response.status_code == 422

    def test_webhook_missing_required_fields(self, client):
        """Verify missing required fields are rejected."""
        response = client.post(
            "/webhook/build-failure",
            json={"build_id": "123"},  # Missing repo, branch, commit_sha, status
        )
        assert response.status_code == 422


class TestMetricsEndpoint:
    """Tests for metrics endpoint."""

    def test_metrics_returns_prometheus_format(self, client):
        """Verify metrics endpoint returns Prometheus format."""
        response = client.get("/metrics")
        assert response.status_code == 200
        # Should return text content
        assert response.headers.get("content-type", "").startswith("text/plain")
