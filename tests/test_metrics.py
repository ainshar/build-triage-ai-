"""Tests for metrics and observability."""

import pytest

from src.build_triage.metrics import (
    MetricNames,
    MetricsRegistry,
    metrics,
    record_github_comment,
    record_llm_metrics,
    track_latency,
)


class TestMetricsRegistry:
    """Tests for MetricsRegistry."""

    @pytest.fixture
    def registry(self):
        """Create fresh registry for each test."""
        return MetricsRegistry()

    def test_increment_counter(self, registry):
        """Verify counter increment."""
        registry.increment("test_counter")
        assert registry.get_counter("test_counter") == 1

        registry.increment("test_counter")
        assert registry.get_counter("test_counter") == 2

    def test_increment_counter_with_value(self, registry):
        """Verify counter increment with custom value."""
        registry.increment("test_counter", value=5)
        assert registry.get_counter("test_counter") == 5

        registry.increment("test_counter", value=3)
        assert registry.get_counter("test_counter") == 8

    def test_increment_counter_with_labels(self, registry):
        """Verify counter with labels."""
        registry.increment("requests", labels={"method": "GET"})
        registry.increment("requests", labels={"method": "POST"})
        registry.increment("requests", labels={"method": "GET"})

        assert registry.get_counter("requests", labels={"method": "GET"}) == 2
        assert registry.get_counter("requests", labels={"method": "POST"}) == 1

    def test_observe_histogram(self, registry):
        """Verify histogram observations."""
        registry.observe("latency", 0.5)
        registry.observe("latency", 1.5)
        registry.observe("latency", 2.0)

        stats = registry.get_histogram_stats("latency")
        assert stats["count"] == 3
        assert stats["sum"] == 4.0
        assert stats["avg"] == pytest.approx(1.333, rel=0.01)

    def test_histogram_percentiles(self, registry):
        """Verify histogram percentile calculations."""
        # Add 100 values from 1-100
        for i in range(1, 101):
            registry.observe("latency", float(i))

        stats = registry.get_histogram_stats("latency")
        assert stats["p50"] == 50.0
        assert stats["p99"] == 99.0

    def test_histogram_empty_stats(self, registry):
        """Verify empty histogram stats."""
        stats = registry.get_histogram_stats("nonexistent")
        assert stats["count"] == 0
        assert stats["sum"] == 0
        assert stats["avg"] == 0

    def test_set_gauge(self, registry):
        """Verify gauge setting."""
        registry.set_gauge("memory_usage", 1024.5)
        assert registry.gauges["memory_usage"] == 1024.5

        registry.set_gauge("memory_usage", 2048.0)
        assert registry.gauges["memory_usage"] == 2048.0

    def test_make_key_without_labels(self, registry):
        """Verify key creation without labels."""
        key = registry._make_key("test_metric", None)
        assert key == "test_metric"

    def test_make_key_with_labels(self, registry):
        """Verify key creation with labels."""
        key = registry._make_key("test_metric", {"a": "1", "b": "2"})
        assert key == "test_metric{a=1,b=2}"

    def test_make_key_labels_sorted(self, registry):
        """Verify labels are sorted consistently."""
        key1 = registry._make_key("test", {"z": "1", "a": "2"})
        key2 = registry._make_key("test", {"a": "2", "z": "1"})
        assert key1 == key2

    def test_export_prometheus_counters(self, registry):
        """Verify Prometheus counter export."""
        registry.increment("http_requests")
        registry.increment("http_requests")

        output = registry.export_prometheus()

        assert "# TYPE http_requests counter" in output
        assert "http_requests 2" in output

    def test_export_prometheus_gauges(self, registry):
        """Verify Prometheus gauge export."""
        registry.set_gauge("active_connections", 42)

        output = registry.export_prometheus()

        assert "# TYPE active_connections gauge" in output
        assert "active_connections 42" in output


class TestMetricNames:
    """Tests for MetricNames constants."""

    def test_metric_names_defined(self):
        """Verify all metric names are defined."""
        assert MetricNames.ANALYSIS_REQUESTS
        assert MetricNames.ANALYSIS_DURATION
        assert MetricNames.ANALYSIS_CONFIDENCE
        assert MetricNames.ANALYSIS_ERRORS
        assert MetricNames.LLM_REQUESTS
        assert MetricNames.LLM_LATENCY
        assert MetricNames.LLM_TOKENS
        assert MetricNames.GITHUB_COMMENTS

    def test_metric_names_follow_convention(self):
        """Verify metric names follow naming convention."""
        for name in dir(MetricNames):
            if not name.startswith("_"):
                value = getattr(MetricNames, name)
                # Should start with "build_triage_"
                assert value.startswith("build_triage_")
                # Should end with _total for counters or have descriptive suffix
                assert "_" in value


class TestTrackLatency:
    """Tests for track_latency context manager."""

    def test_track_latency_records_duration(self):
        """Verify latency is recorded."""
        registry = MetricsRegistry()

        # Temporarily replace global metrics
        import src.build_triage.metrics as m

        original = m.metrics
        m.metrics = registry

        try:
            with track_latency("test_operation"):
                pass  # Some operation

            stats = registry.get_histogram_stats("test_operation")
            assert stats["count"] == 1
            assert stats["avg"] >= 0
        finally:
            m.metrics = original

    def test_track_latency_with_labels(self):
        """Verify latency with labels."""
        registry = MetricsRegistry()

        import src.build_triage.metrics as m

        original = m.metrics
        m.metrics = registry

        try:
            with track_latency("api_request", labels={"endpoint": "/analyze"}):
                pass

            key = registry._make_key("api_request", {"endpoint": "/analyze"})
            assert key in registry.histograms
        finally:
            m.metrics = original


class TestRecordLLMMetrics:
    """Tests for record_llm_metrics function."""

    def test_records_all_metrics(self):
        """Verify all LLM metrics are recorded."""
        registry = MetricsRegistry()

        import src.build_triage.metrics as m

        original = m.metrics
        m.metrics = registry

        try:
            record_llm_metrics(
                duration=1.5,
                input_tokens=100,
                output_tokens=50,
                model="claude-3-sonnet",
            )

            # Check request counter
            assert registry.get_counter(
                MetricNames.LLM_REQUESTS, labels={"model": "claude-3-sonnet"}
            ) == 1

            # Check token counters
            assert registry.get_counter(
                MetricNames.LLM_TOKENS,
                labels={"type": "input", "model": "claude-3-sonnet"},
            ) == 100
            assert registry.get_counter(
                MetricNames.LLM_TOKENS,
                labels={"type": "output", "model": "claude-3-sonnet"},
            ) == 50
        finally:
            m.metrics = original


class TestRecordGitHubComment:
    """Tests for record_github_comment function."""

    def test_records_success(self):
        """Verify successful comment is recorded."""
        registry = MetricsRegistry()

        import src.build_triage.metrics as m

        original = m.metrics
        m.metrics = registry

        try:
            record_github_comment("owner/repo", success=True)

            assert registry.get_counter(
                MetricNames.GITHUB_COMMENTS,
                labels={"repo": "owner/repo", "success": "true"},
            ) == 1
        finally:
            m.metrics = original

    def test_records_failure(self):
        """Verify failed comment is recorded."""
        registry = MetricsRegistry()

        import src.build_triage.metrics as m

        original = m.metrics
        m.metrics = registry

        try:
            record_github_comment("owner/repo", success=False)

            assert registry.get_counter(
                MetricNames.GITHUB_COMMENTS,
                labels={"repo": "owner/repo", "success": "false"},
            ) == 1
        finally:
            m.metrics = original
