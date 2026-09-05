#!/usr/bin/env python3
"""Создает первого администратора и проверяет вход без вывода токена."""

from __future__ import annotations

import getpass
import json
import os
import ssl
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_URL = os.getenv("CEH_BASE_URL", "https://127.0.0.1").rstrip("/")
INSECURE_TLS = os.getenv("CEH_INSECURE_TLS") == "1"
TIMEOUT = 15


def open_request(request: Request):
    context = None
    if BASE_URL.startswith("https://") and INSECURE_TLS:
        context = ssl._create_unverified_context()  # noqa: SLF001
    return urlopen(request, timeout=TIMEOUT, context=context)


def request_json(method: str, path: str, *, payload=None, form=None):
    headers = {"Accept": "application/json"}
    body = None
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    elif form is not None:
        body = urlencode(form).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"

    request = Request(f"{BASE_URL}{path}", data=body, headers=headers, method=method)
    try:
        with open_request(request) as response:
            data = response.read()
            return response.status, json.loads(data.decode("utf-8")) if data else None
    except HTTPError as exc:
        data = exc.read()
        try:
            detail = json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            detail = {"detail": data.decode("utf-8", errors="replace")}
        return exc.code, detail


def required_value(env_name: str, prompt: str, *, secret: bool = False) -> str:
    value = os.getenv(env_name, "").strip()
    if value:
        return value
    if not sys.stdin.isatty():
        raise RuntimeError(f"В неинтерактивном режиме задайте {env_name}")
    reader = getpass.getpass if secret else input
    value = reader(prompt).strip()
    if not value:
        raise RuntimeError(f"Поле {env_name} не может быть пустым")
    return value


def main() -> int:
    email = required_value("CEH_ADMIN_EMAIL", "Email первого администратора: ")
    full_name = required_value("CEH_ADMIN_NAME", "Имя администратора: ")
    password = required_value("CEH_ADMIN_PASSWORD", "Пароль: ", secret=True)
    if len(password) < 8:
        raise RuntimeError("Пароль должен содержать не менее 8 символов")

    status, response = request_json(
        "POST",
        "/api/v1/auth/bootstrap",
        payload={"email": email, "password": password, "full_name": full_name},
    )
    if status == 409:
        raise RuntimeError("Первый администратор уже создан. Используйте обычный вход в веб-панель")
    if status != 201:
        raise RuntimeError(f"Не удалось создать администратора: HTTP {status}: {response}")

    login_status, login_response = request_json(
        "POST",
        "/api/v1/auth/token",
        form={"username": email, "password": password},
    )
    if login_status != 200 or not isinstance(login_response, dict) or not login_response.get("access_token"):
        raise RuntimeError(f"Администратор создан, но проверка входа не прошла: HTTP {login_status}")

    print(f"Первый администратор создан: {email}")
    print(f"Вход проверен. Откройте веб-панель: {BASE_URL}/")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, URLError, TimeoutError) as exc:
        print(f"Ошибка первого запуска: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
