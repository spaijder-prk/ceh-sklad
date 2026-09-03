from __future__ import annotations

import argparse
import os
import sys

from .ceh_client import CehSkladClient
from .planner import build_plan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dry-run bridge между ceh-sklad и облачной 1С:УНФ"
    )
    parser.add_argument(
        "--ceh-url",
        default=os.getenv("CEH_API_URL"),
        help="HTTPS origin ceh-sklad, например https://sklad.example.ru",
    )
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument(
        "--allow-http",
        action="store_true",
        help="Разрешить HTTP только для локальной разработки",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    integration_key = os.getenv("CEH_1C_KEY")
    if not args.ceh_url:
        raise SystemExit("Не задан --ceh-url или CEH_API_URL")
    if not integration_key:
        raise SystemExit("Не задан CEH_1C_KEY")

    ready = 0
    blocked = 0
    planned_documents = 0
    with CehSkladClient(
        args.ceh_url,
        integration_key,
        allow_http=args.allow_http,
    ) as client:
        profile = client.profile()
        print(
            f"Контракт: {profile.contract_version}; "
            f"цель: {profile.target_configuration}; deployment={profile.deployment}"
        )
        items = client.outbox(args.limit)
        for item in items:
            plan = build_plan(item)
            if plan.blocked:
                blocked += 1
                print(
                    f"BLOCKED {item.kind} {item.internal_id}: "
                    + "; ".join(item.blocking_reasons)
                )
                continue

            ready += 1
            planned_documents += len(plan.documents)
            for document in plan.documents:
                products = ", ".join(document.line_skus) or "без товарных строк"
                print(
                    f"PLAN {item.kind} {item.internal_id} -> {document.unf_document}; "
                    f"external_key={document.external_key}; товары={products}"
                )

    print(
        f"Dry-run завершен: outbox={ready + blocked}, готовы={ready}, "
        f"blocked={blocked}, документов УНФ по плану={planned_documents}"
    )
    print("Записи в УНФ и confirm-export НЕ выполнялись.")
    if blocked:
        sys.exit(3)


if __name__ == "__main__":
    main()
