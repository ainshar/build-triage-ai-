"""Shared test fixtures and configuration."""

import pytest
from unittest.mock import MagicMock, AsyncMock

from src.build_triage.models import AnalysisResult, FailureCategory, FixSuggestion


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    settings = MagicMock()
    settings.anthropic_api_key = "sk-ant-test-key"
    settings.github_token = "ghp_test_token"
    settings.claude_model = "claude-3-sonnet-20240229"
    settings.max_tokens = 1024
    settings.max_log_length = 50000
    settings.confidence_threshold = 0.7
    settings.host = "0.0.0.0"
    settings.port = 8000
    settings.debug = False
    return settings


@pytest.fixture
def sample_analysis_result():
    """Create a sample analysis result for testing."""
    return AnalysisResult(
        build_id="test-build-123",
        category=FailureCategory.CODE_ERROR,
        summary="Missing import statement",
        root_cause="The module 'requests' is not installed",
        suggestions=[
            FixSuggestion(
                description="Add requests to requirements.txt",
                code_snippet="requests>=2.28.0",
                file_path="requirements.txt",
                confidence=0.9,
            ),
        ],
        confidence=0.85,
        relevant_lines=[
            "ModuleNotFoundError: No module named 'requests'",
            "  File 'main.py', line 1, in <module>",
        ],
    )


@pytest.fixture
def sample_low_confidence_result():
    """Create a low confidence analysis result."""
    return AnalysisResult(
        category=FailureCategory.UNKNOWN,
        summary="Unable to determine failure cause",
        root_cause="Log content is insufficient for analysis",
        confidence=0.3,
    )


@pytest.fixture
def sample_build_logs():
    """Create sample build logs for testing."""
    return """
Building project...
Installing dependencies...
npm install
npm WARN deprecated request@2.88.2

Running tests...
FAIL src/tests/test_math.py::test_addition
  AssertionError: assert 4 == 5

  Expected: 5
  Got: 4

ERROR: 1 failed, 23 passed
Build failed with exit code 1
"""


@pytest.fixture
def sample_rust_error_logs():
    """Create sample Rust error logs."""
    return """
   Compiling myproject v0.1.0 (/home/user/project)
error[E0433]: failed to resolve: use of undeclared crate or module `tokio`
 --> src/main.rs:1:5
  |
1 | use tokio::runtime::Runtime;
  |     ^^^^^ use of undeclared crate or module `tokio`

error: aborting due to previous error

For more information about this error, try `rustc --explain E0433`.
error: could not compile `myproject`
"""


@pytest.fixture
def mock_anthropic_response():
    """Create mock Anthropic API response."""
    response = MagicMock()
    response.content = [
        MagicMock(
            text='{"category": "test_failure", "summary": "Test assertion failed", '
            '"root_cause": "Expected value mismatch", "confidence": 0.9, '
            '"suggestions": [], "relevant_lines": ["assert 4 == 5"]}'
        )
    ]
    return response


@pytest.fixture
def mock_analyzer(mock_settings, sample_analysis_result):
    """Create mock BuildAnalyzer."""
    analyzer = MagicMock()
    analyzer.analyze = AsyncMock(return_value=sample_analysis_result)
    analyzer._truncate_logs = MagicMock(side_effect=lambda x: x)
    analyzer._extract_error_context = MagicMock(return_value="")
    return analyzer


@pytest.fixture
def mock_github_client(mock_settings):
    """Create mock GitHubClient."""
    client = MagicMock()
    client.post_pr_comment = AsyncMock(return_value=True)
    client.fetch_logs_from_url = AsyncMock(return_value="Sample logs from URL")
    client.format_comment = MagicMock(return_value="## Analysis Comment")
    return client
