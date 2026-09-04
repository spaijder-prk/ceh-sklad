from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .odata import FreshODataClient
from .tenant_config import TenantMapping


@dataclass(frozen=True)
class ProductPrices:
    retail: Decimal | None
    wholesale: Decimal | None


class FreshPriceReader:
    """Читает последние цены двух выбранных видов через SliceLast регистра УНФ."""

    def __init__(self, client: FreshODataClient, mapping: TenantMapping) -> None:
        self.client = client
        self.mapping = mapping

    def _read_price(self, product_ref: str, price_type_ref: str) -> Decimal | None:
        fields = self.mapping.price_fields
        rows = self.client.slice_last_by_guid_fields(
            self.mapping.resources["prices"],
            {
                fields["product_ref"]: product_ref,
                fields["price_type_ref"]: price_type_ref,
            },
            select=(fields["value"],),
        )
        if not rows:
            return None
        if len(rows) > 1:
            raise RuntimeError(
                "SliceLast вернул несколько цен для одной номенклатуры и вида цены; "
                "нужно добавить недостающее измерение tenant mapping"
            )
        raw = rows[0].get(fields["value"])
        if raw is None:
            raise RuntimeError("Строка регистра цен УНФ не содержит настроенное поле цены")
        try:
            value = Decimal(str(raw))
        except (InvalidOperation, ValueError) as exc:
            raise RuntimeError("УНФ вернула некорректное значение цены") from exc
        if value < 0:
            raise RuntimeError("УНФ вернула отрицательную цену")
        return value

    def product_prices(self, product_ref: str) -> ProductPrices:
        return ProductPrices(
            retail=self._read_price(product_ref, self.mapping.constants["retail_price_type_ref"]),
            wholesale=self._read_price(product_ref, self.mapping.constants["wholesale_price_type_ref"]),
        )
