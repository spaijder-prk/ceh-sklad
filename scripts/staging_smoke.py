from __future__ import annotations

import argparse
import asyncio
import os
from urllib.parse import urlencode, urlparse

import httpx
import websockets


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only smoke-проверка staging-контура ceh-sklad")
    parser.add_argument("--base-url", required=True, help="HTTPS origin, например https://staging-sklad.example.ru")
    parser.add_argument("--expected-location-id", required=True, help="Ожидаемый виртуальный склад представителя")
    parser.add_argument("--timeout", type=float, default=15.0)
    return parser.parse_args()


def validate_base_url(value: str) -> str:
    base_url = value.rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("Staging smoke разрешен только для полноценного HTTPS URL")
    return base_url


async def main() -> None:
    args = parse_args()
    base_url = validate_base_url(args.base_url)
    login = os.getenv("CEH_STAGING_REP_LOGIN")
    password = os.getenv("CEH_STAGING_REP_PASSWORD")
    integration_key = os.getenv("CEH_STAGING_1C_KEY")
    if not login or not password:
        raise RuntimeError("Задайте CEH_STAGING_REP_LOGIN и CEH_STAGING_REP_PASSWORD через GitHub Secrets")

    timeout = httpx.Timeout(args.timeout)
    async with httpx.AsyncClient(base_url=base_url, timeout=timeout, follow_redirects=False) as client:
        ready = await client.get("/health/ready")
        ready.raise_for_status()
        ready_data = ready.json()
        if ready_data.get("status") != "ready" or ready_data.get("database") != "ok":
            raise RuntimeError(f"Readiness вернул неожиданный ответ: {ready_data}")
        print(f"Readiness: БД доступна, схема {ready_data.get('schema_revision')}")

        login_response = await client.post(
            "/api/v1/auth/login",
            json={"login": login, "password": password},
        )
        login_response.raise_for_status()
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        me = await client.get("/api/v1/auth/me", headers=headers)
        me.raise_for_status()
        user = me.json()
        if user.get("role") != "representative":
            raise RuntimeError("Staging smoke должен использовать учетную запись representative")
        if user.get("location_id") != args.expected_location_id:
            raise RuntimeError(
                f"У представителя другой виртуальный склад: {user.get('location_id')} != {args.expected_location_id}"
            )
        print(f"Авторизация: {user.get('name')} / {user.get('login')}")

        stocks = await client.get(
            "/api/v1/stocks",
            params={"location_id": args.expected_location_id},
            headers=headers,
        )
        stocks.raise_for_status()
        stock_rows = stocks.json()
        print(f"Остатки представителя: {len(stock_rows)} позиций")

        debt = await client.get(
            f"/api/v1/representatives/{args.expected_location_id}/debt",
            headers=headers,
        )
        debt.raise_for_status()
        print(f"Задолженность читается: {debt.json().get('debt')}")

        stock_history = await client.get("/api/v1/operations/stock", params={"limit": 1}, headers=headers)
        money_history = await client.get("/api/v1/operations/money", params={"limit": 1}, headers=headers)
        stock_history.raise_for_status()
        money_history.raise_for_status()
        print("История товарных и денежных операций читается")

        if integration_key:
            outbox = await client.get(
                "/api/v1/integration/1c/outbox",
                params={"limit": 1},
                headers={"X-1C-Key": integration_key},
            )
            outbox.raise_for_status()
            print(f"Контур 1С: ключ принят, outbox доступен ({len(outbox.json())} элементов в выборке)")
        else:
            print("Контур 1С: пропущен, CEH_STAGING_1C_KEY не задан")

    parsed = urlparse(base_url)
    websocket_scheme = "wss"
    query = urlencode({"token": token, "location_id": args.expected_location_id})
    ws_url = f"{websocket_scheme}://{parsed.netloc}/api/v1/realtime?{query}"
    async with websockets.connect(ws_url, open_timeout=args.timeout, close_timeout=args.timeout) as socket:
        await socket.send("staging-smoke")
        print("WebSocket: WSS handshake и отправка сообщения успешны")

    print("Staging smoke завершен успешно. Изменяющие операции не выполнялись.")


if __name__ == "__main__":
    asyncio.run(main())
