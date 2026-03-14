"""Tests for the build analyzer."""

import json
import pytest
from unittest.mock import MagicMock, patch

from src.build_triage.analyzer import BuildAnalyzer, ANALYSIS_PROMPT
from src.build_triage.models import AnalysisResult, FailureCategory


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

    def test_invalid_category_raises(self):
        """Verify invalid category raises ValueError."""
        with pytest.raises(ValueError):
            FailureCategory("not_a_category")


class TestAnalysisResult:
    """Tests for AnalysisResult model."""

    def test_should_post_to_pr_above_threshold(self):
        """Verify posting logic for high confidence results."""
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
        result = AnalysisResult(
            category=FailureCategory.UNKNOWN,
            summary="Unknown failure",
            root_cause="Could not determine",
            confidence=0.3,
        )
        assert result.should_post_to_pr(threshold=0.7) is False

    def test_should_post_to_pr_at_threshold(self):
        """Verify posting logic at exact threshold."""
        result = AnalysisResult(
            category=FailureCategory.CODE_ERROR,
            summary="Error",
            root_cause="Cause",
            confidence=0.7,
        )
        assert result.should_post_to_pr(threshold=0.7) is True


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

    def test_payload_with_logs(self):
        """Verify payload with inline logs."""
        from src.build_triage.models import BuildStatus, WebhookPayload

        payload = WebhookPayload(
            build_id="123",
            repo="owner/repo",
            branch="main",
            commit_sha="abc123",
            status=BuildStatus.FAILED,
            logs="Error: Build failed",
        )
        assert payload.logs == "Error: Build failed"


class TestBuildAnalyzer:
    """Tests for BuildAnalyzer class."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = MagicMock()
        settings.anthropic_api_key = "sk-test-key"
        settings.claude_model = "claude-3-sonnet-20240229"
        settings.max_tokens = 1024
        settings.max_log_length = 50000
        return settings

    @pytest.fixture
    def analyzer(self, mock_settings):
        """Create analyzer with mock settings."""
        with patch("src.build_triage.analyzer.anthropic.Anthropic"):
            return BuildAnalyzer(settings=mock_settings)

    def test_truncate_logs_short(self, analyzer):
        """Verify short logs are not truncated."""
        logs = "Short log content"
        result = analyzer._truncate_logs(logs)
        assert result == logs

    def test_truncate_logs_long(self, analyzer):
        """Verify long logs are truncated."""
        analyzer.settings.max_log_length = 100

        # Create logs longer than max
        logs = "A" * 50 + "B" * 50 + "C" * 50  # 150 chars

        result = analyzer._truncate_logs(logs)

        assert len(result) <= 150  # Should be around max_length
        assert "TRUNCATED" in result
        assert result.startswith("A")  # Keeps beginning
        assert result.endswith("C")  # Keeps end

    def test_truncate_logs_preserves_20_80_ratio(self, analyzer):
        """Verify truncation preserves 20% beginning, 80% end."""
        analyzer.settings.max_log_length = 1000

        # Create easily identifiable sections
        logs = "BEGIN" * 500 + "END" * 500  # 5000 chars

        result = analyzer._truncate_logs(logs)

        # Beginning should have some BEGIN
        assert "BEGIN" in result[:200]
        # End should have some END
        assert "END" in result[-800:]

    def test_extract_error_context_rust(self, analyzer):
        """Verify Rust error detection."""
        logs = """
        Compiling myproject v0.1.0
        error[E0433]: failed to resolve
        error: aborting due to previous error
        """

        context = analyzer._extract_error_context(logs)

        assert "error[E0433]" in context

    def test_extract_error_context_python(self, analyzer):
        """Verify Python exception detection."""
        logs = """
        Running tests...
        Exception: ValueError raised
        Traceback (most recent call last):
        """

        context = analyzer._extract_error_context(logs)

        assert "Exception" in context

    def test_extract_error_context_npm(self, analyzer):
        """Verify NPM error detection."""
        logs = """
        npm WARN deprecated package
        npm ERR! code ERESOLVE
        npm ERR! Could not resolve dependency
        """

        context = analyzer._extract_error_context(logs)

        assert "npm ERR!" in context

    def test_extract_error_context_limits_lines(self, analyzer):
        """Verify error extraction limits to 10 lines."""
        # Create logs with 20 error lines
        error_lines = [f"ERROR: Line {i}" for i in range(20)]
        logs = "\n".join(error_lines)

        context = analyzer._extract_error_context(logs)

        # Should have at most 10 error lines
        assert context.count("ERROR:") <= 10

    def test_extract_error_context_no_errors(self, analyzer):
        """Verify empty context when no errors."""
        logs = """
        Building project...
        Compiling file1.py
        Compiling file2.py
        Build successful!
        """

        context = analyzer._extract_error_context(logs)

        assert context == ""

    def test_parse_response_valid_json(self, analyzer):
        """Verify parsing valid JSON response."""
        response = json.dumps({
            "category": "code_error",
            "summary": "Missing import",
            "root_cause": "Module not found",
            "confidence": 0.9,
        })

        result = analyzer._parse_response(response)

        assert result["category"] == "code_error"
        assert result["confidence"] == 0.9

    def test_parse_response_markdown_code_block(self, analyzer):
        """Verify parsing JSON in markdown code block."""
        response = """Here's my analysis:

```json
{
    "category": "test_failure",
    "summary": "Test failed",
    "root_cause": "Assertion error",
    "confidence": 0.85
}
```

Hope this helps!"""

        result = analyzer._parse_response(response)

        assert result["category"] == "test_failure"

    def test_parse_response_bare_json_object(self, analyzer):
        """Verify parsing bare JSON object in text."""
        response = """I analyzed the logs.
{"category": "dependency", "summary": "Missing package", "root_cause": "Not installed", "confidence": 0.8}
Let me know if you need more help."""

        result = analyzer._parse_response(response)

        assert result["category"] == "dependency"

    def test_parse_response_invalid_json_raises(self, analyzer):
        """Verify invalid JSON raises error."""
        response = "This is not JSON at all, just plain text."

        with pytest.raises(json.JSONDecodeError):
            analyzer._parse_response(response)


class TestAnalysisPrompt:
    """Tests for analysis prompt template."""

    def test_prompt_contains_categories(self):
        """Verify prompt contains all categories."""
        categories = [
            "code_error",
            "test_failure",
            "flaky_test",
            "dependency",
            "infrastructure",
            "timeout",
            "unknown",
        ]
        for cat in categories:
            assert cat in ANALYSIS_PROMPT

    def test_prompt_requests_json(self):
        """Verify prompt requests JSON output."""
        assert "JSON" in ANALYSIS_PROMPT

    def test_prompt_has_placeholders(self):
        """Verify prompt has required placeholders."""
        assert "{logs}" in ANALYSIS_PROMPT
        assert "{context_section}" in ANALYSIS_PROMPT
