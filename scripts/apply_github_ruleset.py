#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API = "https://api.github.com"
RULESET_NAME = "Защита main"


def _request(method: str, url: str, token: str | None, payload: dict | None = None):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ceh-sklad-ruleset-applier/2",
        **({"Content-Type": "application/json"} if data is not None else {}),
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = Request(url, data=data, method=method, headers=headers)
    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {exc.code}: {body[:1000]}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"GitHub API недоступен: {exc}") from exc


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Применить или read-only проверить repository ruleset защиты main"
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Только проверить существующий ruleset; POST/PUT не выполняются",
    )
    return parser.parse_args()


def _set_values(value) -> set[str]:
    return {str(item) for item in (value or [])}


def validate_ruleset(actual: dict, expected: dict) -> list[str]:
    errors: list[str] = []

    for key in ("name", "target", "enforcement"):
        if actual.get(key) != expected.get(key):
            errors.append(f"{key}: ожидалось {expected.get(key)!r}, получено {actual.get(key)!r}")

    if list(actual.get("bypass_actors") or []) != list(expected.get("bypass_actors") or []):
        errors.append("bypass_actors отличается от декларации")

    actual_ref = (actual.get("conditions") or {}).get("ref_name") or {}
    expected_ref = (expected.get("conditions") or {}).get("ref_name") or {}
    for key in ("include", "exclude"):
        if _set_values(actual_ref.get(key)) != _set_values(expected_ref.get(key)):
            errors.append(f"conditions.ref_name.{key} отличается от декларации")

    actual_rules = {
        str(rule.get("type")): rule
        for rule in (actual.get("rules") or [])
        if isinstance(rule, dict) and rule.get("type")
    }
    expected_rules = {
        str(rule.get("type")): rule
        for rule in (expected.get("rules") or [])
        if isinstance(rule, dict) and rule.get("type")
    }
    if set(actual_rules) != set(expected_rules):
        errors.append(
            "набор rules отличается: "
            f"ожидалось {sorted(expected_rules)}, получено {sorted(actual_rules)}"
        )

    pull_request_expected = (expected_rules.get("pull_request") or {}).get("parameters") or {}
    pull_request_actual = (actual_rules.get("pull_request") or {}).get("parameters") or {}
    for key, expected_value in pull_request_expected.items():
        if pull_request_actual.get(key) != expected_value:
            errors.append(
                f"pull_request.{key}: ожидалось {expected_value!r}, "
                f"получено {pull_request_actual.get(key)!r}"
            )

    status_expected = (expected_rules.get("required_status_checks") or {}).get("parameters") or {}
    status_actual = (actual_rules.get("required_status_checks") or {}).get("parameters") or {}
    for key in ("strict_required_status_checks_policy", "do_not_enforce_on_create"):
        if status_actual.get(key) != status_expected.get(key):
            errors.append(
                f"required_status_checks.{key}: ожидалось {status_expected.get(key)!r}, "
                f"получено {status_actual.get(key)!r}"
            )

    expected_contexts = {
        str(item.get("context"))
        for item in status_expected.get("required_status_checks") or []
        if isinstance(item, dict) and item.get("context")
    }
    actual_contexts = {
        str(item.get("context"))
        for item in status_actual.get("required_status_checks") or []
        if isinstance(item, dict) and item.get("context")
    }
    if actual_contexts != expected_contexts:
        errors.append(
            "required status checks отличаются: "
            f"ожидалось {sorted(expected_contexts)}, получено {sorted(actual_contexts)}"
        )

    return errors


def _read_full_ruleset(repository: str, ruleset_id: int, token: str | None) -> dict:
    result = _request("GET", f"{API}/repos/{repository}/rulesets/{ruleset_id}", token)
    if not isinstance(result, dict):
        raise RuntimeError("GitHub API не вернул объект ruleset")
    return result


def _verify_ruleset(repository: str, ruleset_id: int, token: str | None, expected: dict) -> dict:
    actual = _read_full_ruleset(repository, ruleset_id, token)
    errors = validate_ruleset(actual, expected)
    if errors:
        details = "\n".join(f"- {item}" for item in errors)
        raise RuntimeError(f"Ruleset {RULESET_NAME!r} не соответствует декларации:\n{details}")
    return actual


def main() -> int:
    args = _parse_args()
    token = os.environ.get("GITHUB_ADMIN_TOKEN") or os.environ.get("GH_TOKEN")
    repository = os.environ.get("GITHUB_REPOSITORY", "spaijder-prk/ceh-sklad").strip()
    if not args.check_only and not token:
        print("Нужен GITHUB_ADMIN_TOKEN или GH_TOKEN с Repository administration: write.", file=sys.stderr)
        return 2
    if repository.count("/") != 1:
        print("GITHUB_REPOSITORY должен иметь формат owner/repo.", file=sys.stderr)
        return 2

    config_path = Path(__file__).resolve().parents[1] / ".github/rulesets/main.json"
    expected = json.loads(config_path.read_text(encoding="utf-8"))

    try:
        rulesets = _request(
            "GET",
            f"{API}/repos/{repository}/rulesets?includes_parents=false",
            token,
        )
        if not isinstance(rulesets, list):
            raise RuntimeError("GitHub API не вернул список rulesets")
        existing = next((item for item in rulesets if item.get("name") == RULESET_NAME), None)

        if args.check_only:
            if existing is None:
                raise RuntimeError(f"Ruleset {RULESET_NAME!r} не найден")
            actual = _verify_ruleset(repository, int(existing["id"]), token, expected)
            print(
                "Ruleset проверен: "
                f"id={actual.get('id')}, enforcement={actual.get('enforcement')}, target={actual.get('target')}"
            )
            return 0

        if existing is None:
            result = _request("POST", f"{API}/repos/{repository}/rulesets", token, expected)
            if not isinstance(result, dict) or not result.get("id"):
                raise RuntimeError("GitHub API не вернул id созданного ruleset")
            print(f"Ruleset создан: id={result.get('id')}")
        else:
            result = _request(
                "PUT",
                f"{API}/repos/{repository}/rulesets/{existing['id']}",
                token,
                expected,
            )
            if not isinstance(result, dict) or not result.get("id"):
                raise RuntimeError("GitHub API не вернул id обновлённого ruleset")
            print(f"Ruleset обновлен: id={result.get('id')}")

        actual = _verify_ruleset(repository, int(result["id"]), token, expected)
        print(
            "Проверка после применения успешна: "
            f"enforcement={actual.get('enforcement')}, target={actual.get('target')}"
        )
        return 0
    except RuntimeError as exc:
        print(f"Ошибка ruleset: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
