"""Data models for Build Triage AI."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class FailureCategory(str, Enum):
    """Categories of build failures."""

    CODE_ERROR = "code_error"
    TEST_FAILURE = "test_failure"
    FLAKY_TEST = "flaky_test"
    DEPENDENCY = "dependency"
    INFRASTRUCTURE = "infrastructure"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


class BuildStatus(str, Enum):
    """Build status values."""

    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PENDING = "pending"


class WebhookPayload(BaseModel):
    """Incoming webhook payload from CI systems."""

    build_id: str = Field(..., description="Unique build identifier")
    repo: str = Field(..., description="Repository in owner/repo format")
    branch: str = Field(..., description="Branch name")
    commit_sha: str = Field(..., description="Commit SHA")
    pr_number: int | None = Field(None, description="PR number if applicable")
    status: BuildStatus = Field(..., description="Build status")
    logs_url: str | None = Field(None, description="URL to fetch build logs")
    logs: str | None = Field(None, description="Inline build logs")
    triggered_by: str | None = Field(None, description="User who triggered the build")
    ci_system: str | None = Field(None, description="CI system name")


class AnalyzeRequest(BaseModel):
    """Request for manual log analysis."""

    logs: str = Field(..., description="Build logs to analyze", max_length=100000)
    context: str | None = Field(None, description="Additional context about the build")


class FixSuggestion(BaseModel):
    """A suggested fix for the build failure."""

    description: str = Field(..., description="Description of the fix")
    code_snippet: str | None = Field(None, description="Example code fix")
    file_path: str | None = Field(None, description="File that needs to be modified")
    confidence: float = Field(..., ge=0, le=1, description="Confidence in this suggestion")


class AnalysisResult(BaseModel):
    """Result of analyzing build logs."""

    build_id: str | None = Field(None, description="Build identifier if from webhook")
    category: FailureCategory = Field(..., description="Failure category")
    summary: str = Field(..., description="Brief summary of the failure")
    root_cause: str = Field(..., description="Identified root cause")
    suggestions: list[FixSuggestion] = Field(default_factory=list, description="Suggested fixes")
    confidence: float = Field(..., ge=0, le=1, description="Overall confidence in analysis")
    relevant_lines: list[str] = Field(
        default_factory=list, description="Most relevant log lines"
    )
    analyzed_at: datetime = Field(default_factory=datetime.utcnow)

    def should_post_to_pr(self, threshold: float = 0.7) -> bool:
        """Determine if analysis should be posted to PR based on confidence."""
        return self.confidence >= threshold


class PRComment(BaseModel):
    """Comment to post to a PR."""

    repo: str
    pr_number: int
    body: str


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    version: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
