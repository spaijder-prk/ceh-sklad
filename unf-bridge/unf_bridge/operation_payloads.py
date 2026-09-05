from __future__ import annotations

from decimal import Decimal
from typing import Any

from .models import UnfLine, UnfOutboxItem
from .payload_builder import MappedDocumentPayloadBuilder
from .planner import PlannedDocument
from .tenant_config import TenantMapping


DOCUMENT_ALIASES = {
    "Перемещение запасов": "transfer",
    "Расходная накладная": "sale",
    "Поступление в кассу": "cash_receipt",
    "Оприходование запасов": "stock_receipt",
    "Списание запасов": "stock_writeoff",
}

REQUIRED_HEADERS = {
    "transfer": {"date", "organization_ref", "source_location_ref", "destination_location_ref"},
    "sale": {"date", "organization_ref", "warehouse_ref", "customer_ref"},
    "cash_receipt": {"date", "organization_ref", "cashbox_ref", "cash_flow_item_ref", "payer_ref", "amount"},
    "stock_receipt": {"date", "organization_ref", "warehouse_ref"},
    "stock_writeoff": {"date", "organization_ref", "warehouse_ref"},
}
REQUIRED_ROW_FIELDS = {
    "transfer": {"product_ref", "quantity"},
    "sale": {"product_ref", "quantity", "unit_price"},
    "stock_receipt": {"product_ref", "quantity"},
    "stock_writeoff": {"product_ref", "quantity"},
}


def _required(value: Any, message: str) -> Any:
    if value is None or value == "":
        raise ValueError(message)
    return value


