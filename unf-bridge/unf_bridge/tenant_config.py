from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .odata import ODataEntitySet


_GUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

REQUIRED_RESOURCES = (
    "products",
    "price_types",
    "prices",
    "warehouses",
    "organizations",
    "counterparties",
    "transfer",
    "sale",
    "cash_receipt",
    "stock_receipt",
    "stock_writeoff",
)
DOCUMENT_RESOURCES = (
    "transfer",
    "sale",
    "cash_receipt",
    "stock_receipt",
    "stock_writeoff",
)
REQUIRED_CONSTANTS = (
    "retail_price_type_ref",
    "wholesale_price_type_ref",
)
REQUIRED_PRICE_FIELDS = (
    "product_ref",
    "price_type_ref",
    "value",
)


@dataclass(frozen=True)
class TenantMapping:
    provider: str
    application_url: str
    timezone: str
    post_documents: bool
    resources: dict[str, str]
    external_key_fields: dict[str, str]
    price_fields: dict[str, str]
    constants: dict[str, str]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TenantMapping":
        provider = str(data.get("provider", "")).strip()
        application_url = str(data.get("application_url", "")).rstrip("/")
        timezone = str(data.get("timezone", "")).strip()
        resources = {str(key): str(value).strip() for key, value in dict(data.get("resources", {})).items()}
        external_key_fields = {
            str(key): str(value).strip()
            for key, value in dict(data.get("external_key_fields", {})).items()
        }
        price_fields = {str(key): str(value).strip() for key, value in dict(data.get("price_fields", {})).items()}
        constants = {str(key): str(value).strip() for key, value in dict(data.get("constants", {})).items()}

        if provider not in {"1cfresh", "other"}:
            raise ValueError("provider должен быть 1cfresh или other")
        parsed = urlparse(application_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("application_url должен быть полноценным HTTPS URL")
        if not timezone:
            raise ValueError("Не задан timezone базы УНФ")

        missing_resources = [key for key in REQUIRED_RESOURCES if not resources.get(key)]
        if missing_resources:
            raise ValueError("Не заданы OData resources: " + ", ".join(missing_resources))
        missing_external_fields = [key for key in DOCUMENT_RESOURCES if not external_key_fields.get(key)]
        if missing_external_fields:
            raise ValueError(
                "Не заданы поля устойчивого внешнего ключа: " + ", ".join(missing_external_fields)
            )
        missing_price_fields = [key for key in REQUIRED_PRICE_FIELDS if not price_fields.get(key)]
        if missing_price_fields:
            raise ValueError("Не заданы поля регистра цен УНФ: " + ", ".join(missing_price_fields))
        missing_constants = [key for key in REQUIRED_CONSTANTS if not constants.get(key)]
        if missing_constants:
            raise ValueError(
                "Не заданы обязательные сопоставления видов цен УНФ: " + ", ".join(missing_constants)
            )

        for key, value in constants.items():
            if key.endswith("_ref") and value and not _GUID_RE.fullmatch(value):
                raise ValueError(f"{key} должен содержать Ref_Key GUID из УНФ")
        if constants["retail_price_type_ref"].lower() == constants["wholesale_price_type_ref"].lower():
            raise ValueError("Розничный и оптовый виды цен УНФ должны быть разными")

        return cls(
            provider=provider,
            application_url=application_url,
            timezone=timezone,
            post_documents=bool(data.get("post_documents", False)),
            resources=resources,
            external_key_fields=external_key_fields,
            price_fields=price_fields,
            constants=constants,
        )

    @classmethod
    def load(cls, path: str | Path) -> "TenantMapping":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("Tenant mapping должен быть JSON-объектом")
        return cls.from_dict(raw)

    def validate_against_metadata(self, entity_sets: list[ODataEntitySet]) -> None:
        by_name = {item.name: item for item in entity_sets}
        missing = sorted({resource for resource in self.resources.values() if resource not in by_name})
        if missing:
            raise ValueError(
                "В $metadata tenant отсутствуют настроенные OData resources: " + ", ".join(missing)
            )

        missing_fields: list[str] = []
        for alias in DOCUMENT_RESOURCES:
            resource = self.resources[alias]
            field = self.external_key_fields[alias]
            properties = by_name[resource].properties
            if properties and field not in properties:
                missing_fields.append(f"{alias}: {resource}.{field}")

        price_resource = self.resources["prices"]
        price_properties = by_name[price_resource].properties
        if price_properties:
            for alias in REQUIRED_PRICE_FIELDS:
                field = self.price_fields[alias]
                if field not in price_properties:
                    missing_fields.append(f"prices: {price_resource}.{field}")

        if missing_fields:
            raise ValueError(
                "В $metadata tenant отсутствуют настроенные поля: " + ", ".join(missing_fields)
            )

    def public_summary(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "application_url": self.application_url,
            "timezone": self.timezone,
            "post_documents": self.post_documents,
            "resources": dict(self.resources),
            "configured_constants": sorted(key for key, value in self.constants.items() if value),
        }
