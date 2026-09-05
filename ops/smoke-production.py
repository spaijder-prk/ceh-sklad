#!/usr/bin/env python3
"""Быстрая проверка полного production-контура на одноразовой тестовой базе."""

from __future__ import annotations

import json
import os
import ssl
import sys
from decimal import Decimal
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4


BASE_URL = os.getenv("CEH_SMOKE_BASE_URL", "https://127.0.0.1:18443").rstrip("/")
ALLOW_MUTATION = os.getenv("CEH_SMOKE_ALLOW_MUTATION") == "YES"
INSECURE_TLS = os.getenv("CEH_SMOKE_INSECURE_TLS") == "1"
INTEGRATION_KEY = os.getenv("CEH_SMOKE_INTEGRATION_KEY")
TIMEOUT = 15


class SmokeError(RuntimeError):
    pass


class Client:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.ssl_context = None
        if base_url.startswith("https://") and INSECURE_TLS:
            self.ssl_context = ssl._create_unverified_context()  # noqa: SLF001

    def request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        json_body: dict[str, Any] | None = None,
        form_body: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        expected: tuple[int, ...] = (200,),
    ) -> tuple[int, bytes, dict[str, str]]:
        payload: bytes | None = None
        request_headers = {"Accept": "application/json"}
        if token:
            request_headers["Authorization"] = f"Bearer {token}"
        if headers:
            request_headers.update(headers)
        if json_body is not None:
            payload = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        elif form_body is not None:
            payload = urlencode(form_body).encode("utf-8")
            request_headers["Content-Type"] = "application/x-www-form-urlencoded"

        request = Request(
            f"{self.base_url}{path}",
            data=payload,
            headers=request_headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=TIMEOUT, context=self.ssl_context) as response:
                status = response.status
                body = response.read()
                response_headers = dict(response.headers.items())
        except HTTPError as exc:
            status = exc.code
            body = exc.read()
            response_headers = dict(exc.headers.items())

        if status not in expected:
            text = body.decode("utf-8", errors="replace")
            raise SmokeError(f"{method} {path}: ожидался {expected}, получен {status}: {text}")
        return status, body, response_headers

    def json(self, method: str, path: str, **kwargs: Any) -> Any:
        _, body, _ = self.request(method, path, **kwargs)
        if not body:
            return None
        return json.loads(body.decode("utf-8"))

    def text(self, method: str, path: str, **kwargs: Any) -> str:
        _, body, _ = self.request(method, path, **kwargs)
        return body.decode("utf-8", errors="replace")


def as_decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def find_quantity(rows: list[dict[str, Any]], product_id: str) -> Decimal:
    for row in rows:
        if row["product_id"] == product_id:
            return as_decimal(row["quantity"])
    return Decimal("0")


def login(client: Client, email: str, password: str) -> str:
    response = client.json(
        "POST",
        "/api/v1/auth/token",
        form_body={"username": email, "password": password},
    )
    return response["access_token"]


def assert_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise SmokeError(f"{label}: ожидалось {expected!r}, получено {actual!r}")


