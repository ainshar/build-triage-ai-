# Design Document: Build Triage AI

## Overview

Build Triage AI is an intelligent system for automatically analyzing CI/CD build failures using large language models. This document outlines the key architectural decisions, trade-offs, and design rationale.

## Design Goals

1. **Accuracy**: Correctly classify failures and provide actionable suggestions
2. **Reliability**: Handle failures gracefully, never block CI pipelines
3. **Latency**: Return results within 30 seconds for real-time feedback
4. **Observability**: Full visibility into system behavior and performance
5. **Extensibility**: Support multiple CI systems and LLM providers

## Architecture Decisions

### ADR-001: Synchronous vs Asynchronous Processing

**Decision**: Synchronous processing with background PR comment posting.

**Context**: CI webhooks expect quick responses. Long-running LLM calls could cause timeouts.

**Trade-offs**:
- ✅ Simple request/response model
- ✅ Immediate feedback to CI system
- ✅ Background tasks for non-critical work (PR comments)
- ⚠️ LLM latency directly impacts response time

**Alternatives Considered**:
- Queue-based async processing: Added complexity, delayed feedback
- Fire-and-forget: No confirmation of analysis completion

### ADR-002: Log Truncation Strategy

**Decision**: Preserve first 20% and last 80% of logs when truncating.

**Context**: Build logs can be massive (100MB+). LLM context windows are limited. Errors typically appear at the end of logs.

**Rationale**:
```
[First 20%: Build setup, dependency resolution]
...truncated...
[Last 80%: Actual compilation, tests, errors]
```

**Trade-offs**:
- ✅ Preserves most relevant error context
- ✅ Keeps initial context for understanding build setup
- ⚠️ May lose relevant warnings in the middle

### ADR-003: Confidence Thresholds

**Decision**: Multi-tier confidence system with configurable thresholds.

**Thresholds**:
| Confidence | Action |
|------------|--------|
| ≥ 0.9 | Post fix suggestion to PR |
| 0.7 - 0.9 | Post classification only |
| < 0.7 | Log internally, don't post |

**Rationale**: Avoid noisy PR comments that erode trust. Only surface high-confidence insights.

### ADR-004: Structured Prompting

**Decision**: Use XML-style structured prompts with JSON output enforcement.

**Example**:
```xml
<build_logs>
{truncated_logs}
</build_logs>

<context>
Repository: {repo}
Branch: {branch}
</context>

Respond with JSON: {"category": "...", "summary": "...", ...}
```

**Rationale**:
- XML tags clearly delineate sections
- JSON output is parseable and validatable
- Consistent format improves reliability

### ADR-005: Error Recovery Strategy

**Decision**: Graceful degradation with fallback responses.

**Error Handling Hierarchy**:
```
1. Retry with exponential backoff (transient failures)
2. Return low-confidence "unknown" result (LLM failures)
3. Return error response with details (validation failures)
4. Never crash or block the CI pipeline
```

**Implementation**:
```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
)
async def analyze(self, logs: str) -> AnalysisResult:
    try:
        # Main analysis path
    except APIError:
        # Graceful fallback
        return AnalysisResult(
            category=FailureCategory.UNKNOWN,
            confidence=0.0,
            summary="Analysis unavailable"
        )
```

### ADR-006: Observability Strategy

**Decision**: Structured logging + Prometheus metrics + OpenTelemetry traces.

**Metrics Exposed**:
| Metric | Type | Description |
|--------|------|-------------|
| `analysis_requests_total` | Counter | Total analysis requests |
| `analysis_duration_seconds` | Histogram | Analysis latency |
| `analysis_confidence` | Histogram | Confidence distribution |
| `category_classifications` | Counter | Classifications by category |
| `github_comments_posted` | Counter | PR comments posted |

**Log Structure**:
```json
{
  "timestamp": "2025-03-13T10:00:00Z",
  "level": "info",
  "event": "analysis_complete",
  "build_id": "12345",
  "category": "code_error",
  "confidence": 0.92,
  "duration_ms": 2340
}
```

## Security Considerations

### Input Validation
- All webhook payloads validated against Pydantic schemas
- Log content sanitized before LLM processing
- Maximum log length enforced (default: 50KB)

### Secrets Management
- API keys loaded from environment variables
- No secrets in logs or error messages
- GitHub tokens scoped to minimum required permissions

### Rate Limiting
- Per-repository rate limits to prevent abuse
- Exponential backoff on LLM API failures

## Performance Characteristics

### Latency Budget
| Component | Target | p99 |
|-----------|--------|-----|
| Request validation | 5ms | 10ms |
| Log processing | 50ms | 100ms |
| LLM analysis | 2000ms | 5000ms |
| GitHub posting | 200ms | 500ms |
| **Total** | **2.5s** | **6s** |

### Throughput
- Target: 100 analyses/minute
- Bottleneck: LLM API rate limits
- Mitigation: Request queuing, caching similar failures

## Future Considerations

### Planned Improvements
1. **Caching**: Cache analysis results for identical log hashes
2. **Learning**: Track fix success rates to improve suggestions
3. **Multi-provider**: Support for OpenAI, local models as fallback
4. **Batch analysis**: Aggregate similar failures across builds

### Extension Points
- `AnalysisProvider` interface for pluggable LLM backends
- `CIAdapter` interface for CI system integrations
- `NotificationChannel` interface for Slack, email, etc.

## References

- [Anthropic Claude API Documentation](https://docs.anthropic.com/)
- [Prometheus Metrics Best Practices](https://prometheus.io/docs/practices/naming/)
- [Structured Logging with structlog](https://www.structlog.org/)
