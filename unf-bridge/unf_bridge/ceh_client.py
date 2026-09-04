from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from .models import UnfOutboxItem, UnfProfile


class CehSkladClient:
    def __init__(
        self,
        base_url: str,
        integration_key: str,
        *,
        timeout: float = 20.0,
        allow_http: bool = False,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        normalized = base_url.rstrip("/")
        parsed = urlparse(normalized)
        if not parsed.netloc or parsed.scheme not in ({"http", "https"} if allow_http else {"https"}):
            raise ValueError("URL ceh-sklad должен быть полноценным HTTPS URL")
        if not integration_key:
            raise ValueError("Не задан сервисный ключ ceh-sklad")
        self._client = httpx.Client(
            base_url=normalized,
            timeout=timeout,
            headers={"X-1C-Key": integration_key},
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "CehSkladClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def readiness(self) -> dict[str, Any]:
        response = self._client.get("/health/ready")
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise RuntimeError("ceh-sklad вернул неожиданный ответ readiness")
        return dict(body)

    def profile(self) -> UnfProfile:
        response = self._client.get("/api/v1/integration/1c/unf/profile")
        response.raise_for_status()
        profile = UnfProfile.from_json(response.json())
        if profile.target_configuration != "1С:Управление нашей фирмой" or profile.deployment != "cloud":
            raise RuntimeError("ceh-sklad вернул неподдерживаемый профиль интеграции")
        if profile.contract_version != "unf-cloud-v2":
            raise RuntimeError(
                f"Bridge ожидает unf-cloud-v2, сервер вернул {profile.contract_version}"
            )
        return profile

    def outbox(self, limit: int = 50) -> list[UnfOutboxItem]:
        response = self._client.get(
            "/api/v1/integration/1c/unf/outbox",
            params={"limit": max(1, min(limit, 100))},
        )
        response.raise_for_status()
        return [UnfOutboxItem.from_json(row) for row in response.json()]

    def import_product(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._client.post("/api/v1/integration/1c/products", json=payload)
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise RuntimeError("ceh-sklad вернул неожиданный ответ импорта товара")
        return dict(body)

    def import_location(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._client.post("/api/v1/integration/1c/locations", json=payload)
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise RuntimeError("ceh-sklad вернул неожиданный ответ импорта склада")
        return dict(body)

    def confirm_single(self, profile: UnfProfile, item: UnfOutboxItem, external_1c_id: str) -> None:
        response = self._client.post(
            profile.confirm_export_path,
            json={
                "entity_type": item.entity_type,
                "internal_id": item.internal_id,
                "external_1c_id": external_1c_id,
            },
        )
        response.raise_for_status()

    def confirm_batch(
        self,
        profile: UnfProfile,
        item: UnfOutboxItem,
        documents: list[tuple[str, str]],
    ) -> None:
        response = self._client.post(
            profile.confirm_export_batch_path,
            json={
                "entity_type": item.entity_type,
                "internal_id": item.internal_id,
                "documents": [
                    {"external_1c_id": external_id, "external_kind": external_kind}
                    for external_id, external_kind in documents
                ],
            },
        )
        response.raise_for_status()