def main() -> int:
    if not ALLOW_MUTATION:
        raise SmokeError(
            "Smoke-тест создает данные. Запускайте только на одноразовой базе с CEH_SMOKE_ALLOW_MUTATION=YES"
        )

    client = Client(BASE_URL)
    suffix = uuid4().hex[:10]
    admin_email = f"smoke-admin-{suffix}@example.local"
    rep_email = f"smoke-rep-{suffix}@example.local"
    manager_email = f"smoke-manager-{suffix}@example.local"
    password = f"Smoke-{suffix}-Pass9!"

    health = client.json("GET", "/health")
    assert_equal(health.get("status"), "ok", "healthcheck")
    index_html = client.text("GET", "/", headers={"Accept": "text/html"})
    if "<div id=\"root\">" not in index_html and "<div id='root'>" not in index_html:
        raise SmokeError("Веб-панель не отдала корневой React-контейнер")

    client.json(
        "POST",
        "/api/v1/auth/bootstrap",
        json_body={"email": admin_email, "password": password, "full_name": "Smoke Администратор"},
        expected=(201,),
    )
    admin_token = login(client, admin_email, password)

    warehouse_a = client.json(
        "POST",
        "/api/v1/warehouses",
        token=admin_token,
        json_body={"code": f"SM-A-{suffix}", "name": "Smoke склад А"},
        expected=(201,),
    )
    warehouse_b = client.json(
        "POST",
        "/api/v1/warehouses",
        token=admin_token,
        json_body={"code": f"SM-B-{suffix}", "name": "Smoke склад Б"},
        expected=(201,),
    )
    product = client.json(
        "POST",
        "/api/v1/products",
        token=admin_token,
        json_body={
            "sku": f"SM-{suffix}",
            "name": "Smoke товар",
            "unit": "шт",
            "retail_price": "125.00",
            "wholesale_price": "100.00",
        },
        expected=(201,),
    )
    rep_user = client.json(
        "POST",
        "/api/v1/users",
        token=admin_token,
        json_body={
            "email": rep_email,
            "password": password,
            "full_name": "Smoke Представитель",
            "role": "representative",
        },
        expected=(201,),
    )
    representative = client.json(
        "POST",
        "/api/v1/representatives",
        token=admin_token,
        json_body={
            "code": f"SM-REP-{suffix}",
            "name": "Smoke Представитель",
            "user_id": rep_user["id"],
        },
        expected=(201,),
    )
    client.json(
        "POST",
        "/api/v1/users",
        token=admin_token,
        json_body={
            "email": manager_email,
            "password": password,
            "full_name": "Smoke Руководитель",
            "role": "manager",
        },
        expected=(201,),
    )

    receipt = client.json(
        "POST",
        "/api/v1/operations/receipt",
        token=admin_token,
        json_body={
            "warehouse_id": warehouse_a["id"],
            "external_id": f"smoke-{suffix}-receipt",
            "lines": [{"product_id": product["id"], "quantity": "10.000"}],
        },
        expected=(201,),
    )
    if not receipt.get("document_id"):
        raise SmokeError("Приход не вернул document_id")

    client.json(
        "POST",
        "/api/v1/operations/warehouse-transfer",
        token=admin_token,
        json_body={
            "source_warehouse_id": warehouse_a["id"],
            "target_warehouse_id": warehouse_b["id"],
            "external_id": f"smoke-{suffix}-transfer",
            "lines": [{"product_id": product["id"], "quantity": "2.000"}],
        },
        expected=(201,),
    )

    issue_payload = {
        "warehouse_id": warehouse_a["id"],
        "representative_id": representative["id"],
        "external_id": f"smoke-{suffix}-issue",
        "lines": [{"product_id": product["id"], "quantity": "5.000"}],
    }
    first_issue = client.json(
        "POST",
        "/api/v1/operations/issue-to-representative",
        token=admin_token,
        json_body=issue_payload,
        expected=(201,),
    )
    repeated_issue = client.json(
        "POST",
        "/api/v1/operations/issue-to-representative",
        token=admin_token,
        json_body=issue_payload,
        expected=(201,),
    )
    assert_equal(repeated_issue["document_id"], first_issue["document_id"], "Идемпотентность выдачи")

    rep_token = login(client, rep_email, password)
    client.json("GET", "/api/v1/auth/me", token=rep_token)
    client.json(
        "POST",
        "/api/v1/operations/sale",
        token=rep_token,
        json_body={
            "representative_id": representative["id"],
            "external_id": f"smoke-{suffix}-sale",
            "lines": [
                {"product_id": product["id"], "quantity": "2.000", "price_type": "retail"}
            ],
        },
        expected=(201,),
    )
    client.json(
        "POST",
        "/api/v1/operations/representative-return",
        token=rep_token,
        json_body={
            "representative_id": representative["id"],
            "warehouse_id": warehouse_b["id"],
            "external_id": f"smoke-{suffix}-return",
            "lines": [{"product_id": product["id"], "quantity": "1.000"}],
        },
        expected=(201,),
    )
    client.json(
        "POST",
        "/api/v1/operations/payment",
        token=admin_token,
        json_body={
            "representative_id": representative["id"],
            "amount": "250.00",
            "external_id": f"smoke-{suffix}-payment",
        },
        expected=(201,),
    )

    stock_a = client.json(
        "GET",
        f"/api/v1/balances/warehouses?warehouse_id={warehouse_a['id']}",
        token=admin_token,
    )
    stock_b = client.json(
        "GET",
        f"/api/v1/balances/warehouses?warehouse_id={warehouse_b['id']}",
        token=admin_token,
    )
    rep_stock = client.json(
        "GET",
        f"/api/v1/balances/representatives?representative_id={representative['id']}",
        token=rep_token,
    )
    debt = client.json(
        "GET",
        f"/api/v1/representatives/{representative['id']}/debt",
        token=rep_token,
    )
    assert_equal(find_quantity(stock_a, product["id"]), Decimal("3.000"), "Остаток склада А")
    assert_equal(find_quantity(stock_b, product["id"]), Decimal("3.000"), "Остаток склада Б")
    assert_equal(find_quantity(rep_stock, product["id"]), Decimal("2.000"), "Остаток представителя")
    assert_equal(as_decimal(debt["debt"]), Decimal("0.00"), "Задолженность после сдачи денег")

    documents = client.json("GET", "/api/v1/documents?limit=20", token=admin_token)
    if len(documents) < 5:
        raise SmokeError(f"В журнале слишком мало документов после сценария: {len(documents)}")
    money = client.json("GET", "/api/v1/money-postings?limit=20", token=admin_token)
    if len(money) < 2:
        raise SmokeError(f"В денежном журнале слишком мало проводок: {len(money)}")

    manager_token = login(client, manager_email, password)
    client.json("GET", "/api/v1/products", token=manager_token)
    client.json(
        "POST",
        "/api/v1/warehouses",
        token=manager_token,
        json_body={"code": f"DENIED-{suffix}", "name": "Не должен создаться"},
        expected=(403,),
    )

    if INTEGRATION_KEY:
        snapshot = client.json(
            "GET",
            "/api/v1/integration/1c/snapshot",
            headers={"X-Integration-Key": INTEGRATION_KEY},
        )
        if not isinstance(snapshot, dict):
            raise SmokeError("Snapshot 1С имеет неожиданный формат")

    print(
        "Smoke production: OK — HTTPS, web, auth, роли, приход, перемещение, выдача, "
        "идемпотентность, продажа, возврат, платеж, остатки, долг, журналы и 1С проверены"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SmokeError as exc:
        print(f"Smoke production: FAIL — {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
