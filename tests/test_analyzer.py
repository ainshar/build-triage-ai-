"""Tests for the build analyzer."""

import pytest

from src.build_triage.models import FailureCategory


class TestFailureCategory:
    """Tests for FailureCategory enum."""

    def test_all_categories_defined(self):
        """Verify all expected categories exist."""
        expected = [
            "code_error",
            "test_failure",
            "flaky_test",
            "dependency",
            "infrastructure",
            "timeout",
            "unknown",
        ]
        actual = [c.value for c in FailureCategory]
        assert sorted(actual) == sorted(expected)

    def test_category_from_string(self):
        """Verify categories can be created from strings."""
        assert FailureCategory("code_error") == FailureCategory.CODE_ERROR
        assert FailureCategory("flaky_test") == FailureCategory.FLAKY_TEST


class TestAnalysisResult:
    """Tests for AnalysisResult model."""

    def test_should_post_to_pr_above_threshold(self):
        """Verify posting logic for high confidence results."""
        from src.build_triage.models import AnalysisResult

        result = AnalysisResult(
            category=FailureCategory.CODE_ERROR,
            summary="Test failure",
            root_cause="Missing import",
            confidence=0.85,
        )
        assert result.should_post_to_pr(threshold=0.7) is True
        assert result.should_post_to_pr(threshold=0.9) is False

    def test_should_post_to_pr_below_threshold(self):
        """Verify posting logic for low confidence results."""
        from src.build_triage.models import AnalysisResult

        result = AnalysisResult(
            category=FailureCategory.UNKNOWN,
            summary="Unknown failure",
            root_cause="Could not determine",
            confidence=0.3,
        )
        assert result.should_post_to_pr(threshold=0.7) is False


class TestWebhookPayload:
    """Tests for WebhookPayload model."""

    def test_valid_payload(self):
        """Verify valid payload parsing."""
        from src.build_triage.models import BuildStatus, WebhookPayload

        payload = WebhookPayload(
            build_id="123",
            repo="owner/repo",
            branch="main",
            commit_sha="abc123",
            status=BuildStatus.FAILED,
        )
        assert payload.build_id == "123"
        assert payload.status == BuildStatus.FAILED
        assert payload.pr_number is None

    def test_payload_with_pr(self):
        """Verify payload with PR number."""
        from src.build_triage.models import BuildStatus, WebhookPayload

        payload = WebhookPayload(
            build_id="123",
            repo="owner/repo",
            branch="feature",
            commit_sha="abc123",
            pr_number=42,
            status=BuildStatus.FAILED,
        )
        assert payload.pr_number == 42
