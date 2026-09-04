from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from .ceh_client import CehSkladClient
from .odata import FreshODataClient, ODataEntitySet
from .tenant_config import TenantMapping


_FIELD_RE = re.compile(r"^[A-Za-zА-Яа-яЁё0-9_]+$")
LocationKind = Literal["warehouse", "representative"]


@dataclass(frozen=True)
class AllowedLocation:
    kind: LocationKind
    name_override: str | None = None


@dataclass(frozen=True)
class LocationImportMapping:
    ref_field: str
    name_field: str
    allowlist: dict[str, AllowedLocation]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LocationImportMapping":
        fields = {
            str(key).strip(): str(value).strip()
            for key, value in dict(data.get("location_fields", {})).items()
        }
        if not fields.get("ref") or not fields.get("name"):
            raise ValueError("location_fields должен содержать ref и name")
        for semantic in ("ref", "name"):
            if not _FIELD_RE.fullmatch(fields[semantic]):
                raise ValueError(f"location_fields.{semantic} должен быть прямым OData-полем")

        allowlist: dict[str, AllowedLocation] = {}
        for external_ref, raw in dict(data.get("location_allowlist", {})).items():
            ref = str(external_ref).strip().lower()
            try:
                UUID(ref)
            except (ValueError, AttributeError) as exc:
                raise ValueError(f"location_allowlist содержит некорректный Ref_Key: {external_ref}") from exc
            if not isinstance(raw, dict):
                raise ValueError(f"location_allowlist.{external_ref} должен быть JSON-объектом")
            kind = str(raw.get("kind", "")).strip()
            if kind not in {"warehouse", "representative"}:
                raise ValueError(f"Для склада {external_ref} kind должен быть warehouse или representative")
            override_raw = str(raw.get("name_override", "")).strip()
            name_override = override_raw or None
            if name_override is not None and (len(name_override) < 2 or len(name_override) > 150):
                raise ValueError(f"Некорректный name_override для склада {external_ref}")
            allowlist[ref] = AllowedLocation(kind=kind, name_override=name_override)  # type: ignore[arg-type]
        if not allowlist:
            raise ValueError("location_allowlist пуст: импорт складов без явного allow-list запрещен")
        return cls(
            ref_field=fields["ref"],
            name_field=fields["name"],
            allowlist=allowlist,
        )

    @classmethod
    def load(cls, path: str | Path) -> "LocationImportMapping":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("Tenant mapping должен быть JSON-объектом")
        return cls.from_dict(raw)

    def validate_against_metadata(self, entity_sets: list[ODataEntitySet], resource: str) -> None:
        entity = next((item for item in entity_sets if item.name == resource), None)
        if entity is None:
            raise ValueError(f"В $metadata отсутствует каталог складов {resource}")
        if not entity.properties:
            return
        missing = [field for field in (self.ref_field, self.name_field) if field not in entity.properties]
        if missing:
            raise ValueError("В $metadata каталога складов отсутствуют поля: " + ", ".join(missing))


@dataclass(frozen=True)
class LocationImportPlan:
    external_ref: str
    name: str
    kind: LocationKind
    ready: bool
    blocking_reasons: tuple[str, ...]
    payload: dict[str, Any] | None


@dataclass(frozen=True)
class LocationImportSummary:
    total: int
    ready: int
    blocked: int
    imported: int
    repeated: int
    messages: tuple[str, ...]


