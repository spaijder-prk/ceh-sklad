from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.load_test import (  # noqa: E402
    RequestResult,
    build_dry_run_report,
    build_execution_report,
)


def args() -> argparse.Namespace:
    return argparse.Namespace(
        requests=4,
        concurrency=2,
        quantity=Decimal("1.5"),
        price_type="retail",
        product_id="product-1",
        location_id="location-1",
        min_success_rate=100.0,
        max_p95_ms=0.0,
        min_throughput_rps=0.0,
    )


def test_execution_report_contains_acceptance_metrics_and_failure_samples():
    results = [
        RequestResult(0, "k0", 200, 10.0, "doc-1", None),
        RequestResult(1, "k1", 201, 20.0, "doc-2", None),
        RequestResult(2, "k2", 200, 30.0, "doc-3", None),
        RequestResult(3, "k3", 500, 100.0, None, "boom"),
    ]

    report = build_execution_report(
        args=args(),
        run_id="run-1",
        available=Decimal("100"),
        results=results,
        wall_seconds=2.0,
        idempotency_verified=True,
    )

    assert report.mode == "execute"
    assert report.successes == 3
    assert report.failures == 1
    assert report.success_rate == 75.0
    assert report.throughput_rps == 2.0
    assert report.latency_min_ms == 10.0
    assert report.latency_p50_ms == 25.0
    assert report.latency_p95_ms == 100.0
    assert report.latency_max_ms == 100.0
    assert report.idempotency_verified is True
    assert report.thresholds_passed is False
    assert "success_rate" in "\n".join(report.threshold_violations)
    assert report.failure_samples == (
        {"index": 3, "status_code": 500, "latency_ms": 100.0, "error": "boom"},
    )


def test_dry_run_report_does_not_fake_performance_metrics():
    report = build_dry_run_report(args(), Decimal("100"))

    assert report.mode == "dry-run"
    assert report.success_rate is None
    assert report.throughput_rps is None
    assert report.latency_p95_ms is None
    assert report.idempotency_verified is False
    assert report.thresholds_passed is None
    assert report.required_quantity == "6.0"
