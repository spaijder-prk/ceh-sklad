from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from .ceh_client import CehSkladClient
from .odata import FreshODataClient, ODataEntitySet
from .price_reader import FreshPriceReader, ProductPrices
from .schema_lock import validate_metadata_schema_lock
from .tenant_config import TenantMapping


_FIELD_RE = re.compile(r"^[A-Za-zА-Яа-яЁё0-9_]+$")
REQUIRED_PRODUCT_FIELDS = ("ref", "sku", "name")
DELETION_POLICIES = {"ignore", "skip", "block", "archive_if_zero_stock"}


@dataclass(frozen=True)
class ProductFieldMapping:
    fields: dict[str, str]
    deletion_policy: str = "ignore"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProductFieldMapping":
        fields = {
            str(key).strip(): str(value).strip()
            for key, value in dict(data.get("product_fields", {})).items()
        }
        deletion_policy = str(data.get("product_deletion_policy", "ignore")).strip().lower()
        if deletion_policy not in DELETION_POLICIES:
            raise ValueError(
                "product_deletion_policy должен быть ignore, skip, block или archive_if_zero_stock"
            )
        missing = [key for key in REQUIRED_PRODUCT_FIELDS if not fields.get(key)]
        if missing:
            raise ValueError("Не заданы product_fields: " + ", ".join(missing))
        allowed_aliases = {*REQUIRED_PRODUCT_FIELDS, "unit_name", "deletion_mark", "version"}
        for semantic, actual in fields.items():
            if semantic not in allowed_aliases:
                raise ValueError(f"Неизвестный product_fields alias: {semantic}")
            if not _FIELD_RE.fullmatch(actual):
                raise ValueError(f"product_fields.{semantic} должен быть прямым OData-полем")
        if deletion_policy != "ignore" and not fields.get("deletion_mark"):
            raise ValueError(
                f"Для product_deletion_policy={deletion_policy} требуется product_fields.deletion_mark"
            )
        if deletion_policy == "archive_if_zero_stock" and not fields.get("version"):
            raise ValueError(
                "Для archive_if_zero_stock требуется product_fields.version из $metadata УНФ"
            )
        return cls(fields=fields, deletion_policy=deletion_policy)

    @classmethod
    def load(cls, path: str | Path) -> "ProductFieldMapping":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("Tenant mapping должен быть JSON-объектом")
        return cls.from_dict(raw)

    def validate_against_metadata(self, entity_sets: list[ODataEntitySet], resource: str) -> None:
        entity = next((item for item in entity_sets if item.name == resource), None)
        if entity is None:
            raise ValueError(f"В $metadata отсутствует каталог номенклатуры {resource}")
        if not entity.properties:
            return
        missing = [field for field in self.fields.values() if field not in entity.properties]
        if missing:
            raise ValueError(
                "В $metadata каталога номенклатуры отсутствуют поля: " + ", ".join(missing)
            )


@dataclass(frozen=True)
class ProductImportPlan:
    external_ref: str
    sku: str
    name: str
    ready: bool
    blocking_reasons: tuple[str, ...]
    payload: dict[str, Any] | None
    action: str = "upsert"
    deletion_mark: bool = False


@dataclass(frozen=True)
class ProductImportSummary:
    total: int
    ready: int
    blocked: int
    skipped: int
    imported: int
    repeated: int
    messages: tuple[str, ...]


