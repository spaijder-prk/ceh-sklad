import argparse
import importlib.util
import sys
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/load_test.py"
SPEC = importlib.util.spec_from_file_location("ceh_load_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
load_test = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = load_test
SPEC.loader.exec_module(load_test)


def _args(**overrides):
    values = {
        "requests": 2,
        "concurrency": 2,
        "quantity": Decimal("1"),
        "price_type": "retail",
        "product_id": "product",
        "location_id": "location",
        "min_success_rate": 100.0,
        "max_p95_ms": 500.0,
        "min_throughput_rps": 1.0,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_execution_report_passes_agreed_thresholds():
    results = [
        load_test.RequestResult(0, "op-0", 200, 100.0, "doc-0", None),
        load_test.RequestResult(1, "op-1", 200, 200.0, "doc-1", None),
    ]
    report = load_test.build_execution_report(
        args=_args(),
        run_id="run",
        available=Decimal("10"),
        results=results,
        wall_seconds=1.0,
        idempotency_verified=True,
    )

    assert report.schema_version == 2
    assert report.success_rate == 100.0
    assert report.latency_p95_ms == 200.0
    assert report.throughput_rps == 2.0
    assert report.thresholds_passed is True
    assert report.threshold_violations == ()


def test_execution_report_lists_threshold_violations():
    results = [
        load_test.RequestResult(0, "op-0", 200, 700.0, "doc-0", None),
        load_test.RequestResult(1, "op-1", 500, 800.0, None, "server error"),
    ]
    report = load_test.build_execution_report(
        args=_args(min_throughput_rps=5.0),
        run_id="run",
        available=Decimal("10"),
        results=results,
        wall_seconds=1.0,
        idempotency_verified=False,
    )

    assert report.thresholds_passed is False
    joined = "\n".join(report.threshold_violations)
    assert "success_rate" in joined
    assert "p95" in joined
    assert "throughput" in joined
    assert "идемпотентный" in joined


def test_zero_performance_thresholds_disable_only_performance_checks():
    violations = load_test.evaluate_thresholds(
        args=_args(max_p95_ms=0.0, min_throughput_rps=0.0),
        success_rate=100.0,
        latency_p95_ms=100000.0,
        throughput_rps=0.001,
        idempotency_verified=True,
    )

    assert violations == ()
