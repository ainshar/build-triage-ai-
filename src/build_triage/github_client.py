"""GitHub API client for posting PR comments."""

import httpx
import structlog

from .config import Settings, get_settings
from .models import AnalysisResult, PRComment

logger = structlog.get_logger()

PR_COMMENT_TEMPLATE = """## 🔍 Build Failure Analysis

**Category:** `{category}`
**Confidence:** {confidence:.0%}

### Summary
{summary}

### Root Cause
{root_cause}

{suggestions_section}

{relevant_lines_section}

---
<sub>🤖 Analyzed by Build Triage AI</sub>
"""


class GitHubClient:
    """Client for interacting with GitHub API."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.base_url = "https://api.github.com"
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.settings.github_token}",
                    "Accept": "application/vnd.github.v3+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def format_comment(self, result: AnalysisResult) -> str:
        """Format analysis result as a PR comment."""
        # Format suggestions
        suggestions_section = ""
        if result.suggestions:
            suggestions_lines = ["### Suggested Fixes"]
            for i, suggestion in enumerate(result.suggestions, 1):
                suggestions_lines.append(
                    f"\n**{i}. {suggestion.description}** "
                    f"(confidence: {suggestion.confidence:.0%})"
                )
                if suggestion.file_path:
                    suggestions_lines.append(f"   - File: `{suggestion.file_path}`")
                if suggestion.code_snippet:
                    suggestions_lines.append(f"   ```\n   {suggestion.code_snippet}\n   ```")
            suggestions_section = "\n".join(suggestions_lines)

        # Format relevant lines
        relevant_lines_section = ""
        if result.relevant_lines:
            lines = "\n".join(f"  {line}" for line in result.relevant_lines)
            relevant_lines_section = f"### Relevant Log Lines\n```\n{lines}\n```"

        return PR_COMMENT_TEMPLATE.format(
            category=result.category.value,
            confidence=result.confidence,
            summary=result.summary,
            root_cause=result.root_cause,
            suggestions_section=suggestions_section,
            relevant_lines_section=relevant_lines_section,
        )

    async def post_pr_comment(
        self,
        repo: str,
        pr_number: int,
        result: AnalysisResult,
    ) -> bool:
        """
        Post analysis result as a comment on a PR.

        Args:
            repo: Repository in owner/repo format
            pr_number: PR number
            result: Analysis result to post

        Returns:
            True if comment was posted successfully
        """
        log = logger.bind(repo=repo, pr_number=pr_number)

        if not self.settings.github_token:
            log.warning("github_token_not_configured")
            return False

        if not result.should_post_to_pr(self.settings.confidence_threshold):
            log.info(
                "skipping_pr_comment_low_confidence",
                confidence=result.confidence,
                threshold=self.settings.confidence_threshold,
            )
            return False

        try:
            client = await self._get_client()
            body = self.format_comment(result)

            response = await client.post(
                f"/repos/{repo}/issues/{pr_number}/comments",
                json={"body": body},
            )

            if response.status_code == 201:
                log.info("pr_comment_posted", comment_url=response.json().get("html_url"))
                return True
            else:
                log.error(
                    "pr_comment_failed",
                    status_code=response.status_code,
                    response=response.text,
                )
                return False

        except httpx.HTTPError as e:
            log.error("github_api_error", error=str(e))
            return False

    async def fetch_logs_from_url(self, logs_url: str) -> str | None:
        """
        Fetch build logs from a URL.

        Args:
            logs_url: URL to fetch logs from

        Returns:
            Log content or None if fetch failed
        """
        log = logger.bind(logs_url=logs_url)

        try:
            client = await self._get_client()
            response = await client.get(logs_url)

            if response.status_code == 200:
                return response.text
            else:
                log.error("fetch_logs_failed", status_code=response.status_code)
                return None

        except httpx.HTTPError as e:
            log.error("fetch_logs_error", error=str(e))
            return None
