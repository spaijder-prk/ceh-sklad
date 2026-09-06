#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

API = "https://api.github.com"
RULESET_NAME = "Защита main"


def _request(method: str, url: str, token: str, payload: dict | None = None):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ceh-sklad-ruleset-applier/1",
            **({"Content-Type": "application/json"} if data is not None else {}),
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {exc.code}: {body[:1000]}") from exc


def main() -> int:
    token = os.environ.get("GITHUB_ADMIN_TOKEN") or os.environ.get("GH_TOKEN")
    repository = os.environ.get("GITHUB_REPOSITORY", "spaijder-prk/ceh-sklad").strip()
    if not token:
        print("Нужен GITHUB_ADMIN_TOKEN или GH_TOKEN с Repository administration: write.", file=sys.stderr)
        return 2
    if repository.count("/") != 1:
        print("GITHUB_REPOSITORY должен иметь формат owner/repo.", file=sys.stderr)
        return 2

    config_path = Path(__file__).resolve().parents[1] / ".github/rulesets/main.json"
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    rulesets = _request("GET", f"{API}/repos/{repository}/rulesets?includes_parents=false", token)
    existing = next((item for item in rulesets if item.get("name") == RULESET_NAME), None)

    if existing is None:
        result = _request("POST", f"{API}/repos/{repository}/rulesets", token, payload)
        print(f"Ruleset создан: id={result.get('id')}")
    else:
        result = _request("PUT", f"{API}/repos/{repository}/rulesets/{existing['id']}", token, payload)
        print(f"Ruleset обновлен: id={result.get('id')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