def _operation_key(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    ref_digest = hashlib.sha256(str(payload["external_1c_id"]).encode("utf-8")).hexdigest()
    return f"unf-location:{ref_digest[:16]}:{digest[:24]}"


class FreshLocationImporter:
    """Импортирует только явно разрешенные склады УНФ."""

    def __init__(
        self,
        fresh_client: FreshODataClient,
        ceh_client: CehSkladClient,
        mapping: TenantMapping,
        location_mapping: LocationImportMapping,
    ) -> None:
        self.fresh_client = fresh_client
        self.ceh_client = ceh_client
        self.mapping = mapping
        self.location_mapping = location_mapping

    def plans(self) -> list[LocationImportPlan]:
        resource = self.mapping.resources["warehouses"]
        config = self.location_mapping
        result: list[LocationImportPlan] = []
        for external_ref, allowed in sorted(config.allowlist.items()):
            rows = self.fresh_client.list(
                resource,
                top=2,
                select=(config.ref_field, config.name_field),
                filter_expression=f"{config.ref_field} eq guid'{external_ref}'",
            )
            reasons: list[str] = []
            source_name = ""
            if not rows:
                reasons.append("Разрешенный склад не найден в УНФ")
            elif len(rows) > 1:
                reasons.append("По Ref_Key найдено несколько складов УНФ")
            else:
                returned_ref = str(rows[0].get(config.ref_field, "")).strip().lower()
                if returned_ref != external_ref:
                    reasons.append("УНФ вернула склад с неожиданным Ref_Key")
                source_name = str(rows[0].get(config.name_field, "")).strip()

            name = allowed.name_override or source_name
            if len(name) < 2 or len(name) > 150:
                reasons.append("Некорректное имя склада")

            payload: dict[str, Any] | None = None
            if not reasons:
                payload = {
                    "external_1c_id": external_ref,
                    "name": name,
                    "kind": allowed.kind,
                }
                payload["operation_key"] = _operation_key(payload)
            result.append(
                LocationImportPlan(
                    external_ref=external_ref,
                    name=name,
                    kind=allowed.kind,
                    ready=not reasons,
                    blocking_reasons=tuple(reasons),
                    payload=payload,
                )
            )
        return result

    def sync(self, *, execute: bool = False) -> LocationImportSummary:
        plans = self.plans()
        ready = 0
        blocked = 0
        imported = 0
        repeated = 0
        messages: list[str] = []
        for plan in plans:
            if not plan.ready or plan.payload is None:
                blocked += 1
                messages.append(
                    f"BLOCKED location {plan.external_ref}: " + "; ".join(plan.blocking_reasons)
                )
                continue
            ready += 1
            messages.append(
                f"PLAN location {plan.name}: external_1c_id={plan.external_ref}; kind={plan.kind}"
            )
            if execute:
                response = self.ceh_client.import_location(plan.payload)
                imported += 1
                if bool(response.get("repeated", False)):
                    repeated += 1
                messages.append(
                    f"IMPORTED location {plan.name}: internal_id={response.get('internal_id')}; "
                    f"repeated={bool(response.get('repeated', False))}"
                )
        return LocationImportSummary(
            total=len(plans),
            ready=ready,
            blocked=blocked,
            imported=imported,
            repeated=repeated,
            messages=tuple(messages),
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Импорт явно разрешенных складов 1С:УНФ в ceh-sklad"
    )
    parser.add_argument("--mapping", required=True, type=Path)
    parser.add_argument("--ceh-url", default=os.getenv("CEH_API_URL"))
    parser.add_argument("--execute", action="store_true")
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
    location_mapping = LocationImportMapping.load(args.mapping)
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
        location_mapping.validate_against_metadata(metadata, mapping.resources["warehouses"])
        summary = FreshLocationImporter(
            fresh_client,
            ceh_client,
            mapping,
            location_mapping,
        ).sync(execute=args.execute)

    for message in summary.messages:
        print(message)
    mode = "EXECUTE" if args.execute else "DRY-RUN"
    print(
        f"{mode}: складов={summary.total}, готовы={summary.ready}, blocked={summary.blocked}, "
        f"импортировано={summary.imported}, повторных={summary.repeated}"
    )
    if not args.execute:
        print("Запись в ceh-sklad НЕ выполнялась. Для импорта нужен явный --execute.")
    if summary.blocked:
        sys.exit(3)


if __name__ == "__main__":
    main()