class UnfOperationPayloadFactory:
    """Преобразует смысл outbox в tenant-specific OData JSON через проверенный mapping."""

    def __init__(self, mapping: TenantMapping) -> None:
        self.mapping = mapping
        self.builder = MappedDocumentPayloadBuilder(mapping)

    def __call__(self, item: UnfOutboxItem, document: PlannedDocument) -> dict[str, Any]:
        try:
            alias = DOCUMENT_ALIASES[document.unf_document]
        except KeyError as exc:
            raise ValueError(f"Неизвестный документ УНФ: {document.unf_document}") from exc

        schema = self.builder.schema(alias)
        missing_headers = sorted(REQUIRED_HEADERS[alias] - set(schema.header_fields))
        if missing_headers:
            raise ValueError(
                f"payload_schemas.{alias} не содержит обязательные semantic aliases шапки: "
                + ", ".join(missing_headers)
            )
        if alias in REQUIRED_ROW_FIELDS:
            if schema.table is None:
                raise ValueError(f"payload_schemas.{alias} не содержит табличную часть")
            missing_rows = sorted(REQUIRED_ROW_FIELDS[alias] - set(schema.table.fields))
            if missing_rows:
                raise ValueError(
                    f"payload_schemas.{alias} не содержит обязательные semantic aliases строки: "
                    + ", ".join(missing_rows)
                )

        if alias == "transfer":
            return self._transfer(item)
        if alias == "sale":
            return self._sale(item)
        if alias == "cash_receipt":
            return self._cash_receipt(item)
        if alias in {"stock_receipt", "stock_writeoff"}:
            return self._adjustment(item, alias)
        raise AssertionError(alias)

    def _constant(self, name: str) -> str:
        return str(
            _required(
                self.mapping.constants.get(name),
                f"В tenant mapping не задан constants.{name}",
            )
        )

    def _base_header(self) -> dict[str, Any]:
        return {"organization_ref": self._constant("organization_ref")}

    @staticmethod
    def _product_ref(line: UnfLine) -> str:
        return str(
            _required(
                line.product_external_1c_id,
                f"Товар {line.sku} не сопоставлен с номенклатурой УНФ",
            )
        )

    @staticmethod
    def _filter_configured(values: dict[str, Any], configured: dict[str, str]) -> dict[str, Any]:
        return {key: value for key, value in values.items() if key in configured}

    def _transfer(self, item: UnfOutboxItem) -> dict[str, Any]:
        schema = self.builder.schema("transfer")
        header = {
            **self._base_header(),
            "date": _required(item.created_at, "У операции отсутствует created_at"),
            "source_location_ref": _required(
                item.source_location_external_1c_id,
                "Не сопоставлен склад-источник УНФ",
            ),
            "destination_location_ref": _required(
                item.destination_location_external_1c_id,
                "Не сопоставлен склад-получатель УНФ",
            ),
            "user_comment": item.comment,
        }
        rows = [
            {"product_ref": self._product_ref(line), "quantity": line.quantity}
            for line in item.lines
        ]
        if not rows:
            raise ValueError("Перемещение не содержит товарных строк")
        return self.builder.build(
            "transfer",
            self._filter_configured(header, schema.header_fields),
            rows,
        )

    def _sale(self, item: UnfOutboxItem) -> dict[str, Any]:
        schema = self.builder.schema("sale")
        if item.sale_price_type not in {"retail", "wholesale"}:
            raise ValueError("У продажи отсутствует сохраненный тип цены retail/wholesale")
        customer_ref = self._constant(f"{item.sale_price_type}_customer_ref")
        header = {
            **self._base_header(),
            "date": _required(item.created_at, "У продажи отсутствует created_at"),
            "warehouse_ref": _required(
                item.source_location_external_1c_id,
                "Не сопоставлен склад продажи УНФ",
            ),
            "customer_ref": customer_ref,
            "user_comment": item.comment,
        }
        rows: list[dict[str, Any]] = []
        for line in item.lines:
            price = _required(line.unit_price, f"У товара {line.sku} нет исторической цены продажи")
            rows.append(
                {
                    "product_ref": self._product_ref(line),
                    "quantity": line.quantity,
                    "unit_price": price,
                }
            )
        if not rows:
            raise ValueError("Продажа не содержит товарных строк")
        return self.builder.build(
            "sale",
            self._filter_configured(header, schema.header_fields),
            rows,
        )

    def _cash_receipt(self, item: UnfOutboxItem) -> dict[str, Any]:
        schema = self.builder.schema("cash_receipt")
        representative_ref = str(
            _required(
                item.representative_external_1c_id,
                "Не сопоставлен представитель для сдачи денег",
            )
        )
        payer_ref = self.mapping.representative_payer_refs.get(representative_ref)
        if not payer_ref:
            raise ValueError(
                f"Для представителя {representative_ref} не задан representative_payer_refs"
            )
        amount = Decimal(str(_required(item.amount, "У сдачи денег отсутствует сумма")))
        if amount <= 0:
            raise ValueError("Сумма поступления в кассу должна быть положительной")
        header = {
            **self._base_header(),
            "date": _required(item.created_at, "У сдачи денег отсутствует created_at"),
            "cashbox_ref": self._constant("cashbox_ref"),
            "cash_flow_item_ref": self._constant("cash_flow_item_ref"),
            "payer_ref": payer_ref,
            "amount": amount,
            "user_comment": item.comment,
        }
        return self.builder.build(
            "cash_receipt",
            self._filter_configured(header, schema.header_fields),
        )

    def _adjustment(self, item: UnfOutboxItem, alias: str) -> dict[str, Any]:
        schema = self.builder.schema(alias)
        header = {
            **self._base_header(),
            "date": _required(item.created_at, "У корректировки отсутствует created_at"),
            "warehouse_ref": _required(
                item.adjustment_location_external_1c_id,
                "Не сопоставлен склад корректировки УНФ",
            ),
            "user_comment": item.comment,
        }
        positive = alias == "stock_receipt"
        rows: list[dict[str, Any]] = []
        for line in item.lines:
            delta = line.quantity_delta
            if delta is None or (delta > 0) != positive:
                continue
            rows.append(
                {
                    "product_ref": self._product_ref(line),
                    "quantity": abs(delta),
                }
            )
        if not rows:
            raise ValueError(f"Корректировка не содержит строк для {alias}")
        return self.builder.build(
            alias,
            self._filter_configured(header, schema.header_fields),
            rows,
        )
