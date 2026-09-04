from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from .ceh_client import CehSkladClient
from .fresh_transport import FreshTransport
from .odata import FreshODataClient
from .operation_payloads import UnfOperationPayloadFactory
from .planner import build_plan
from .processor import PayloadFactory, UnfBridgeProcessor
from .tenant_config import TenantMapping


@dataclass(frozen=True)
class SyncSummary:
    outbox_items: int
    ready_items: int
    blocked_items: int
    planned_documents: int
    processed_items: int
    reused_documents: int
    messages: tuple[str, ...]


def run_sync(
    ceh_client: CehSkladClient,
    transport: FreshTransport,
    payload_factory: PayloadFactory,
    *,
    limit: int = 50,
    execute: bool = False,
) -> SyncSummary:
    """Валидирует контур и либо планирует, либо доставляет текущий outbox."""
    profile = ceh_client.profile()
    transport.validate_configuration(require_schema_lock=execute)
    processor = UnfBridgeProcessor(ceh_client, transport, payload_factory)

    ready = 0
    blocked = 0
    planned_documents = 0
    processed = 0
    reused = 0
    messages: list[str] = []
    items = ceh_client.outbox(limit)

    for item in items:
        plan = build_plan(item)
        if plan.blocked:
            blocked += 1
            messages.append(
                f"BLOCKED {item.kind} {item.internal_id}: "
                + "; ".join(item.blocking_reasons)
            )
            continue

        # Даже в dry-run строим все payload: так ошибки semantic mapping выявляются
        # до включения режима записи.
        for document in plan.documents:
            payload_factory(item, document)
            messages.append(
                f"PLAN {item.kind} {item.internal_id} -> {document.unf_document}; "
                f"external_key={document.external_key}"
            )
        ready += 1
        planned_documents += len(plan.documents)

        if not execute:
            continue

        result = processor.process_item(profile, item)
        processed += 1
        reused += result.reused_documents
        messages.append(
            f"SENT {item.kind} {item.internal_id}: refs={','.join(result.document_refs)}; "
            f"reused={result.reused_documents}"
        )

    return SyncSummary(
        outbox_items=len(items),
        ready_items=ready,
        blocked_items=blocked,
        planned_documents=planned_documents,
        processed_items=processed,
        reused_documents=reused,
        messages=tuple(messages),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Безопасная синхронизация outbox ceh-sklad с 1С:УНФ через OData 1С:Фреш"
    )
    parser.add_argument(
        "--mapping",
        required=True,
        type=Path,
        help="Несекретный tenant mapping JSON, заполненный по $metadata",
    )
    parser.add_argument(
        "--ceh-url",
        default=os.getenv("CEH_API_URL"),
        help="HTTPS origin ceh-sklad",
    )
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument(
        "--execute",
        action="store_true",
        help=(
            "Разрешить создание документов УНФ и confirm-export; требует принятого "
            "expected_metadata_structure_sha256. Без флага выполняется только dry-run"
        ),
    )
    parser.add_argument(
        "--allow-http-ceh",
        action="store_true",
        help="Разрешить HTTP для ceh-sklad только на локальном тестовом стенде",
    )
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
    if mapping.provider != "1cfresh":
        raise SystemExit("Команда ceh-unf-fresh-sync предназначена только для provider=1cfresh")

    with CehSkladClient(
        args.ceh_url,
        ceh_key,
        allow_http=args.allow_http_ceh,
    ) as ceh_client, FreshODataClient(
        mapping.application_url,
        fresh_login,
        fresh_password,
    ) as fresh_client:
        transport = FreshTransport(fresh_client, mapping)
        payload_factory = UnfOperationPayloadFactory(mapping)
        summary = run_sync(
            ceh_client,
            transport,
            payload_factory,
            limit=max(1, min(args.limit, 100)),
            execute=args.execute,
        )

    for message in summary.messages:
        print(message)
    mode = "EXECUTE" if args.execute else "DRY-RUN"
    print(
        f"{mode}: outbox={summary.outbox_items}, готовы={summary.ready_items}, "
        f"blocked={summary.blocked_items}, документов={summary.planned_documents}, "
        f"отправлено={summary.processed_items}, повторно найдено={summary.reused_documents}"
    )
    if not args.execute:
        print("Записи в УНФ и confirm-export НЕ выполнялись. Для записи нужен явный --execute.")
    elif not mapping.post_documents:
        print("Внимание: post_documents=false — документы создаются в УНФ без проведения.")

    if summary.blocked_items:
        sys.exit(3)


if __name__ == "__main__":
    main()
