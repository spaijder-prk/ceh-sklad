from datetime import UTC, datetime
from decimal import Decimal

from unf_bridge.fresh_transport import DocumentWriteResult
from unf_bridge.fresh_sync import run_sync
from unf_bridge.models import UnfLine, UnfOutboxItem, UnfProfile


class FakeCehClient:
    def __init__(self, items: list[UnfOutboxItem]) -> None:
        self.items = items
        self.confirmed: list[tuple[str, str]] = []

    def profile(self) -> UnfProfile:
        return UnfProfile(
            contract_version="unf-cloud-v2",
            target_configuration="1С:Управление нашей фирмой",
            deployment="cloud",
            confirm_export_path="/confirm",
            confirm_export_batch_path="/confirm-batch",
        )

    def outbox(self, limit: int = 50) -> list[UnfOutboxItem]:
        return self.items[:limit]

    def confirm_single(self, profile, item, external_1c_id: str) -> None:
        self.confirmed.append((item.internal_id, external_1c_id))

    def confirm_batch(self, profile, item, documents) -> None:
        self.confirmed.extend((item.internal_id, external_id) for external_id, _ in documents)


class FakeTransport:
    def __init__(self) -> None:
        self.validated = 0
        self.writes: list[tuple[str, str, dict]] = []

    def validate_configuration(self) -> None:
        self.validated += 1

    def ensure_document(self, alias: str, external_key: str, payload: dict) -> DocumentWriteResult:
        self.writes.append((alias, external_key, payload))
        return DocumentWriteResult(
            ref_key="11111111-1111-1111-1111-111111111111",
            repeated=False,
        )


def ready_item() -> UnfOutboxItem:
    return UnfOutboxItem(
        entity_type="stock_document",
        internal_id="doc-1",
        kind="transfer",
        unf_document="Перемещение запасов",
        unf_operation="Перемещение",
        ready_for_unf=True,
        blocking_reasons=(),
        requires_split=False,
        source_location_external_1c_id="source",
        destination_location_external_1c_id="destination",
        adjustment_location_external_1c_id=None,
        representative_external_1c_id=None,
        amount=None,
        comment=None,
        lines=(
            UnfLine(
                product_external_1c_id="product",
                sku="SKU",
                quantity=Decimal("1"),
                quantity_delta=None,
                unit_price=None,
            ),
        ),
        created_at=datetime(2026, 9, 4, 8, 0, tzinfo=UTC),
    )


def test_dry_run_validates_and_builds_payload_but_never_writes_or_confirms():
    ceh = FakeCehClient([ready_item()])
    transport = FakeTransport()
    payload_calls: list[str] = []

    def payload_factory(item, document):
        payload_calls.append(document.external_key)
        return {"safe": True}

    summary = run_sync(ceh, transport, payload_factory, execute=False)  # type: ignore[arg-type]
    assert transport.validated == 1
    assert len(payload_calls) == 1
    assert transport.writes == []
    assert ceh.confirmed == []
    assert summary.ready_items == 1 and summary.processed_items == 0


def test_execute_uses_retry_safe_processor_and_confirms_only_after_write():
    ceh = FakeCehClient([ready_item()])
    transport = FakeTransport()
    summary = run_sync(
        ceh,
        transport,
        lambda item, document: {"safe": True},
        execute=True,
    )  # type: ignore[arg-type]
    assert len(transport.writes) == 1
    assert ceh.confirmed == [("doc-1", "11111111-1111-1111-1111-111111111111")]
    assert summary.processed_items == 1


def test_blocked_item_is_never_built_or_written():
    blocked = ready_item()
    blocked = UnfOutboxItem(
        **{
            **blocked.__dict__,
            "ready_for_unf": False,
            "blocking_reasons": ("Не сопоставлен склад",),
        }
    )
    ceh = FakeCehClient([blocked])
    transport = FakeTransport()
    calls = 0

    def payload_factory(item, document):
        nonlocal calls
        calls += 1
        return {}

    summary = run_sync(ceh, transport, payload_factory, execute=True)  # type: ignore[arg-type]
    assert calls == 0
    assert transport.writes == [] and ceh.confirmed == []
    assert summary.blocked_items == 1
