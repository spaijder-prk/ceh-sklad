from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

import httpx

EXECUTION_CONFIRMATION = "I_UNDERSTAND_THIS_CREATES_REAL_SALES"


@dataclass
class RequestResult:
    index: int
    operation_key: str
    status_code: int
    latency_ms: float
    response_id: str | None
    error: str | None


@dataclass(frozen=True)
class LoadTestReport:
    schema_version: int
    mode: str
    run_id: str | None
    requests: int
    concurrency: int
    quantity: str
    price_type: str
    product_id: str
    location_id: str
    available_quantity: str
    required_quantity: str
    successes: int
    failures: int
    success_rate: float | None
    wall_seconds: float | None
    throughput_rps: float | None
    latency_min_ms: float | None
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    latency_max_ms: float | None
    idempotency_verified: bool
    threshold_min_success_rate: float
    threshold_max_p95_ms: float | None
    threshold_min_throughput_rps: float | None
    thresholds_passed: bool | None
    threshold_violations: tuple[str, ...]
    failure_samples: tuple[dict[str, object], ...]


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = round((len(ordered) - 1) * fraction)
    return ordered[position]


def normalized_thresholds(args: argparse.Namespace) -> tuple[float, float | None, float | None]:
    return (
        float(args.min_success_rate),
        float(args.max_p95_ms) if args.max_p95_ms > 0 else None,
        float(args.min_throughput_rps) if args.min_throughput_rps > 0 else None,
    )


def evaluate_thresholds(
    *,
    args: argparse.Namespace,
    success_rate: float,
    latency_p95_ms: float,
    throughput_rps: float,
    idempotency_verified: bool,
) -> tuple[str, ...]:
    min_success_rate, max_p95_ms, min_throughput_rps = normalized_thresholds(args)
    violations: list[str] = []
    if success_rate < min_success_rate:
        violations.append(
            f"success_rate {success_rate:.2f}% < требуемых {min_success_rate:.2f}%"
        )
    if max_p95_ms is not None and latency_p95_ms > max_p95_ms:
        violations.append(
            f"p95 {latency_p95_ms:.1f} ms > допустимых {max_p95_ms:.1f} ms"
        )
    if min_throughput_rps is not None and throughput_rps < min_throughput_rps:
        violations.append(
            f"throughput {throughput_rps:.2f} req/s < требуемых {min_throughput_rps:.2f} req/s"
        )
    if not idempotency_verified:
        violations.append("идемпотентный повтор первого успешного запроса не подтвержден")
    return tuple(violations)


def build_execution_report(
    *,
    args: argparse.Namespace,
    run_id: str,
    available: Decimal,
    results: list[RequestResult],
    wall_seconds: float,
    idempotency_verified: bool,
) -> LoadTestReport:
    successes = [row for row in results if 200 <= row.status_code < 300]
    failures = [row for row in results if row not in successes]
    latencies = [row.latency_ms for row in results]
    count = len(results)
    success_rate = (len(successes) / count * 100.0) if count else 0.0
    throughput = count / wall_seconds if wall_seconds > 0 else 0.0
    latency_min = min(latencies) if latencies else 0.0
    latency_p50 = statistics.median(latencies) if latencies else 0.0
    latency_p95 = percentile(latencies, 0.95) if latencies else 0.0
    latency_max = max(latencies) if latencies else 0.0
    min_success_rate, max_p95_ms, min_throughput_rps = normalized_thresholds(args)
    violations = evaluate_thresholds(
        args=args,
        success_rate=success_rate,
        latency_p95_ms=latency_p95,
        throughput_rps=throughput,
        idempotency_verified=idempotency_verified,
    )

    return LoadTestReport(
        schema_version=2,
        mode="execute",
        run_id=run_id,
        requests=args.requests,
        concurrency=args.concurrency,
        quantity=str(args.quantity),
        price_type=args.price_type,
        product_id=args.product_id,
        location_id=args.location_id,
        available_quantity=str(available),
        required_quantity=str(args.quantity * args.requests),
        successes=len(successes),
        failures=len(failures),
        success_rate=round(success_rate, 4),
        wall_seconds=round(wall_seconds, 6),
        throughput_rps=round(throughput, 4),
        latency_min_ms=round(latency_min, 3),
        latency_p50_ms=round(latency_p50, 3),
        latency_p95_ms=round(latency_p95, 3),
        latency_max_ms=round(latency_max, 3),
        idempotency_verified=idempotency_verified,
        threshold_min_success_rate=min_success_rate,
        threshold_max_p95_ms=max_p95_ms,
        threshold_min_throughput_rps=min_throughput_rps,
        thresholds_passed=not violations,
        threshold_violations=violations,
        failure_samples=tuple(
            {
                "index": row.index,
                "status_code": row.status_code,
                "latency_ms": round(row.latency_ms, 3),
                "error": row.error,
            }
            for row in failures[:10]
        ),
    )


