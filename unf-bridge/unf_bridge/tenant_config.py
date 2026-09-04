from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .odata import ODataEntitySet, validate_field_path


_GUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_RESOURCE_RE = re.compile(r"^[A-Za-zА-Яа-яЁё0-9_]+$")

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


def _metadata_has_path(entity: ODataEntitySet, path: str) -> bool:
    root = path.split("/", 1)[0]
    return root in entity.properties or root in {item.name for item in entity.navigation}


def _validate_direct_field(value: str, *, description: str) -> str:
    if not value or not _RESOURCE_RE.fullmatch(value) or "/" in value:
        raise ValueError(f"{description} должно быть прямым OData-полем")
    return value


def _validate_semantic_name(value: str) -> str:
    if not value or not _RESOURCE_RE.fullmatch(value):
        raise ValueError("Некорректный semantic alias tenant mapping")
    return value


@dataclass(frozen=True)
class ReferenceCheck:
    name: str
    resource: str
    ref_key: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReferenceCheck":
        name = _validate_semantic_name(str(data.get("name", "")).strip())
        resource = _validate_direct_field(
            str(data.get("resource", "")).strip(),
            description=f"EntitySet reference_checks.{name}",
        )
        ref_key = str(data.get("ref_key", "")).strip()
        if not _GUID_RE.fullmatch(ref_key):
            raise ValueError(f"reference_checks.{name}.ref_key должен быть GUID из УНФ")
        return cls(name=name, resource=resource, ref_key=ref_key)


@dataclass(frozen=True)
class DocumentTableMapping:
    property: str
    row_resource: str
    fields: dict[str, str]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DocumentTableMapping":
        property_name = _validate_direct_field(
            str(data.get("property", "")).strip(),
            description="Имя табличной части",
        )
        row_resource = _validate_direct_field(
            str(data.get("row_resource", "")).strip(),
            description="EntitySet строки табличной части",
        )
        fields: dict[str, str] = {}
        for semantic, actual in dict(data.get("fields", {})).items():
            semantic_name = _validate_semantic_name(str(semantic).strip())
            actual_name = _validate_direct_field(
                str(actual).strip(),
                description=f"Поле строки {semantic_name}",
            )
            if actual_name == "LineNumber":
                raise ValueError("LineNumber управляется bridge и не задается в fields")
            fields[semantic_name] = actual_name
        if not fields:
            raise ValueError("Для табличной части не заданы поля строк")
        return cls(property=property_name, row_resource=row_resource, fields=fields)


