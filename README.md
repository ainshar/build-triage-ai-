# Build Triage AI

AI-powered CI/CD build failure triage system using Claude to analyze build logs, classify root causes, and suggest fixes.

## Features

- **Webhook Integration**: Receives build failure notifications from CI systems (GitHub Actions, Jenkins, TeamCity)
- **Intelligent Analysis**: Uses Claude to analyze build logs and identify root causes
- **Classification**: Categorizes failures (code error, infra issue, flaky test, dependency problem)
- **Fix Suggestions**: Provides actionable suggestions based on failure patterns
- **PR Comments**: Automatically posts diagnosis to GitHub PRs
- **Confidence Scoring**: Only suggests fixes above configurable confidence thresholds

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL (optional, for persistence)
- Anthropic API key
- GitHub token (for PR comments)

### Installation

```bash
# Clone the repository
git clone https://github.com/ainshar/build-triage-ai.git
cd build-triage-ai

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Copy environment template
cp .env.example .env
# Edit .env with your API keys
```

### Configuration

Create a `.env` file:

```env
ANTHROPIC_API_KEY=your_anthropic_api_key
GITHUB_TOKEN=your_github_token
DATABASE_URL=postgresql://user:pass@localhost/build_triage  # Optional
LOG_LEVEL=INFO
CONFIDENCE_THRESHOLD=0.7
```

### Running

```bash
# Start the server
uvicorn src.build_triage.main:app --reload

# Or with Docker
docker-compose up
```

### Usage

#### Webhook Endpoint

Configure your CI system to POST to `/webhook/build-failure`:

```json
{
  "build_id": "12345",
  "repo": "owner/repo",
  "branch": "main",
  "commit_sha": "abc123",
  "pr_number": 42,
  "status": "failed",
  "logs_url": "https://ci.example.com/builds/12345/logs",
  "logs": "Optional inline logs..."
}
```

#### Manual Analysis

```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"logs": "your build logs here..."}'
```

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   CI System     │────▶│  Build Triage   │────▶│   Claude API    │
│ (GitHub/Jenkins)│     │     Service     │     │                 │
└─────────────────┘     └────────┬────────┘     └─────────────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │   GitHub API    │
                        │  (PR Comments)  │
                        └─────────────────┘
```

## API Reference

### POST /webhook/build-failure
Receives build failure notifications from CI systems.

### POST /analyze
Analyzes build logs and returns diagnosis.

### GET /health
Health check endpoint.

### GET /analyses/{build_id}
Retrieves previous analysis results.

## Development

```bash
# Run tests
pytest

# Run with coverage
pytest --cov=src

# Lint
ruff check src tests

# Format
ruff format src tests

# Type check
mypy src
```

## Classification Categories

| Category | Description |
|----------|-------------|
| `code_error` | Syntax errors, type errors, logic bugs |
| `test_failure` | Assertion failures, test logic issues |
| `flaky_test` | Intermittent failures, race conditions |
| `dependency` | Package conflicts, missing dependencies |
| `infrastructure` | Network issues, resource limits, CI config |
| `timeout` | Build or test timeouts |
| `unknown` | Unclassifiable failures |

## License

MIT License - see [LICENSE](LICENSE) for details.
