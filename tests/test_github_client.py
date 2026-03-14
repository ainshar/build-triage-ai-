"""Tests for GitHub client."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.build_triage.github_client import GitHubClient, PR_COMMENT_TEMPLATE
from src.build_triage.models import AnalysisResult, FailureCategory, FixSuggestion


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    settings = MagicMock()
    settings.github_token = "ghp_test_token"
    settings.confidence_threshold = 0.7
    return settings


@pytest.fixture
def github_client(mock_settings):
    """Create GitHub client with mock settings."""
    return GitHubClient(settings=mock_settings)


class TestFormatComment:
    """Tests for comment formatting."""

    def test_format_comment_basic(self, github_client):
        """Verify basic comment formatting."""
        result = AnalysisResult(
            category=FailureCategory.CODE_ERROR,
            summary="Missing import",
            root_cause="Module 'requests' not found",
            confidence=0.9,
        )

        comment = github_client.format_comment(result)

        assert "code_error" in comment
        assert "90%" in comment
        assert "Missing import" in comment
        assert "Module 'requests' not found" in comment
        assert "Build Triage AI" in comment

    def test_format_comment_with_suggestions(self, github_client):
        """Verify comment formatting with suggestions."""
        result = AnalysisResult(
            category=FailureCategory.DEPENDENCY,
            summary="Missing dependency",
            root_cause="Package not installed",
            confidence=0.85,
            suggestions=[
                FixSuggestion(
                    description="Add requests to requirements.txt",
                    code_snippet="requests>=2.28.0",
                    file_path="requirements.txt",
                    confidence=0.9,
                ),
                FixSuggestion(
                    description="Run pip install",
                    code_snippet=None,
                    file_path=None,
                    confidence=0.8,
                ),
            ],
        )

        comment = github_client.format_comment(result)

        assert "Suggested Fixes" in comment
        assert "Add requests to requirements.txt" in comment
        assert "requirements.txt" in comment
        assert "requests>=2.28.0" in comment
        assert "Run pip install" in comment

    def test_format_comment_with_relevant_lines(self, github_client):
        """Verify comment formatting with relevant log lines."""
        result = AnalysisResult(
            category=FailureCategory.TEST_FAILURE,
            summary="Test failed",
            root_cause="Assertion error",
            confidence=0.95,
            relevant_lines=[
                "FAILED test_math.py::test_add",
                "AssertionError: assert 4 == 5",
            ],
        )

        comment = github_client.format_comment(result)

        assert "Relevant Log Lines" in comment
        assert "FAILED test_math.py::test_add" in comment
        assert "AssertionError" in comment


class TestPostPRComment:
    """Tests for PR comment posting."""

    @pytest.mark.asyncio
    async def test_skip_low_confidence(self, github_client):
        """Verify low confidence results are not posted."""
        result = AnalysisResult(
            category=FailureCategory.UNKNOWN,
            summary="Unknown failure",
            root_cause="Could not determine",
            confidence=0.3,  # Below 0.7 threshold
        )

        posted = await github_client.post_pr_comment("owner/repo", 42, result)

        assert posted is False

    @pytest.mark.asyncio
    async def test_skip_when_no_token(self):
        """Verify posting skipped when no GitHub token."""
        settings = MagicMock()
        settings.github_token = None
        settings.confidence_threshold = 0.7

        client = GitHubClient(settings=settings)
        result = AnalysisResult(
            category=FailureCategory.CODE_ERROR,
            summary="Error",
            root_cause="Cause",
            confidence=0.9,
        )

        posted = await client.post_pr_comment("owner/repo", 42, result)

        assert posted is False

    @pytest.mark.asyncio
    async def test_post_success(self, github_client):
        """Verify successful comment posting."""
        result = AnalysisResult(
            category=FailureCategory.CODE_ERROR,
            summary="Missing import",
            root_cause="ModuleNotFoundError",
            confidence=0.9,
        )

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "html_url": "https://github.com/owner/repo/pull/42#comment-1"
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        with patch.object(
            github_client, "_get_client", return_value=mock_client
        ):
            posted = await github_client.post_pr_comment("owner/repo", 42, result)

        assert posted is True
        mock_client.post.assert_called_once()


class TestFetchLogsFromUrl:
    """Tests for fetching logs from URL."""

    @pytest.mark.asyncio
    async def test_fetch_logs_success(self, github_client):
        """Verify successful log fetching."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Build log content here..."

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        with patch.object(
            github_client, "_get_client", return_value=mock_client
        ):
            logs = await github_client.fetch_logs_from_url(
                "https://ci.example.com/builds/123/logs"
            )

        assert logs == "Build log content here..."

    @pytest.mark.asyncio
    async def test_fetch_logs_failure(self, github_client):
        """Verify handling of fetch failure."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        with patch.object(
            github_client, "_get_client", return_value=mock_client
        ):
            logs = await github_client.fetch_logs_from_url(
                "https://ci.example.com/builds/invalid/logs"
            )

        assert logs is None
