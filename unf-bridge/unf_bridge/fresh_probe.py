from __future__ import annotations

import argparse
import os
from pathlib import Path

from .odata import FreshODataClient, ODataEntitySet
from .tenant_config import TenantMapping


DEFAULT_HINTS = (
    "Номенклат",
    "ВидЦен",
    "Цен",
    "Склад",
    "Перемещ",
    "Расход",
    "Касс",
    "Оприход",
    "Списан",
    "Организац",
    "Контрагент",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only probe стандартного OData интерфейса 1С:Фреш"
    )
    parser.add_argument(
        "--url",
        default=os.getenv("UNF_FRESH_URL"),
        help="URL приложения 1С:Фреш, например https://1cfresh.com/a/.../...",
    )
    parser.add_argument(
        "--mapping",
        type=Path,
        help="Несекретный JSON mapping; при наличии будет сверён с $metadata tenant",
    )
    parser.add_argument(
        "--contains",
        action="append",
        default=[],
        help="Показать EntitySet, имя которых содержит строку; можно указывать несколько раз",
    )
    parser.add_argument("--all", action="store_true", help="Показать все EntitySet")
    parser.add_argument(
        "--details",
        action="store_true",
        help="Показать поля, EDM-типы, nullable и связанные EntitySet/табличные части",
    )
    parser.add_argument(
        "--allow-http",
        action="store_true",
        help="Разрешить HTTP только для локального тестового стенда",
    )
    return parser.parse_args()


def related_entity_sets(item: ODataEntitySet, entity_sets: list[ODataEntitySet]) -> list[ODataEntitySet]:
    prefix = f"{item.name}_"
    return [candidate for candidate in entity_sets if candidate.name.startswith(prefix)]


def entity_details_lines(item: ODataEntitySet, entity_sets: list[ODataEntitySet]) -> list[str]:
    lines: list[str] = []
    if item.fields:
        lines.append("  Поля:")
        for field in item.fields:
            marker = "nullable" if field.nullable else "required"
            lines.append(f"    {field.name}: {field.edm_type} [{marker}]")
    elif item.properties:
        lines.append("  Поля: " + ", ".join(item.properties))

    if item.navigation:
        lines.append("  NavigationProperty:")
        for navigation in item.navigation:
            lines.append(f"    {navigation.name}: {navigation.target_type}")

    related = related_entity_sets(item, entity_sets)
    if related:
        lines.append("  Связанные EntitySet / возможные табличные части:")
        for candidate in related:
            lines.append(f"    {candidate.name} -> {candidate.entity_type}")
            for field in candidate.fields:
                marker = "nullable" if field.nullable else "required"
                lines.append(f"      {field.name}: {field.edm_type} [{marker}]")
    return lines


def main() -> None:
    args = parse_args()
    username = os.getenv("UNF_FRESH_LOGIN")
    password = os.getenv("UNF_FRESH_PASSWORD")
    if not args.url:
        raise SystemExit("Не задан --url или UNF_FRESH_URL")
    if not username or not password:
        raise SystemExit("Задайте UNF_FRESH_LOGIN и UNF_FRESH_PASSWORD через secret storage")

    mapping = TenantMapping.load(args.mapping) if args.mapping else None
    if mapping and mapping.application_url.rstrip("/") != args.url.rstrip("/"):
        raise SystemExit("application_url в mapping не совпадает с URL probe")

    with FreshODataClient(
        args.url,
        username,
        password,
        allow_http=args.allow_http,
    ) as client:
        entity_sets = client.entity_sets()

    if mapping:
        mapping.validate_against_metadata(entity_sets)
        print(f"Mapping проверен: {args.mapping}")

    filters = tuple(args.contains) if args.contains else DEFAULT_HINTS
    if args.all:
        selected = entity_sets
    else:
        selected = [
            item
            for item in entity_sets
            if any(fragment.casefold() in item.name.casefold() for fragment in filters)
        ]

    print(f"OData доступен: {len(entity_sets)} EntitySet опубликовано")
    print(f"OData base: {args.url.rstrip('/')}/odata/standard.odata")
    print("Сервисные учетные данные в вывод не включаются.")
    if not selected:
        print("Подходящие EntitySet по фильтру не найдены. Используйте --all для полного списка.")
        return
    for item in selected:
        print(f"{item.name} -> {item.entity_type}")
        if args.details:
            for line in entity_details_lines(item, entity_sets):
                print(line)


if __name__ == "__main__":
    main()
