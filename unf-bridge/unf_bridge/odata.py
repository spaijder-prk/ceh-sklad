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
class ODataField:
    name: str
    edm_type: str
    nullable: bool = True


@dataclass(frozen=True)
class ODataNavigation:
    name: str
    target_type: str


@dataclass(frozen=True)
class ODataEntitySet:
    name: str
    entity_type: str
    properties: tuple[str, ...] = ()
    fields: tuple[ODataField, ...] = ()
    navigation: tuple[ODataNavigation, ...] = ()


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _validate_resource(value: str) -> str:
    if not value or not _RESOURCE_RE.fullmatch(value):
        raise ValueError("Некорректное имя OData-ресурса")
    return value


def validate_field_path(value: str) -> str:
    """Разрешает только безопасный путь из OData-идентификаторов `segment/segment`."""
    parts = value.split("/")
    if not value or not parts or any(not part or not _RESOURCE_RE.fullmatch(part) for part in parts):
        raise ValueError("Некорректный путь OData-поля")
    return value


def _validate_guid(value: str) -> str:
    if not _GUID_RE.fullmatch(value):
        raise ValueError("Некорректный Ref_Key OData")
    return value.lower()


def _odata_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


class FreshODataClient:
    """Низкоуровневый клиент стандартного OData интерфейса 1С:Фреш."""

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
        fields_by_type: dict[str, tuple[ODataField, ...]] = {}
        navigation_by_type: dict[str, tuple[ODataNavigation, ...]] = {}

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
                fields = tuple(
                    ODataField(
                        name=child.attrib["Name"],
                        edm_type=child.attrib.get("Type", "unknown"),
                        nullable=child.attrib.get("Nullable", "true").lower() != "false",
                    )
                    for child in entity_type
                    if _local_name(child.tag) == "Property" and child.attrib.get("Name")
                )
                navigation = tuple(
                    ODataNavigation(
                        name=child.attrib["Name"],
                        target_type=child.attrib.get("Type", "unknown"),
                    )
                    for child in entity_type
                    if _local_name(child.tag) == "NavigationProperty" and child.attrib.get("Name")
                )
                aliases = (type_name, f"{namespace}.{type_name}") if namespace else (type_name,)
                for alias in aliases:
                    fields_by_type[alias] = fields
                    navigation_by_type[alias] = navigation

        result: list[ODataEntitySet] = []
        for element in root.iter():
            if _local_name(element.tag) != "EntitySet":
                continue
            name = element.attrib.get("Name")
            entity_type = element.attrib.get("EntityType")
            if name and entity_type:
                fields = fields_by_type.get(entity_type, ())
                result.append(
                    ODataEntitySet(
                        name=name,
                        entity_type=entity_type,
                        properties=tuple(field.name for field in fields),
                        fields=fields,
                        navigation=navigation_by_type.get(entity_type, ()),
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
                validate_field_path(field)
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

    def slice_last_by_guid_fields(
        self,
        resource: str,
        filters: dict[str, str],
        *,
        select: tuple[str, ...] = (),
    ) -> list[dict[str, Any]]:
        """Читает SliceLast периодического регистра с безопасными GUID-условиями."""
        resource = _validate_resource(resource)
        if not filters:
            raise ValueError("SliceLast требует хотя бы одно измерение")
        conditions: list[str] = []
        for field, value in filters.items():
            field = validate_field_path(field)
            guid = _validate_guid(value)
            conditions.append(f"{field} eq guid'{guid}'")
        params: dict[str, str] = {
            "$format": "json",
            "Condition": " and ".join(conditions),
        }
        if select:
            for field in select:
                validate_field_path(field)
            params["$select"] = ",".join(select)
        response = self._client.get(f"{resource}/SliceLast", params=params)
        response.raise_for_status()
        body = response.json()
        value = body.get("value")
        if not isinstance(value, list):
            raise RuntimeError("OData SliceLast вернул неожиданный формат")
        return [dict(row) for row in value]

    def find_one_by_guid(self, resource: str, ref_key: str) -> dict[str, Any] | None:
        """Безопасно проверяет существование объекта каталога по стандартному Ref_Key."""
        resource = _validate_resource(resource)
        guid = _validate_guid(ref_key)
        rows = self.list(
            resource,
            top=2,
            select=("Ref_Key",),
            filter_expression=f"Ref_Key eq guid'{guid}'",
        )
        if len(rows) > 1:
            raise RuntimeError(f"По Ref_Key {guid} найдено несколько объектов в {resource}")
        return rows[0] if rows else None

    def find_one_by_text_field(
        self,
        resource: str,
        field: str,
        value: str,
    ) -> dict[str, Any] | None:
        resource = _validate_resource(resource)
        field = _validate_resource(field)
        if not value:
            raise ValueError("Устойчивый внешний ключ не может быть пустым")
        rows = self.list(
            resource,
            top=2,
            filter_expression=f"{field} eq {_odata_string(value)}",
        )
        if len(rows) > 1:
            raise RuntimeError(
                f"Нарушена идемпотентность УНФ: по {resource}.{field} найдено несколько объектов"
            )
        return rows[0] if rows else None

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
