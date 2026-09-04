from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .odata import FreshODataClient
from .tenant_config import DOCUMENT_RESOURCES, TenantMapping


@dataclass(frozen=True)
class DocumentWriteResult:
    ref_key: str
    repeated: bool


class FreshTransport:
    """Идемпотентная низкоуровневая запись документов в 1С:Фреш.

    Формирование бизнес-реквизитов документа остаётся отдельным mapping-слоем.
    Transport отвечает только за проверку metadata, поиск по устойчивому ключу,
    create и опциональное проведение.
    """

    def __init__(self, client: FreshODataClient, mapping: TenantMapping) -> None:
        self.client = client
        self.mapping = mapping

    def validate_configuration(self) -> None:
        self.mapping.validate_against_metadata(self.client.entity_sets())

    def find_document(self, alias: str, external_key: str) -> dict[str, Any] | None:
        if alias not in DOCUMENT_RESOURCES:
            raise ValueError(f"Неизвестный тип документа УНФ: {alias}")
        return self.client.find_one_by_text_field(
            self.mapping.resources[alias],
            self.mapping.external_key_fields[alias],
            external_key,
        )

    def ensure_document(
        self,
        alias: str,
        external_key: str,
        payload: dict[str, Any],
    ) -> DocumentWriteResult:
        if alias not in DOCUMENT_RESOURCES:
            raise ValueError(f"Неизвестный тип документа УНФ: {alias}")
        if not external_key:
            raise ValueError("Устойчивый внешний ключ не может быть пустым")

        existing = self.find_document(alias, external_key)
        if existing is not None:
            ref_key = existing.get("Ref_Key")
            if not isinstance(ref_key, str) or not ref_key:
                raise RuntimeError("Найденный документ УНФ не содержит Ref_Key")
            return DocumentWriteResult(ref_key=ref_key, repeated=True)

        resource = self.mapping.resources[alias]
        external_field = self.mapping.external_key_fields[alias]
        body = dict(payload)
        body[external_field] = external_key
        created = self.client.create(resource, body)
        ref_key = created.get("Ref_Key")
        if not isinstance(ref_key, str) or not ref_key:
            raise RuntimeError("Созданный документ УНФ не содержит Ref_Key")

        if self.mapping.post_documents:
            self.client.post_document(resource, ref_key)
        return DocumentWriteResult(ref_key=ref_key, repeated=False)