@dataclass(frozen=True)
class DocumentPayloadMapping:
    header_fields: dict[str, str]
    table: DocumentTableMapping | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DocumentPayloadMapping":
        header_fields: dict[str, str] = {}
        for semantic, actual in dict(data.get("header_fields", {})).items():
            semantic_name = _validate_semantic_name(str(semantic).strip())
            header_fields[semantic_name] = _validate_direct_field(
                str(actual).strip(),
                description=f"Поле шапки {semantic_name}",
            )
        table_raw = data.get("table")
        if table_raw is not None and not isinstance(table_raw, dict):
            raise ValueError("table в payload_schemas должен быть JSON-объектом")
        return cls(
            header_fields=header_fields,
            table=DocumentTableMapping.from_dict(table_raw) if isinstance(table_raw, dict) else None,
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
    payload_schemas: dict[str, DocumentPayloadMapping]
    representative_payer_refs: dict[str, str]
    reference_checks: tuple[ReferenceCheck, ...] = ()

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
        representative_payer_refs = {
            str(key).strip(): str(value).strip()
            for key, value in dict(data.get("representative_payer_refs", {})).items()
        }

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
        for alias, field in external_key_fields.items():
            if alias in DOCUMENT_RESOURCES:
                _validate_direct_field(field, description=f"Поле устойчивого ключа {alias}")

        missing_price_fields = [key for key in REQUIRED_PRICE_FIELDS if not price_fields.get(key)]
        if missing_price_fields:
            raise ValueError("Не заданы поля регистра цен УНФ: " + ", ".join(missing_price_fields))
        for alias, field in price_fields.items():
            if alias in REQUIRED_PRICE_FIELDS:
                validate_field_path(field)

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

        for representative_external_id, payer_ref in representative_payer_refs.items():
            if not representative_external_id:
                raise ValueError("Пустой external_1c_id представителя в representative_payer_refs")
            if not _GUID_RE.fullmatch(payer_ref):
                raise ValueError(
                    f"Плательщик представителя {representative_external_id} должен быть Ref_Key GUID из УНФ"
                )

        reference_checks_raw = data.get("reference_checks", [])
        if not isinstance(reference_checks_raw, list):
            raise ValueError("reference_checks должен быть JSON-массивом")
        reference_checks: list[ReferenceCheck] = []
        reference_names: set[str] = set()
        for index, raw_check in enumerate(reference_checks_raw):
            if not isinstance(raw_check, dict):
                raise ValueError(f"reference_checks[{index}] должен быть JSON-объектом")
            check = ReferenceCheck.from_dict(raw_check)
            if check.name in reference_names:
                raise ValueError(f"Дублируется reference_checks.{check.name}")
            reference_names.add(check.name)
            reference_checks.append(check)

        payload_schemas: dict[str, DocumentPayloadMapping] = {}
        for alias, raw_schema in dict(data.get("payload_schemas", {})).items():
            alias_name = _validate_semantic_name(str(alias).strip())
            if alias_name not in DOCUMENT_RESOURCES:
                raise ValueError(f"Неизвестный документ в payload_schemas: {alias_name}")
            if not isinstance(raw_schema, dict):
                raise ValueError(f"payload_schemas.{alias_name} должен быть JSON-объектом")
            payload_schemas[alias_name] = DocumentPayloadMapping.from_dict(raw_schema)

        return cls(
            provider=provider,
            application_url=application_url,
            timezone=timezone,
            post_documents=bool(data.get("post_documents", False)),
            resources=resources,
            external_key_fields=external_key_fields,
            price_fields=price_fields,
            constants=constants,
            payload_schemas=payload_schemas,
            representative_payer_refs=representative_payer_refs,
            reference_checks=tuple(reference_checks),
        )

    @classmethod
    def load(cls, path: str | Path) -> "TenantMapping":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("Tenant mapping должен быть JSON-объектом")
        return cls.from_dict(raw)

    def validate_against_metadata(self, entity_sets: list[ODataEntitySet]) -> None:
        by_name = {item.name: item for item in entity_sets}
        configured_resources = set(self.resources.values()) | {check.resource for check in self.reference_checks}
        missing = sorted(resource for resource in configured_resources if resource not in by_name)
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
        price_entity = by_name[price_resource]
        if price_entity.properties or price_entity.navigation:
            for alias in REQUIRED_PRICE_FIELDS:
                field = self.price_fields[alias]
                if not _metadata_has_path(price_entity, field):
                    missing_fields.append(f"prices: {price_resource}.{field}")

        for alias, schema in self.payload_schemas.items():
            document_resource = self.resources[alias]
            document_entity = by_name[document_resource]

            if document_entity.properties:
                for semantic, field in schema.header_fields.items():
                    if field not in document_entity.properties:
                        missing_fields.append(
                            f"payload {alias}.{semantic}: {document_resource}.{field}"
                        )

            if schema.table is None:
                continue

            table_name = schema.table.property
            table_field = next((field for field in document_entity.fields if field.name == table_name), None)
            table_navigation = next(
                (item for item in document_entity.navigation if item.name == table_name),
                None,
            )
            if document_entity.properties or document_entity.navigation:
                if table_field is None and table_navigation is None:
                    missing_fields.append(
                        f"payload {alias}.table: {document_resource}.{table_name}"
                    )
                else:
                    collection_type = (
                        table_field.edm_type if table_field is not None else table_navigation.target_type
                    )
                    if collection_type != "unknown" and not collection_type.startswith("Collection("):
                        missing_fields.append(
                            f"payload {alias}.table: {document_resource}.{table_name} не Collection"
                        )

            row_entity = by_name.get(schema.table.row_resource)
            if row_entity is None:
                missing.append(schema.table.row_resource)
                continue
            if row_entity.properties:
                if "LineNumber" not in row_entity.properties:
                    missing_fields.append(
                        f"payload {alias}.table: {schema.table.row_resource}.LineNumber"
                    )
                for semantic, field in schema.table.fields.items():
                    if field not in row_entity.properties:
                        missing_fields.append(
                            f"payload {alias}.row.{semantic}: {schema.table.row_resource}.{field}"
                        )

        if missing:
            raise ValueError(
                "В $metadata tenant отсутствуют настроенные OData resources: "
                + ", ".join(sorted(set(missing)))
            )
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
            "payload_schemas": sorted(self.payload_schemas),
            "representative_payer_mappings": len(self.representative_payer_refs),
            "reference_checks": [check.name for check in self.reference_checks],
            "configured_constants": sorted(key for key, value in self.constants.items() if value),
        }