def build_dry_run_report(args: argparse.Namespace, available: Decimal) -> LoadTestReport:
    min_success_rate, max_p95_ms, min_throughput_rps = normalized_thresholds(args)
    return LoadTestReport(
        schema_version=2,
        mode="dry-run",
        run_id=None,
        requests=args.requests,
        concurrency=args.concurrency,
        quantity=str(args.quantity),
        price_type=args.price_type,
        product_id=args.product_id,
        location_id=args.location_id,
        available_quantity=str(available),
        required_quantity=str(args.quantity * args.requests),
        successes=0,
        failures=0,
        success_rate=None,
        wall_seconds=None,
        throughput_rps=None,
        latency_min_ms=None,
        latency_p50_ms=None,
        latency_p95_ms=None,
        latency_max_ms=None,
        idempotency_verified=False,
        threshold_min_success_rate=min_success_rate,
        threshold_max_p95_ms=max_p95_ms,
        threshold_min_throughput_rps=min_throughput_rps,
        thresholds_passed=None,
        threshold_violations=(),
        failure_samples=(),
    )


def write_report(report: LoadTestReport, output: Path | None) -> None:
    if output is None:
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(asdict(report), ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Нагрузочный сценарий продаж ceh-sklad. По умолчанию выполняется только dry-run."
    )
    parser.add_argument("--base-url", required=True, help="Например https://staging-sklad.example.ru")
    parser.add_argument("--login", required=True, help="Логин торгового представителя")
    parser.add_argument("--location-id", required=True, help="UUID виртуального склада представителя")
    parser.add_argument("--product-id", required=True, help="UUID товара с достаточным остатком")
    parser.add_argument("--requests", type=int, default=50, help="Количество продаж")
    parser.add_argument("--concurrency", type=int, default=10, help="Одновременные запросы")
    parser.add_argument("--quantity", type=Decimal, default=Decimal("1"), help="Количество товара на одну продажу")
    parser.add_argument("--price-type", choices=("retail", "wholesale"), default="retail")
    parser.add_argument("--timeout", type=float, default=20.0, help="HTTP timeout в секундах")
    parser.add_argument("--output", type=Path, help="Сохранить машинный JSON-отчет")
    parser.add_argument(
        "--min-success-rate",
        type=float,
        default=100.0,
        help="Минимальный success rate в процентах; по умолчанию 100",
    )
    parser.add_argument(
        "--max-p95-ms",
        type=float,
        default=0.0,
        help="Максимальный p95 в мс; 0 отключает этот порог",
    )
    parser.add_argument(
        "--min-throughput-rps",
        type=float,
        default=0.0,
        help="Минимальный throughput req/s; 0 отключает этот порог",
    )
    parser.add_argument("--execute", action="store_true", help="Действительно провести продажи")
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if args.requests < 1:
        raise ValueError("--requests должен быть >= 1")
    if args.concurrency < 1:
        raise ValueError("--concurrency должен быть >= 1")
    if args.concurrency > args.requests:
        args.concurrency = args.requests
    if args.quantity <= 0:
        raise ValueError("--quantity должен быть > 0")
    if not 0 <= args.min_success_rate <= 100:
        raise ValueError("--min-success-rate должен быть от 0 до 100")
    if args.max_p95_ms < 0:
        raise ValueError("--max-p95-ms должен быть >= 0")
    if args.min_throughput_rps < 0:
        raise ValueError("--min-throughput-rps должен быть >= 0")

    parsed = urlparse(args.base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("--base-url должен быть полноценным HTTP(S) URL")
    if args.execute and parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("Реальный load-test вне localhost разрешен только через HTTPS")

    if args.execute and os.getenv("CEH_LOAD_TEST_CONFIRM") != EXECUTION_CONFIRMATION:
        raise ValueError(
            "Для --execute задайте CEH_LOAD_TEST_CONFIRM="
            f"{EXECUTION_CONFIRMATION}"
        )


async def login_and_validate(
    client: httpx.AsyncClient,
    args: argparse.Namespace,
) -> tuple[dict[str, str], dict]:
    password = os.getenv("CEH_LOAD_PASSWORD")
    if not password:
        raise RuntimeError("Пароль не передается в CLI. Задайте CEH_LOAD_PASSWORD.")

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"login": args.login, "password": password},
    )
    login_response.raise_for_status()
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    me_response = await client.get("/api/v1/auth/me", headers=headers)
    me_response.raise_for_status()
    user = me_response.json()
    if user.get("role") != "representative":
        raise RuntimeError("Load-test нужно выполнять учетной записью representative")
    if user.get("location_id") != args.location_id:
        raise RuntimeError("Указанный --location-id не совпадает с виртуальным складом пользователя")

    stocks_response = await client.get(
        "/api/v1/stocks",
        params={"location_id": args.location_id},
        headers=headers,
    )
    stocks_response.raise_for_status()
    product = next(
        (row for row in stocks_response.json() if row["product_id"] == args.product_id),
        None,
    )
    if product is None:
        raise RuntimeError("Товар не найден в подтвержденном остатке представителя")

    available = Decimal(str(product["quantity"]))
    required = args.quantity * args.requests
    if args.execute and available < required:
        raise RuntimeError(
            f"Для полного теста нужно {required}, подтвержденный остаток только {available}. "
            "Уменьшите --requests/--quantity или подготовьте staging-остаток."
        )

    return headers, product


