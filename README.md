# Build Triage AI

AI-powered CI/CD build failure triage system that uses Claude to analyze build logs, classify root causes, and suggest fixes automatically.

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              Build Triage AI                                  │
└──────────────────────────────────────────────────────────────────────────────┘

                    ┌─────────────────────────────────┐
                    │        CI/CD Systems            │
                    │  (GitHub Actions, Jenkins, etc) │
                    └───────────────┬─────────────────┘
                                    │
                                    ▼ Webhook (POST /webhook/build-failure)
                    ┌─────────────────────────────────┐
                    │         FastAPI Server          │
                    │  ┌───────────────────────────┐  │
                    │  │    Request Validation     │  │
                    │  │    Rate Limiting          │  │
                    │  │    Authentication         │  │
                    │  └───────────────────────────┘  │
                    └───────────────┬─────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
                    ▼                               ▼
    ┌───────────────────────────┐   ┌───────────────────────────┐
    │      Log Processor        │   │     Metrics Collector     │
    │  ┌─────────────────────┐  │   │  ┌─────────────────────┐  │
    │  │ Truncation          │  │   │  │ Request count       │  │
    │  │ Error extraction    │  │   │  │ Latency (p50/p99)   │  │
    │  │ Context enrichment  │  │   │  │ Error rate          │  │
    │  └─────────────────────┘  │   │  │ Analysis confidence │  │
    └───────────────┬───────────┘   │  └─────────────────────┘  │
                    │               └───────────────────────────┘
                    ▼
    ┌───────────────────────────────────────────────────────────┐
    │                    Build Analyzer                          │
    │  ┌─────────────────────────────────────────────────────┐  │
    │  │                  Claude API                          │  │
    │  │  • Structured prompting for consistent output        │  │
    │  │  • JSON schema enforcement                           │  │
    │  │  • Retry with exponential backoff                    │  │
    │  └─────────────────────────────────────────────────────┘  │
    │  ┌─────────────────────────────────────────────────────┐  │
    │  │              Response Parser                         │  │
    │  │  • JSON extraction from markdown                     │  │
    │  │  • Schema validation                                 │  │
    │  │  • Fallback handling                                 │  │
    │  └─────────────────────────────────────────────────────┘  │
    └───────────────┬───────────────────────────────────────────┘
                    │
                    ▼
    ┌───────────────────────────────────────────────────────────┐
    │                   Analysis Result                          │
    │  {                                                         │
    │    "category": "code_error | test_failure | flaky_test",  │
    │    "summary": "Brief description",                         │
    │    "root_cause": "Detailed explanation",                   │
    │    "suggestions": [...],                                   │
    │    "confidence": 0.85                                      │
    │  }                                                         │
    └───────────────┬───────────────────────────────────────────┘
                    │
                    ▼
    ┌───────────────────────────────────────────────────────────┐
    │                  GitHub Client                             │
    │  ┌─────────────────────────────────────────────────────┐  │
    │  │ Confidence threshold check (default: 0.7)           │  │
    │  │ Markdown comment formatting                          │  │
    │  │ PR comment posting via GitHub API                    │  │
    │  └─────────────────────────────────────────────────────┘  │
    └───────────────────────────────────────────────────────────┘
```

## Features

- **Webhook Integration**: Receives build failure notifications from CI systems
- **Intelligent Analysis**: Uses Claude to analyze build logs and identify root causes
- **Classification**: Categorizes failures into actionable categories
- **Fix Suggestions**: Provides code suggestions with confidence scores
- **PR Comments**: Automatically posts diagnosis to GitHub PRs
- **Observability**: Structured logging, metrics, and tracing support

## Quick Start

### Prerequisites

- Python 3.11+
- Anthropic API key
- GitHub token (optional, for PR comments)

### Installation

```bash
# Clone the repository
git clone https://github.com/ainshar/build-triage-ai-.git
cd build-triage-ai-

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Copy environment template
cp .env.example .env
# Edit .env with your API keys
```

### Configuration

```env
# Required
ANTHROPIC_API_KEY=sk-ant-...

# Optional - for PR comments
GITHUB_TOKEN=ghp_...

# Analysis settings
CONFIDENCE_THRESHOLD=0.7
MAX_LOG_LENGTH=50000

# Claude settings
CLAUDE_MODEL=claude-sonnet-4-20250514
```

### Running

```bash
# Development
uvicorn src.build_triage.main:app --reload

# Production
uvicorn src.build_triage.main:app --host 0.0.0.0 --port 8000

# Docker
docker-compose up
```

## API Reference

### POST /webhook/build-failure

Receives build failure webhooks from CI systems.

```json
{
  "build_id": "12345",
  "repo": "owner/repo",
  "branch": "main",
  "commit_sha": "abc123def456",
  "pr_number": 42,
  "status": "failed",
  "logs": "Build output logs...",
  "logs_url": "https://ci.example.com/builds/12345/logs"
}
```

### POST /analyze

Manual log analysis endpoint.

```json
{
  "logs": "Build logs to analyze...",
  "context": "Optional additional context"
}
```

### GET /health

Health check endpoint returning service status.

### GET /metrics

Prometheus-compatible metrics endpoint.

## Failure Categories

| Category | Description | Example |
|----------|-------------|---------|
| `code_error` | Compilation or syntax errors | Missing import, type error |
| `test_failure` | Test assertion failures | Expected vs actual mismatch |
| `flaky_test` | Intermittent failures | Race condition, timing issue |
| `dependency` | Package or dependency issues | Version conflict, missing package |
| `infrastructure` | CI/CD infrastructure problems | Network timeout, resource limits |
| `timeout` | Build or test timeouts | Long-running test, infinite loop |
| `unknown` | Unclassifiable failures | Requires manual investigation |

## Development

```bash
# Run tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Lint
ruff check src tests

# Format
ruff format src tests

# Type check
mypy src
```

## Project Structure

```
build-triage-ai/
├── src/
│   └── build_triage/
│       ├── __init__.py
│       ├── main.py           # FastAPI application
│       ├── analyzer.py       # Claude integration
│       ├── github_client.py  # GitHub API client
│       ├── models.py         # Pydantic models
│       ├── config.py         # Configuration
│       ├── metrics.py        # Observability
│       └── errors.py         # Error handling
├── tests/
│   ├── test_analyzer.py
│   ├── test_api.py
│   └── test_github_client.py
├── docs/
│   └── DESIGN.md            # Architecture decisions
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

## License

MIT License - see [LICENSE](LICENSE) for details.