def _parse_deletion_mark(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1"}:
            return True
        if normalized in {"false", "0"}:
            return False
    raise ValueError("DeletionMark должен быть boolean из OData УНФ")


def _operation_key(
    payload: dict[str, Any],
    *,
    source_version: str | None = None,
    deletion_mark: bool | None = None,
) -> str:
    if source_version is None and deletion_mark is None:
        material: Any = payload
    else:
        material = {
            "payload": payload,
            "source_version": source_version,
            "deletion_mark": deletion_mark,
        }
    raw = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload_digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    ref_digest = hashlib.sha256(str(payload["external_1c_id"]).encode("utf-8")).hexdigest()
    return f"unf-product:{ref_digest[:16]}:{payload_digest[:24]}"


class FreshProductImporter:
    """Планирует и выполняет импорт номенклатуры и двух видов цен из УНФ."""

    def __init__(
        self,
        fresh_client: FreshODataClient,
        ceh_client: CehSkladClient,
        mapping: TenantMapping,
        product_mapping: ProductFieldMapping,
        *,
        price_reader: FreshPriceReader | None = None,
    ) -> None:
        self.fresh_client = fresh_client
        self.ceh_client = ceh_client
        self.mapping = mapping
        self.product_mapping = product_mapping
        self.price_reader = price_reader or FreshPriceReader(fresh_client, mapping)

    def plans(self, limit: int = 50) -> list[ProductImportPlan]:
        fields = self.product_mapping.fields
        selected = tuple(dict.fromkeys(fields.values()))
        rows = self.fresh_client.list(
            self.mapping.resources["products"],
            top=max(1, min(limit, 100)),
            select=selected,
        )
        result: list[ProductImportPlan] = []
        for row in rows:
            external_ref = str(row.get(fields["ref"], "")).strip()
            sku = str(row.get(fields["sku"], "")).strip()
            name = str(row.get(fields["name"], "")).strip()
            unit_name = (
                str(row.get(fields["unit_name"], "шт")).strip()
                if fields.get("unit_name")
                else "шт"
            ) or "шт"
            reasons: list[str] = []
            action = "upsert"
            marked_deleted = False
            source_version: str | None = None

            try:
                UUID(external_ref)
            except (ValueError, AttributeError):
                reasons.append("Ref_Key номенклатуры не является GUID")
            if not sku or len(sku) > 80:
                reasons.append("Некорректный артикул номенклатуры")
            if len(name) < 2 or len(name) > 200:
                reasons.append("Некорректное наименование номенклатуры")
            if len(unit_name) > 30:
                reasons.append("Наименование единицы измерения длиннее 30 символов")

            deletion_field = fields.get("deletion_mark")
            if deletion_field:
                try:
                    marked_deleted = _parse_deletion_mark(row.get(deletion_field))
                except ValueError as exc:
                    reasons.append(str(exc))

            if self.product_mapping.deletion_policy == "archive_if_zero_stock":
                version_field = fields.get("version")
                source_version = str(row.get(version_field, "")).strip() if version_field else ""
                if not source_version:
                    reasons.append("Не прочитана версия номенклатуры для безопасной идемпотентности")

            if marked_deleted and not reasons:
                policy = self.product_mapping.deletion_policy
                if policy == "skip":
                    action = "skip"
                elif policy == "block":
                    reasons.append("Товар помечен на удаление в УНФ: требуется ручное решение")
                elif policy == "archive_if_zero_stock":
                    check = self.ceh_client.product_archive_check(external_ref)
                    if not bool(check.get("exists", False)):
                        action = "skip"
                    elif not bool(check.get("is_active", False)):
                        action = "skip"
                    elif not bool(check.get("can_archive", False)):
                        reasons.append(
                            str(check.get("reason") or "Товар нельзя безопасно архивировать")
                        )

            prices = ProductPrices(retail=None, wholesale=None)
            if not reasons and action != "skip":
                prices = self.price_reader.product_prices(external_ref)
                if prices.retail is None:
                    reasons.append("Не найдена цена выбранного розничного вида")
                if prices.wholesale is None:
                    reasons.append("Не найдена цена выбранного оптового вида")

            payload: dict[str, Any] | None = None
            if not reasons and action != "skip":
                payload = {
                    "external_1c_id": external_ref,
                    "sku": sku,
                    "name": name,
                    "unit_name": unit_name,
                    "retail_price": str(Decimal(prices.retail)),
                    "wholesale_price": str(Decimal(prices.wholesale)),
                    "is_active": not marked_deleted,
                }
                key_version = (
                    source_version
                    if self.product_mapping.deletion_policy == "archive_if_zero_stock"
                    else None
                )
                key_mark = (
                    marked_deleted
                    if self.product_mapping.deletion_policy == "archive_if_zero_stock"
                    else None
                )
                payload["operation_key"] = _operation_key(
                    payload,
                    source_version=key_version,
                    deletion_mark=key_mark,
                )

            result.append(
                ProductImportPlan(
                    external_ref=external_ref,
                    sku=sku,
                    name=name,
                    ready=not reasons,
                    blocking_reasons=tuple(reasons),
                    payload=payload,
                    action=action,
                    deletion_mark=marked_deleted,
                )
            )
        return result

    def sync(self, *, limit: int = 50, execute: bool = False) -> ProductImportSummary:
        plans = self.plans(limit)
        ready = 0
        blocked = 0
        skipped = 0
        imported = 0
        repeated = 0
        messages: list[str] = []
        for plan in plans:
            if plan.action == "skip" and plan.ready:
                skipped += 1
                messages.append(
                    f"SKIPPED product {plan.sku or plan.external_ref}: DeletionMark={plan.deletion_mark}"
                )
                continue
            if not plan.ready or plan.payload is None:
                blocked += 1
                messages.append(
                    f"BLOCKED product {plan.sku or plan.external_ref}: "
                    + "; ".join(plan.blocking_reasons)
                )
                continue
            ready += 1
            messages.append(
                f"PLAN product {plan.sku}: external_1c_id={plan.external_ref}; "
                f"active={plan.payload['is_active']}; retail={plan.payload['retail_price']}; "
                f"wholesale={plan.payload['wholesale_price']}"
            )
            if execute:
                response = self.ceh_client.import_product(plan.payload)
                imported += 1
                if bool(response.get("repeated", False)):
                    repeated += 1
                messages.append(
                    f"IMPORTED product {plan.sku}: internal_id={response.get('internal_id')}; "
                    f"active={plan.payload['is_active']}; repeated={bool(response.get('repeated', False))}"
                )
        return ProductImportSummary(
            total=len(plans),
            ready=ready,
            blocked=blocked,
            skipped=skipped,
            imported=imported,
            repeated=repeated,
            messages=tuple(messages),
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Импорт номенклатуры и двух выбранных видов цен из 1С:УНФ в ceh-sklad"
    )
    parser.add_argument("--mapping", required=True, type=Path)
    parser.add_argument("--ceh-url", default=os.getenv("CEH_API_URL"))
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Разрешить запись в ceh-sklad; требует принятого schema lock",
    )
    parser.add_argument("--allow-http-ceh", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ceh_key = os.getenv("CEH_1C_KEY")
    fresh_login = os.getenv("UNF_FRESH_LOGIN")
    fresh_password = os.getenv("UNF_FRESH_PASSWORD")
    if not args.ceh_url:
        raise SystemExit("Не задан --ceh-url или CEH_API_URL")
    if not ceh_key:
        raise SystemExit("Не задан CEH_1C_KEY")
    if not fresh_login or not fresh_password:
        raise SystemExit("Задайте UNF_FRESH_LOGIN и UNF_FRESH_PASSWORD через secret storage")

    mapping = TenantMapping.load(args.mapping)
    product_mapping = ProductFieldMapping.load(args.mapping)
    with CehSkladClient(
        args.ceh_url,
        ceh_key,
        allow_http=args.allow_http_ceh,
    ) as ceh_client, FreshODataClient(
        mapping.application_url,
        fresh_login,
        fresh_password,
    ) as fresh_client:
        ceh_client.profile()
        metadata = fresh_client.entity_sets()
        mapping.validate_against_metadata(metadata)
        validate_metadata_schema_lock(
            mapping.application_url,
            metadata,
            mapping.expected_metadata_structure_sha256,
            require_schema_lock=args.execute,
        )
        product_mapping.validate_against_metadata(metadata, mapping.resources["products"])
        summary = FreshProductImporter(
            fresh_client,
            ceh_client,
            mapping,
            product_mapping,
        ).sync(limit=max(1, min(args.limit, 100)), execute=args.execute)

    for message in summary.messages:
        print(message)
    mode = "EXECUTE" if args.execute else "DRY-RUN"
    print(
        f"{mode}: товаров={summary.total}, готовы={summary.ready}, blocked={summary.blocked}, "
        f"skipped={summary.skipped}, импортировано={summary.imported}, повторных={summary.repeated}"
    )
    if not args.execute:
        print("Запись в ceh-sklad НЕ выполнялась. Для импорта нужен явный --execute.")
    if summary.blocked:
        sys.exit(3)


if __name__ == "__main__":
    main()
