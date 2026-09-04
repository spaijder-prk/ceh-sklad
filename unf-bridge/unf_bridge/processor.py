from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .ceh_client import CehSkladClient
from .fresh_transport import FreshTransport
from .models import UnfOutboxItem, UnfProfile
from .planner import PlannedDocument, build_plan


PayloadFactory = Callable[[UnfOutboxItem, PlannedDocument], dict[str, Any]]


DOCUMENT_ALIASES = {
    "Перемещение запасов": "transfer",
    "Расходная накладная": "sale",
    "Поступление в кассу": "cash_receipt",
    "Оприходование запасов": "stock_receipt",
    "Списание запасов": "stock_writeoff",
}


@dataclass(frozen=True)
class ProcessResult:
    internal_id: str
    document_refs: tuple[str, ...]
    reused_documents: int


def document_alias(document: PlannedDocument) -> str:
    try:
        return DOCUMENT_ALIASES[document.unf_document]
    except KeyError as exc:
        raise ValueError(f"Для документа УНФ не задан transport alias: {document.unf_document}") from exc


class UnfBridgeProcessor:
    """Оркестрирует безопасную доставку одного outbox элемента в УНФ.

    PayloadFactory отвечает только за tenant-specific реквизиты. Все гарантии повторной
    доставки сосредоточены здесь и в FreshTransport: перед create всегда выполняется
    поиск по детерминированному external key, а ceh-sklad подтверждается только после
    получения Ref_Key всех документов.
    """

    def __init__(
        self,
        ceh_client: CehSkladClient,
        transport: FreshTransport,
        payload_factory: PayloadFactory,
    ) -> None:
        self.ceh_client = ceh_client
        self.transport = transport
        self.payload_factory = payload_factory

    def process_item(self, profile: UnfProfile, item: UnfOutboxItem) -> ProcessResult:
        plan = build_plan(item)
        if plan.blocked:
            raise ValueError(
                f"Операция {item.internal_id} не готова к УНФ: " + "; ".join(item.blocking_reasons)
            )

        written: list[tuple[PlannedDocument, str, bool]] = []
        for document in plan.documents:
            alias = document_alias(document)
            payload = self.payload_factory(item, document)
            result = self.transport.ensure_document(alias, document.external_key, payload)
            written.append((document, result.ref_key, result.repeated))

        if len(written) == 1:
            self.ceh_client.confirm_single(profile, item, written[0][1])
        else:
            self.ceh_client.confirm_batch(
                profile,
                item,
                [(ref_key, document.unf_document) for document, ref_key, _ in written],
            )

        return ProcessResult(
            internal_id=item.internal_id,
            document_refs=tuple(ref_key for _, ref_key, _ in written),
            reused_documents=sum(1 for _, _, repeated in written if repeated),
        )

    def process_outbox(self, limit: int = 50) -> list[ProcessResult]:
        profile = self.ceh_client.profile()
        results: list[ProcessResult] = []
        for item in self.ceh_client.outbox(limit):
            results.append(self.process_item(profile, item))
        return results
