"""Build log analyzer using Claude API."""

import json
import re

import anthropic
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import Settings, get_settings
from .models import AnalysisResult, FailureCategory, FixSuggestion

logger = structlog.get_logger()

ANALYSIS_PROMPT = """You are an expert CI/CD engineer analyzing build failure logs.
Analyze the following build logs and provide a structured diagnosis.

<build_logs>
{logs}
</build_logs>

{context_section}

Analyze the logs and respond with a JSON object containing:
1. "category": One of: code_error, test_failure, flaky_test, dependency, infrastructure, timeout, unknown
2. "summary": A brief one-line summary of the failure (max 100 chars)
3. "root_cause": Detailed explanation of the root cause
4. "suggestions": Array of fix suggestions, each with:
   - "description": What to do to fix it
   - "code_snippet": Example code if applicable (or null)
   - "file_path": File to modify if known (or null)
   - "confidence": 0-1 confidence in this suggestion
5. "confidence": Overall confidence in your analysis (0-1)
6. "relevant_lines": Array of the most relevant log lines (max 5)

Focus on:
- Identifying the actual error vs symptoms
- Distinguishing between code issues and infrastructure problems
- Recognizing flaky test patterns (race conditions, timing issues)
- Providing actionable fix suggestions

Respond ONLY with valid JSON, no other text."""


class BuildAnalyzer:
    """Analyzes build logs using Claude to identify failures and suggest fixes."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.client = anthropic.Anthropic(api_key=self.settings.anthropic_api_key)

    def _truncate_logs(self, logs: str) -> str:
        """Truncate logs to maximum length, keeping most relevant parts."""
        max_length = self.settings.max_log_length

        if len(logs) <= max_length:
            return logs

        # Keep first 20% and last 80% (errors usually at end)
        first_part = int(max_length * 0.2)
        last_part = max_length - first_part - 50  # 50 chars for truncation message

        truncated = (
            logs[:first_part]
            + "\n\n... [TRUNCATED - showing last portion] ...\n\n"
            + logs[-last_part:]
        )
        return truncated

    def _extract_error_context(self, logs: str) -> str:
        """Extract additional context from logs like error patterns."""
        patterns = [
            r"error\[E\d+\]:",  # Rust errors
            r"ERROR:",  # Generic errors
            r"FAILED",  # Test failures
            r"Exception:",  # Python exceptions
            r"error:",  # Generic lowercase
            r"npm ERR!",  # NPM errors
            r"FATAL:",  # Fatal errors
        ]

        error_lines = []
        for line in logs.split("\n"):
            for pattern in patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    error_lines.append(line.strip())
                    break

        if error_lines:
            return "Key error lines detected:\n" + "\n".join(error_lines[:10])
        return ""

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def analyze(
        self,
        logs: str,
        build_id: str | None = None,
        context: str | None = None,
    ) -> AnalysisResult:
        """
        Analyze build logs and return diagnosis.

        Args:
            logs: Build logs to analyze
            build_id: Optional build identifier
            context: Optional additional context

        Returns:
            AnalysisResult with diagnosis and suggestions
        """
        log = logger.bind(build_id=build_id)
        log.info("analyzing_build_logs", log_length=len(logs))

        # Prepare logs
        truncated_logs = self._truncate_logs(logs)
        error_context = self._extract_error_context(logs)

        # Build context section
        context_parts = []
        if context:
            context_parts.append(f"Additional context: {context}")
        if error_context:
            context_parts.append(error_context)

        context_section = ""
        if context_parts:
            context_section = "<context>\n" + "\n".join(context_parts) + "\n</context>\n"

        # Build prompt
        prompt = ANALYSIS_PROMPT.format(
            logs=truncated_logs,
            context_section=context_section,
        )

        # Call Claude
        try:
            response = self.client.messages.create(
                model=self.settings.claude_model,
                max_tokens=self.settings.max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )

            # Parse response
            response_text = response.content[0].text
            log.debug("claude_response", response=response_text[:500])

            # Extract JSON from response
            result_data = self._parse_response(response_text)

            # Build result
            suggestions = [
                FixSuggestion(
                    description=s.get("description", ""),
                    code_snippet=s.get("code_snippet"),
                    file_path=s.get("file_path"),
                    confidence=s.get("confidence", 0.5),
                )
                for s in result_data.get("suggestions", [])
            ]

            result = AnalysisResult(
                build_id=build_id,
                category=FailureCategory(result_data.get("category", "unknown")),
                summary=result_data.get("summary", "Analysis failed"),
                root_cause=result_data.get("root_cause", "Unable to determine root cause"),
                suggestions=suggestions,
                confidence=result_data.get("confidence", 0.5),
                relevant_lines=result_data.get("relevant_lines", [])[:5],
            )

            log.info(
                "analysis_complete",
                category=result.category,
                confidence=result.confidence,
                suggestions_count=len(result.suggestions),
            )

            return result

        except anthropic.APIError as e:
            log.error("claude_api_error", error=str(e))
            raise
        except json.JSONDecodeError as e:
            log.error("json_parse_error", error=str(e))
            # Return a basic result on parse failure
            return AnalysisResult(
                build_id=build_id,
                category=FailureCategory.UNKNOWN,
                summary="Failed to parse analysis",
                root_cause="Analysis response could not be parsed",
                confidence=0.0,
            )

    def _parse_response(self, response_text: str) -> dict:
        """Parse JSON from Claude response, handling potential formatting issues."""
        # Try direct parse first
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            pass

        # Try to extract JSON from markdown code blocks
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", response_text)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find JSON object in response
        brace_match = re.search(r"\{[\s\S]*\}", response_text)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        raise json.JSONDecodeError("Could not extract JSON from response", response_text, 0)
