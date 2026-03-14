"""Observability: metrics, logging, and tracing for Build Triage AI."""

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Callable

import structlog

logger = structlog.get_logger()


@dataclass
class MetricsRegistry:
    """Simple in-memory metrics registry.

    In production, this would integrate with Prometheus, DataDog, etc.
    """

    counters: dict[str, int] = field(default_factory=dict)
    histograms: dict[str, list[float]] = field(default_factory=dict)
    gauges: dict[str, float] = field(default_factory=dict)

    def increment(self, name: str, value: int = 1, labels: dict | None = None) -> None:
        """Increment a counter metric."""
        key = self._make_key(name, labels)
        self.counters[key] = self.counters.get(key, 0) + value
        logger.debug("metric_counter", name=name, value=self.counters[key], labels=labels)

    def observe(self, name: str, value: float, labels: dict | None = None) -> None:
        """Record a histogram observation."""
        key = self._make_key(name, labels)
        if key not in self.histograms:
            self.histograms[key] = []
        self.histograms[key].append(value)
        logger.debug("metric_histogram", name=name, value=value, labels=labels)

    def set_gauge(self, name: str, value: float, labels: dict | None = None) -> None:
        """Set a gauge value."""
        key = self._make_key(name, labels)
        self.gauges[key] = value
        logger.debug("metric_gauge", name=name, value=value, labels=labels)

    def get_counter(self, name: str, labels: dict | None = None) -> int:
        """Get current counter value."""
        key = self._make_key(name, labels)
        return self.counters.get(key, 0)

    def get_histogram_stats(self, name: str, labels: dict | None = None) -> dict:
        """Get histogram statistics."""
        key = self._make_key(name, labels)
        values = self.histograms.get(key, [])
        if not values:
            return {"count": 0, "sum": 0, "avg": 0, "p50": 0, "p99": 0}

        sorted_values = sorted(values)
        count = len(sorted_values)
        return {
            "count": count,
            "sum": sum(sorted_values),
            "avg": sum(sorted_values) / count,
            "p50": sorted_values[int(count * 0.5)],
            "p99": sorted_values[int(count * 0.99)] if count > 1 else sorted_values[-1],
        }

    def _make_key(self, name: str, labels: dict | None) -> str:
        """Create a unique key for metric with labels."""
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"

    def export_prometheus(self) -> str:
        """Export metrics in Prometheus format."""
        lines = []

        for key, value in self.counters.items():
            lines.append(f"# TYPE {key.split('{')[0]} counter")
            lines.append(f"{key} {value}")

        for key, values in self.histograms.items():
            base_name = key.split("{")[0]
            stats = self.get_histogram_stats(base_name)
            lines.append(f"# TYPE {base_name} histogram")
            lines.append(f"{base_name}_count {stats['count']}")
            lines.append(f"{base_name}_sum {stats['sum']}")

        for key, value in self.gauges.items():
            lines.append(f"# TYPE {key.split('{')[0]} gauge")
            lines.append(f"{key} {value}")

        return "\n".join(lines)


# Global metrics registry
metrics = MetricsRegistry()


# Metric names
class MetricNames:
    """Constants for metric names."""

    ANALYSIS_REQUESTS = "build_triage_analysis_requests_total"
    ANALYSIS_DURATION = "build_triage_analysis_duration_seconds"
    ANALYSIS_CONFIDENCE = "build_triage_analysis_confidence"
    ANALYSIS_ERRORS = "build_triage_analysis_errors_total"
    CATEGORY_CLASSIFICATIONS = "build_triage_classifications_total"
    GITHUB_COMMENTS = "build_triage_github_comments_total"
    WEBHOOK_REQUESTS = "build_triage_webhook_requests_total"
    LLM_REQUESTS = "build_triage_llm_requests_total"
    LLM_LATENCY = "build_triage_llm_latency_seconds"
    LLM_TOKENS = "build_triage_llm_tokens_total"


@contextmanager
def track_latency(metric_name: str, labels: dict | None = None):
    """Context manager to track operation latency."""
    start_time = time.perf_counter()
    try:
        yield
    finally:
        duration = time.perf_counter() - start_time
        metrics.observe(metric_name, duration, labels)


def track_analysis(func: Callable) -> Callable:
    """Decorator to track analysis metrics."""

    async def wrapper(*args, **kwargs):
        metrics.increment(MetricNames.ANALYSIS_REQUESTS)

        start_time = time.perf_counter()
        try:
            result = await func(*args, **kwargs)

            # Record success metrics
            duration = time.perf_counter() - start_time
            metrics.observe(MetricNames.ANALYSIS_DURATION, duration)
            metrics.observe(MetricNames.ANALYSIS_CONFIDENCE, result.confidence)
            metrics.increment(
                MetricNames.CATEGORY_CLASSIFICATIONS,
                labels={"category": result.category.value},
            )

            logger.info(
                "analysis_metrics",
                duration_ms=round(duration * 1000, 2),
                confidence=result.confidence,
                category=result.category.value,
            )

            return result

        except Exception as e:
            metrics.increment(
                MetricNames.ANALYSIS_ERRORS,
                labels={"error_type": type(e).__name__},
            )
            raise

    return wrapper


def record_llm_metrics(
    duration: float,
    input_tokens: int,
    output_tokens: int,
    model: str,
) -> None:
    """Record LLM-specific metrics."""
    metrics.increment(MetricNames.LLM_REQUESTS, labels={"model": model})
    metrics.observe(MetricNames.LLM_LATENCY, duration, labels={"model": model})
    metrics.increment(
        MetricNames.LLM_TOKENS,
        value=input_tokens,
        labels={"type": "input", "model": model},
    )
    metrics.increment(
        MetricNames.LLM_TOKENS,
        value=output_tokens,
        labels={"type": "output", "model": model},
    )


def record_github_comment(repo: str, success: bool) -> None:
    """Record GitHub comment posting metrics."""
    metrics.increment(
        MetricNames.GITHUB_COMMENTS,
        labels={"repo": repo, "success": str(success).lower()},
    )
