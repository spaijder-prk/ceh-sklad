from decimal import Decimal

import pytest

from unf_bridge.models import UnfLine, UnfOutboxItem
from unf_bridge.planner import build_plan, stable_external_key


def item(*, ready: bool = True, split: bool = False) -> UnfOutboxItem:
    return UnfOutboxItem(
        entity_type="stock_document",
        internal_id="11111111-1111-1111-1111-111111111111",
        kind="adjustment" if split else "sale",
        unf_document="Оприходование запасов + Списание запасов" if split else "Расходная накладная",
        unf_operation="Тестовая операция",
        ready_for_unf=ready,
        blocking_reasons=() if ready else ("Не сопоставлен склад",),
        requires_split=split,
        source_location_external_1c_id="warehouse-1",
        destination_location_external_1c_id=None,
        adjustment_location_external_1c_id="warehouse-1" if split else None,
        representative_external_1c_id=None,
        amount=None,
        comment=None,
        lines=(
            UnfLine(
                product_external_1c_id="product-plus",
                sku="PLUS",
                quantity=Decimal("2"),
                quantity_delta=Decimal("2") if split else None,
                unit_price=Decimal("100") if not split else None,
            ),
            *(
                (
                    UnfLine(
                        product_external_1c_id="product-minus",
                        sku="MINUS",
                        quantity=Decimal("1"),
                        quantity_delta=Decimal("-1"),
                        unit_price=None,
                    ),
                )
                if split
                else ()
            ),
        ),
    )


def test_single_document_plan_uses_stable_key():
    source = item()
    plan = build_plan(source)
    assert plan.blocked is False
    assert len(plan.documents) == 1
    assert plan.documents[0].external_key == stable_external_key(source)
    assert plan.documents[0].unf_document == "Расходная накладная"
    assert plan.documents[0].line_skus == ("PLUS",)


def test_mixed_adjustment_splits_into_two_stable_documents():
    source = item(split=True)
    plan = build_plan(source)
    assert plan.blocked is False
    assert [document.unf_document for document in plan.documents] == [
        "Оприходование запасов",
        "Списание запасов",
    ]
    assert [document.external_key for document in plan.documents] == [
        stable_external_key(source, "receipt"),
        stable_external_key(source, "writeoff"),
    ]
    assert plan.documents[0].line_skus == ("PLUS",)
    assert plan.documents[1].line_skus == ("MINUS",)


def test_blocked_item_does_not_produce_documents():
    plan = build_plan(item(ready=False))
    assert plan.blocked is True
    assert plan.documents == ()


def test_invalid_split_without_both_delta_groups_is_rejected():
    source = item(split=True)
    broken = UnfOutboxItem(
        **{
            **source.__dict__,
            "lines": (source.lines[0],),
        }
    )
    with pytest.raises(ValueError, match="обеих групп"):
        build_plan(broken)
