from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable, Mapping

from .tenant_config import DocumentPayloadMapping, TenantMapping


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


def _map_values(
    configured_fields: Mapping[str, str],
    values: Mapping[str, Any],
    *,
    scope: str,
) -> dict[str, Any]:
    unknown = sorted(set(values) - set(configured_fields))
    if unknown:
        raise ValueError(
            f"Для {scope} не настроены semantic aliases: " + ", ".join(unknown)
        )
    result: dict[str, Any] = {}
    for semantic, value in values.items():
        if value is None:
            continue
        result[configured_fields[semantic]] = _json_value(value)
    return result


class MappedDocumentPayloadBuilder:
    """Строит OData JSON по semantic values и tenant-specific mapping.

    Builder не знает русские имена реквизитов конкретной версии УНФ. Он только
    применяет mapping, который заранее проверяется против `$metadata`.
    """

    def __init__(self, mapping: TenantMapping) -> None:
        self.mapping = mapping

    def schema(self, alias: str) -> DocumentPayloadMapping:
        try:
            return self.mapping.payload_schemas[alias]
        except KeyError as exc:
            raise ValueError(
                f"Для документа {alias} не задан payload_schemas в tenant mapping"
            ) from exc

    def build(
        self,
        alias: str,
        header_values: Mapping[str, Any],
        rows: Iterable[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        schema = self.schema(alias)
        payload = _map_values(
            schema.header_fields,
            header_values,
            scope=f"шапки {alias}",
        )

        if rows is None:
            return payload
        if schema.table is None:
            raise ValueError(f"Для документа {alias} не настроена табличная часть")

        mapped_rows: list[dict[str, Any]] = []
        for line_number, values in enumerate(rows, start=1):
            row = _map_values(
                schema.table.fields,
                values,
                scope=f"строки {alias}",
            )
            row["LineNumber"] = line_number
            mapped_rows.append(row)
        payload[schema.table.property] = mapped_rows
        return payload
