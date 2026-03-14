"""Main FastAPI application for Build Triage AI."""

from contextlib import asynccontextmanager

import structlog
from fastapi import BackgroundTasks, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .analyzer import BuildAnalyzer
from .config import get_settings
from .github_client import GitHubClient
from .models import (
    AnalysisResult,
    AnalyzeRequest,
    BuildStatus,
    HealthResponse,
    WebhookPayload,
)

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

logger = structlog.get_logger()

# Global instances
analyzer: BuildAnalyzer | None = None
github_client: GitHubClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global analyzer, github_client

    logger.info("starting_application", version=__version__)

    # Initialize services
    settings = get_settings()
    analyzer = BuildAnalyzer(settings)
    github_client = GitHubClient(settings)

    yield

    # Cleanup
    if github_client:
        await github_client.close()

    logger.info("shutting_down_application")


app = FastAPI(
    title="Build Triage AI",
    description="AI-powered CI/CD build failure triage using Claude",
    version=__version__,
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="ok", version=__version__)


@app.post("/analyze", response_model=AnalysisResult, tags=["Analysis"])
async def analyze_logs(request: AnalyzeRequest) -> AnalysisResult:
    """
    Analyze build logs and return diagnosis.

    This endpoint accepts raw build logs and returns an AI-powered
    analysis including failure category, root cause, and fix suggestions.
    """
    if analyzer is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Analyzer not initialized",
        )

    logger.info("manual_analysis_request", log_length=len(request.logs))

    result = await analyzer.analyze(
        logs=request.logs,
        context=request.context,
    )

    return result


@app.post(
    "/webhook/build-failure",
    response_model=AnalysisResult,
    tags=["Webhook"],
)
async def webhook_build_failure(
    payload: WebhookPayload,
    background_tasks: BackgroundTasks,
) -> AnalysisResult:
    """
    Receive build failure webhook and analyze.

    This endpoint is designed to receive webhooks from CI systems
    when builds fail. It analyzes the logs and optionally posts
    results to the associated PR.
    """
    if analyzer is None or github_client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Services not initialized",
        )

    log = logger.bind(
        build_id=payload.build_id,
        repo=payload.repo,
        pr_number=payload.pr_number,
    )

    # Only process failed builds
    if payload.status != BuildStatus.FAILED:
        log.info("skipping_non_failed_build", status=payload.status)
        raise HTTPException(
            status_code=status.HTTP_200_OK,
            detail="Build did not fail, skipping analysis",
        )

    # Get logs
    logs = payload.logs
    if not logs and payload.logs_url:
        log.info("fetching_logs_from_url")
        logs = await github_client.fetch_logs_from_url(payload.logs_url)

    if not logs:
        log.error("no_logs_available")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No logs provided and could not fetch from logs_url",
        )

    # Analyze
    log.info("analyzing_webhook_payload")
    result = await analyzer.analyze(
        logs=logs,
        build_id=payload.build_id,
        context=f"Repository: {payload.repo}, Branch: {payload.branch}",
    )

    # Post to PR in background if applicable
    if payload.pr_number:
        background_tasks.add_task(
            github_client.post_pr_comment,
            payload.repo,
            payload.pr_number,
            result,
        )

    return result


@app.get(
    "/analyses/{build_id}",
    response_model=AnalysisResult | None,
    tags=["Analysis"],
)
async def get_analysis(build_id: str) -> AnalysisResult | None:
    """
    Retrieve a previous analysis result by build ID.

    Note: This endpoint requires database configuration.
    Returns None if persistence is not configured.
    """
    # TODO: Implement database persistence
    logger.info("get_analysis_request", build_id=build_id)
    return None


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "src.build_triage.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
