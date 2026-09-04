from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse
from xml.etree import ElementTree

import httpx


_RESOURCE_RE = re.compile(r"^[A-Za-zА-Яа-яЁё0-9_]+$")
_GUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


@dataclass(frozen=True)
class ODataEntitySet:
    name: str
    entity_type: str
    properties: tuple[str, ...] = ()


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _validate_resource(value: str) -> str:
    if not value or not _RESOURCE_RE.fullmatch(value):
        raise ValueError("Некорректное имя OData-ресурса")
    return value


def _validate_guid(value: str) -> str:
    if not _GUID_RE.fullmatch(value):
        raise ValueError("Некорректный Ref_Key OData")
    return value.lower()


class FreshODataClient:
    """Низкоуровневый клиент стандартного OData интерфейса 1С:Фреш.

    Клиент намеренно не знает имена объектов конкретной версии УНФ. Сначала bridge
    читает `$metadata`, затем tenant-конфигурация сопоставляет найденные EntitySet и
    их свойства с нужными документами и справочниками.
    """

    def __init__(
        self,
        application_url: str,
        username: str,
        password: str,
        *,
        timeout: float = 20.0,
        allow_http: bool = False,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        normalized = application_url.rstrip("/")
        parsed = urlparse(normalized)
        allowed_schemes = {"http", "https"} if allow_http else {"https"}
        if not parsed.netloc or parsed.scheme not in allowed_schemes:
            raise ValueError("URL приложения 1С должен быть полноценным HTTPS URL")
        if not username or not password:
            raise ValueError("Для OData 1С требуются отдельные сервисные учетные данные")

        self.application_url = normalized
        self.odata_url = f"{normalized}/odata/standard.odata"
        self._client = httpx.Client(
            base_url=f"{self.odata_url}/",
            auth=(username, password),
            timeout=timeout,
            follow_redirects=False,
            transport=transport,
            headers={"Accept": "application/json"},
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "FreshODataClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def metadata(self) -> str:
        response = self._client.get("$metadata", headers={"Accept": "application/xml"})
        response.raise_for_status()
        return response.text

    def entity_sets(self) -> list[ODataEntitySet]:
        raw = self.metadata()
        root = ElementTree.fromstring(raw)
        properties_by_type: dict[str, tuple[str, ...]] = {}

        for schema in root.iter():
            if _local_name(schema.tag) != "Schema":
                continue
            namespace = schema.attrib.get("Namespace", "")
            for entity_type in schema:
                if _local_name(entity_type.tag) != "EntityType":
                    continue
                type_name = entity_type.attrib.get("Name")
                if not type_name:
                    continue
                properties = tuple(
                    child.attrib["Name"]
                    for child in entity_type
                    if _local_name(child.tag) == "Property" and child.attrib.get("Name")
                )
                properties_by_type[type_name] = properties
                if namespace:
                    properties_by_type[f"{namespace}.{type_name}"] = properties

        result: list[ODataEntitySet] = []
        for element in root.iter():
            if _local_name(element.tag) != "EntitySet":
                continue
            name = element.attrib.get("Name")
            entity_type = element.attrib.get("EntityType")
            if name and entity_type:
                result.append(
                    ODataEntitySet(
                        name=name,
                        entity_type=entity_type,
                        properties=properties_by_type.get(entity_type, ()),
                    )
                )
        return sorted(result, key=lambda item: item.name.casefold())

    def list(
        self,
        resource: str,
        *,
        top: int = 50,
        select: tuple[str, ...] = (),
        filter_expression: str | None = None,
    ) -> list[dict[str, Any]]:
        resource = _validate_resource(resource)
        params: dict[str, str | int] = {"$format": "json", "$top": max(1, min(top, 100))}
        if select:
            for field in select:
                _validate_resource(field)
            params["$select"] = ",".join(select)
        if filter_expression:
            params["$filter"] = filter_expression
        response = self._client.get(resource, params=params)
        response.raise_for_status()
        body = response.json()
        value = body.get("value")
        if not isinstance(value, list):
            raise RuntimeError("OData вернул неожиданный формат списка")
        return [dict(row) for row in value]

    def create(self, resource: str, payload: dict[str, Any]) -> dict[str, Any]:
        resource = _validate_resource(resource)
        response = self._client.post(resource, params={"$format": "json"}, json=payload)
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise RuntimeError("OData вернул неожиданный ответ при создании объекта")
        return dict(body)

    def post_document(self, resource: str, ref_key: str) -> None:
        resource = _validate_resource(resource)
        ref_key = _validate_guid(ref_key)
        response = self._client.post(f"{resource}(guid'{ref_key}')/Post()")
        response.raise_for_status()
