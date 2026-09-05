from unf_bridge.location_import import FreshLocationImporter, LocationImportMapping
from unf_bridge.tenant_config import TenantMapping


WAREHOUSE_REF = "11111111-1111-1111-1111-111111111111"
REP_REF = "22222222-2222-2222-2222-222222222222"
IGNORED_REF = "33333333-3333-3333-3333-333333333333"

BASE = {
    "provider": "1cfresh",
    "application_url": "https://1cfresh.example/a/unf/100",
    "timezone": "Europe/Moscow",
    "post_documents": False,
    "resources": {
        "products": "Catalog_Номенклатура",
        "price_types": "Catalog_ВидыЦен",
        "prices": "InformationRegister_Цены",
        "warehouses": "Catalog_Склады",
        "organizations": "Catalog_Организации",
        "counterparties": "Catalog_Контрагенты",
        "transfer": "Document_Перемещение",
        "sale": "Document_Продажа",
        "cash_receipt": "Document_Касса",
        "stock_receipt": "Document_Оприходование",
        "stock_writeoff": "Document_Списание",
    },
    "external_key_fields": {
        "transfer": "Комментарий",
        "sale": "Комментарий",
        "cash_receipt": "Комментарий",
        "stock_receipt": "Комментарий",
        "stock_writeoff": "Комментарий",
    },
    "price_fields": {"product_ref": "Номенклатура_Key", "price_type_ref": "ВидЦен_Key", "value": "Цена"},
    "constants": {
        "retail_price_type_ref": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "wholesale_price_type_ref": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    },
    "location_fields": {"ref": "Ref_Key", "name": "Description"},
    "location_allowlist": {
        WAREHOUSE_REF: {"kind": "warehouse"},
        REP_REF: {"kind": "representative", "name_override": "Склад представителя Иван"},
    },
}


class FakeFresh:
    rows = {
        WAREHOUSE_REF: {"Ref_Key": WAREHOUSE_REF, "Description": "Центральный склад"},
        REP_REF: {"Ref_Key": REP_REF, "Description": "Внешнее имя представителя"},
        IGNORED_REF: {"Ref_Key": IGNORED_REF, "Description": "Служебный склад"},
    }

    def list(self, resource, *, top=50, select=(), filter_expression=None):
        assert resource == "Catalog_Склады"
        ref = filter_expression.split("guid'", 1)[1].split("'", 1)[0]
        row = self.rows.get(ref)
        return [row] if row else []


class FakeCeh:
    def __init__(self):
        self.payloads = []

    def import_location(self, payload):
        self.payloads.append(dict(payload))
        return {"internal_id": f"id-{len(self.payloads)}", "repeated": False}


def service(config=BASE):
    ceh = FakeCeh()
    return FreshLocationImporter(
        FakeFresh(),  # type: ignore[arg-type]
        ceh,  # type: ignore[arg-type]
        TenantMapping.from_dict(config),
        LocationImportMapping.from_dict(config),
    ), ceh


def test_only_allowlisted_locations_are_planned_and_kind_is_explicit():
    importer, _ = service()
    plans = importer.plans()
    assert {plan.external_ref for plan in plans} == {WAREHOUSE_REF, REP_REF}
    assert IGNORED_REF not in {plan.external_ref for plan in plans}
    by_ref = {plan.external_ref: plan for plan in plans}
    assert by_ref[WAREHOUSE_REF].name == "Центральный склад"
    assert by_ref[WAREHOUSE_REF].kind == "warehouse"
    assert by_ref[REP_REF].name == "Склад представителя Иван"
    assert by_ref[REP_REF].kind == "representative"


def test_dry_run_never_writes_and_execute_sends_only_allowlist():
    importer, ceh = service()
    dry = importer.sync(execute=False)
    assert dry.ready == 2 and ceh.payloads == []
    executed = importer.sync(execute=True)
    assert executed.imported == 2
    assert {row["external_1c_id"] for row in ceh.payloads} == {WAREHOUSE_REF, REP_REF}


def test_missing_allowlisted_location_is_blocked():
    missing_ref = "44444444-4444-4444-4444-444444444444"
    config = {**BASE, "location_allowlist": {missing_ref: {"kind": "warehouse"}}}
    importer, ceh = service(config)
    summary = importer.sync(execute=True)
    assert summary.blocked == 1 and ceh.payloads == []
    assert "не найден" in summary.messages[0]


def test_empty_allowlist_is_rejected():
    config = {**BASE, "location_allowlist": {}}
    try:
        LocationImportMapping.from_dict(config)
    except ValueError as exc:
        assert "allow-list" in str(exc)
    else:
        raise AssertionError("Пустой allow-list должен быть запрещен")
