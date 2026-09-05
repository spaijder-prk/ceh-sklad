from __future__ import annotations

from decimal import Decimal

import pytest

from unf_bridge.fresh_transport import DocumentWriteResult
from unf_bridge.models import UnfLine, UnfOutboxItem, UnfProfile
from unf_bridge.processor import UnfBridgeProcessor


PROFILE = UnfProfile(
    contract_version="unf-cloud-v2",
    target_configuration="1С:Управление нашей фирмой",
    deployment="cloud",
    confirm_export_path="/api/v1/integration/1c/confirm-export",
    confirm_export_batch_path="/api/v1/integration/1c/confirm-export-batch",
)


def item(*, split: bool = False) -> UnfOutboxItem:
    return UnfOutboxItem(
        entity_type="stock_document",
        internal_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        kind="adjustment" if split else "sale",
        unf_document=("Оприходование запасов + Списание запасов" if split else "Расходная накладная"),
        unf_operation="test",
        ready_for_unf=True,
        blocking_reasons=(),
        requires_split=split,
        source_location_external_1c_id="warehouse",
        destination_location_external_1c_id=None,
        adjustment_location_external_1c_id="warehouse" if split else None,
        representative_external_1c_id=None,
        amount=None,
        comment=None,
        lines=(
            UnfLine(
                product_external_1c_id="p1",
                sku="P1",
                quantity=Decimal("2"),
                quantity_delta=Decimal("2") if split else None,
                unit_price=Decimal("100") if not split else None,
            ),
            *(
                (
                    UnfLine(
                        product_external_1c_id="p2",
                        sku="P2",
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


class FakeCehClient:
    def __init__(self) -> None:
        self.single: list[str] = []
        self.batch: list[list[tuple[str, str]]] = []
        self.fail_confirm_once = False

    def confirm_single(self, profile, current_item, external_id: str) -> None:
        if self.fail_confirm_once:
            self.fail_confirm_once = False
            raise ConnectionError("обрыв после записи УНФ")
        self.single.append(external_id)

    def confirm_batch(self, profile, current_item, documents: list[tuple[str, str]]) -> None:
        self.batch.append(documents)


class RememberingTransport:
    def __init__(self) -> None:
        self.refs: dict[str, str] = {}
        self.create_count = 0

    def ensure_document(self, alias: str, external_key: str, payload: dict) -> DocumentWriteResult:
        existing = self.refs.get(external_key)
        if existing:
            return DocumentWriteResult(ref_key=existing, repeated=True)
        self.create_count += 1
        ref = f"00000000-0000-0000-0000-{self.create_count:012d}"
        self.refs[external_key] = ref
        return DocumentWriteResult(ref_key=ref, repeated=False)


def payload_factory(current_item, document):
    return {"Description": document.operation}


def test_processor_confirms_single_document():
    ceh = FakeCehClient()
    transport = RememberingTransport()
    processor = UnfBridgeProcessor(ceh, transport, payload_factory)  # type: ignore[arg-type]

    result = processor.process_item(PROFILE, item())

    assert transport.create_count == 1
    assert result.reused_documents == 0
    assert ceh.single == ["00000000-0000-0000-0000-000000000001"]
    assert ceh.batch == []


def test_processor_confirms_split_adjustment_as_batch():
    ceh = FakeCehClient()
    transport = RememberingTransport()
    processor = UnfBridgeProcessor(ceh, transport, payload_factory)  # type: ignore[arg-type]

    result = processor.process_item(PROFILE, item(split=True))

    assert transport.create_count == 2
    assert len(result.document_refs) == 2
    assert ceh.single == []
    assert ceh.batch == [[
        ("00000000-0000-0000-0000-000000000001", "Оприходование запасов"),
        ("00000000-0000-0000-0000-000000000002", "Списание запасов"),
    ]]


def test_retry_after_network_break_reuses_document_instead_of_creating_duplicate():
    ceh = FakeCehClient()
    ceh.fail_confirm_once = True
    transport = RememberingTransport()
    processor = UnfBridgeProcessor(ceh, transport, payload_factory)  # type: ignore[arg-type]
    current = item()

    with pytest.raises(ConnectionError, match="обрыв"):
        processor.process_item(PROFILE, current)

    assert transport.create_count == 1
    result = processor.process_item(PROFILE, current)

    assert transport.create_count == 1
    assert result.reused_documents == 1
    assert ceh.single == ["00000000-0000-0000-0000-000000000001"]