async def perform_sale(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    args: argparse.Namespace,
    run_id: str,
    index: int,
    semaphore: asyncio.Semaphore,
) -> RequestResult:
    operation_key = f"load-{run_id}-{index:06d}"
    payload = {
        "representative_location_id": args.location_id,
        "items": [{"product_id": args.product_id, "quantity": str(args.quantity)}],
        "price_type": args.price_type,
        "comment": f"LOAD TEST {run_id}",
        "operation_key": operation_key,
    }

    async with semaphore:
        started = time.perf_counter()
        try:
            response = await client.post("/api/v1/sales", json=payload, headers=headers)
            latency_ms = (time.perf_counter() - started) * 1000
            response_id = None
            error = None
            try:
                body = response.json()
                response_id = body.get("id")
                if not response.is_success:
                    error = str(body.get("detail") or body)
            except Exception:
                if not response.is_success:
                    error = response.text[:300]
            return RequestResult(index, operation_key, response.status_code, latency_ms, response_id, error)
        except Exception as exc:
            latency_ms = (time.perf_counter() - started) * 1000
            return RequestResult(index, operation_key, 0, latency_ms, None, repr(exc))


async def verify_first_idempotency(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    args: argparse.Namespace,
    run_id: str,
    first: RequestResult,
) -> bool:
    if first.status_code // 100 != 2 or not first.response_id:
        return False

    payload = {
        "representative_location_id": args.location_id,
        "items": [{"product_id": args.product_id, "quantity": str(args.quantity)}],
        "price_type": args.price_type,
        "comment": f"LOAD TEST {run_id}",
        "operation_key": first.operation_key,
    }
    repeated = await client.post("/api/v1/sales", json=payload, headers=headers)
    repeated.raise_for_status()
    repeated_id = repeated.json().get("id")
    if repeated_id != first.response_id:
        raise RuntimeError(
            f"Идемпотентный повтор вернул другой document id: {first.response_id} -> {repeated_id}"
        )
    return True


async def main_async(args: argparse.Namespace) -> int:
    base_url = args.base_url.rstrip("/")
    async with httpx.AsyncClient(base_url=base_url, timeout=args.timeout) as client:
        headers, product = await login_and_validate(client, args)
        available = Decimal(str(product["quantity"]))
        required = args.quantity * args.requests
        print(
            f"Проверка пройдена: {product['product_name']} | остаток={available} | "
            f"план={required} | requests={args.requests} | concurrency={args.concurrency}"
        )

        if not args.execute:
            report = build_dry_run_report(args, available)
            write_report(report, args.output)
            print("DRY-RUN: продажи не отправлялись. Для реального staging-теста добавьте --execute.")
            if args.output:
                print(f"JSON-отчет: {args.output}")
            return 0

        run_id = uuid.uuid4().hex[:12]
        semaphore = asyncio.Semaphore(args.concurrency)
        wall_started = time.perf_counter()
        results = await asyncio.gather(
            *(
                perform_sale(client, headers, args, run_id, index, semaphore)
                for index in range(args.requests)
            )
        )
        wall_seconds = time.perf_counter() - wall_started

        successes = [row for row in results if 200 <= row.status_code < 300]
        failures = [row for row in results if row not in successes]
        idempotency_verified = False
        if successes:
            idempotency_verified = await verify_first_idempotency(
                client, headers, args, run_id, successes[0]
            )

        report = build_execution_report(
            args=args,
            run_id=run_id,
            available=available,
            results=results,
            wall_seconds=wall_seconds,
            idempotency_verified=idempotency_verified,
        )
        write_report(report, args.output)

        print(
            f"Результат: success={report.successes} failure={report.failures} "
            f"success_rate={report.success_rate:.2f}% wall={report.wall_seconds:.2f}s "
            f"throughput={report.throughput_rps:.2f} req/s"
        )
        print(
            f"Latency ms: min={report.latency_min_ms:.1f} "
            f"p50={report.latency_p50_ms:.1f} "
            f"p95={report.latency_p95_ms:.1f} "
            f"max={report.latency_max_ms:.1f}"
        )
        print(f"Идемпотентность первого успешного запроса: {'OK' if idempotency_verified else 'не проверена'}")
        if report.thresholds_passed:
            print("Acceptance-пороги: OK")
        else:
            print("Acceptance-пороги: НЕ ПРОЙДЕНЫ")
            for violation in report.threshold_violations:
                print(f"  - {violation}")
        for row in failures[:10]:
            print(
                f"FAIL #{row.index}: status={row.status_code} "
                f"latency={row.latency_ms:.1f}ms error={row.error}"
            )
        if args.output:
            print(f"JSON-отчет: {args.output}")

        return 0 if report.thresholds_passed else 1


def main() -> int:
    try:
        args = parse_args()
        validate_args(args)
        return asyncio.run(main_async(args))
    except (ValueError, RuntimeError, httpx.HTTPError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
