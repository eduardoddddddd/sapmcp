from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from sapmcp import resources


class FakeSDK:
    def RfcGetVersion(self, major, minor, patch):
        major._obj.value = 7
        minor._obj.value = 50
        patch._obj.value = 12
        return 0


class FakeSDKConnector:
    def __init__(self, calls: list[str]):
        self.calls = calls
        self.sap_lib = FakeSDK()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def call_function(self, function_name, **kwargs):
        name = function_name.upper()
        self.calls.append(name)
        if name == "STFC_CONNECTION":
            req = kwargs.get("import_params", {}).get("REQUTEXT", "")
            return {"ECHOTEXT": req, "RESPTEXT": "SAP is reachable"}
        if name == "RFC_GET_FUNCTION_INTERFACE":
            func = kwargs.get("import_params", {}).get("FUNCNAME", "")
            return {
                "PARAMS": [
                    {
                        "PARAMETER": "USERNAME",
                        "PARAMCLASS": "I",
                        "TABNAME": "",
                        "FIELDNAME": "",
                        "EXID": "C",
                        "POSITION": "1",
                        "OFFSET": "0",
                        "INTLENGTH": "12",
                        "DECIMALS": "0",
                        "DEFAULT": "",
                        "PARAMTEXT": f"Input for {func}",
                        "OPTIONAL": "",
                    }
                ],
                "EXCEPTION_LIST": [],
            }
        if name == "DDIF_FIELDINFO_GET":
            return {
                "DFIES_TAB": [
                    {
                        "FIELDNAME": "MANDT",
                        "POSITION": "1",
                        "KEYFLAG": "X",
                        "INTTYPE": "C",
                        "DATATYPE": "CLNT",
                        "LENG": "3",
                        "INTLEN": "6",
                        "DECIMALS": "0",
                        "FIELDTEXT": "Client",
                        "ROLLNAME": "MANDT",
                    },
                    {
                        "FIELDNAME": "BELNR",
                        "POSITION": "2",
                        "KEYFLAG": "X",
                        "INTTYPE": "C",
                        "DATATYPE": "CHAR",
                        "LENG": "10",
                        "INTLEN": "20",
                        "DECIMALS": "0",
                        "FIELDTEXT": "Document Number",
                        "ROLLNAME": "BELNR_D",
                    },
                ]
            }
        if name == "RFC_READ_TABLE":
            return {
                "FIELDS": [{"FIELDNAME": "FUNCNAME"}, {"FIELDNAME": "FMODE"}],
                "DATA": [{"WA": "BAPI_USER_GET_DETAIL\tR"}],
            }
        raise AssertionError(f"Unexpected RFC call: {name}")


@pytest.fixture(autouse=True)
def clean_cache_and_env(monkeypatch):
    resources.invalidate_cache()
    monkeypatch.setenv("SAP_ASHOST", "sap.example.local")
    monkeypatch.setenv("SAP_SYSNR", "00")
    monkeypatch.setenv("SAP_CLIENT", "100")
    monkeypatch.setenv("SAP_USER", "RFC_USER")
    monkeypatch.setenv("SAP_PASS", "top-secret")
    monkeypatch.setenv("SAP_NWRFC_LIB_PATH", "/secret/sdk/libsapnwrfc.dylib")
    monkeypatch.delenv("SAPMCP_ALLOWED_RFC", raising=False)
    monkeypatch.delenv("SAPMCP_DESTINATIONS", raising=False)
    monkeypatch.delenv("SAPMCP_DEFAULT_DESTINATION", raising=False)
    monkeypatch.setenv("SAPMCP_READ_ONLY", "true")
    yield
    resources.invalidate_cache()


def test_function_interface_resource_uses_ttl_and_manual_invalidation(monkeypatch):
    calls: list[str] = []
    now = {"value": 100.0}
    monkeypatch.setattr(resources, "_connector", lambda destination=None: FakeSDKConnector(calls))
    monkeypatch.setattr(resources.time, "monotonic", lambda: now["value"])

    first = resources.get_function_interface("bapi_user_get_detail")
    second = resources.get_function_interface("BAPI_USER_GET_DETAIL")
    assert first == second
    assert calls == ["RFC_GET_FUNCTION_INTERFACE"]

    now["value"] = 701.0
    resources.get_function_interface("BAPI_USER_GET_DETAIL")
    assert calls == ["RFC_GET_FUNCTION_INTERFACE", "RFC_GET_FUNCTION_INTERFACE"]

    removed = resources.invalidate_cache("function/BAPI_USER_GET_DETAIL")
    assert removed == 1
    resources.get_function_interface("BAPI_USER_GET_DETAIL")
    assert calls == ["RFC_GET_FUNCTION_INTERFACE", "RFC_GET_FUNCTION_INTERFACE", "RFC_GET_FUNCTION_INTERFACE"]


def test_cache_get_or_load_deduplicates_concurrent_misses():
    workers = 8
    calls = 0
    calls_lock = threading.Lock()
    start = threading.Barrier(workers)

    def load_once():
        nonlocal calls
        with calls_lock:
            calls += 1
        time.sleep(0.05)
        return {"items": []}

    def read_cached():
        start.wait(timeout=2)
        return resources._cache_get_or_load("race-demo", 60, load_once)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(lambda _: read_cached(), range(workers)))

    assert calls == 1
    assert results == [{"items": []}] * workers

    results[0]["items"].append("mutated")
    assert resources._cache_get_or_load("race-demo", 60, load_once) == {"items": []}


def test_cache_get_or_load_shares_loader_exception_and_allows_retry():
    workers = 4
    calls = 0
    calls_lock = threading.Lock()
    start = threading.Barrier(workers)

    def failing_load():
        nonlocal calls
        with calls_lock:
            calls += 1
        time.sleep(0.05)
        raise RuntimeError("SAP unavailable")

    def read_cached():
        start.wait(timeout=2)
        return resources._cache_get_or_load("error-demo", 60, failing_load)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(read_cached) for _ in range(workers)]

    for future in futures:
        with pytest.raises(RuntimeError, match="SAP unavailable"):
            future.result()
    assert calls == 1

    assert resources._cache_get_or_load("error-demo", 60, lambda: {"ok": True}) == {"ok": True}


def test_invalidate_cache_detaches_inflight_load():
    load_started = threading.Event()
    release_load = threading.Event()

    def slow_load():
        load_started.set()
        assert release_load.wait(timeout=2)
        return {"version": 1}

    with ThreadPoolExecutor(max_workers=1) as executor:
        first_load = executor.submit(resources._cache_get_or_load, "invalidate-demo", 60, slow_load)
        assert load_started.wait(timeout=2)
        assert resources.invalidate_cache("invalidate-demo") == 0
        release_load.set()
        assert first_load.result() == {"version": 1}

    assert resources._cache_get_or_load("invalidate-demo", 60, lambda: {"version": 2}) == {"version": 2}


def test_system_info_is_sanitized_and_cached(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(resources, "_connector", lambda destination=None: FakeSDKConnector(calls))

    info = resources.get_system_info()
    again = resources.get_system_info()

    assert calls == ["STFC_CONNECTION"]
    assert info == again
    assert info["stfc_connection"]["ECHOTEXT"] == "sapmcp ping"
    assert info["sdk_version"] == "7.50.12"
    assert "PASSWD" not in info["sap_params"]
    assert "top-secret" not in repr(info)
    assert "nwrfc" not in repr(info).lower()
    assert "/secret/sdk" not in repr(info)


def test_table_schema_resource_formats_ddif_fields(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(resources, "_connector", lambda destination=None: FakeSDKConnector(calls))

    schema = resources.get_table_schema("bkpf")

    assert calls == ["DDIF_FIELDINFO_GET"]
    assert schema["uri"] == "sap://table/BKPF/schema"
    assert schema["table"] == "BKPF"
    assert schema["ttl_seconds"] == 600
    assert schema["fields"] == [
        {
            "field": "MANDT",
            "type": "CLNT",
            "inttype": "C",
            "length": "3",
            "int_length": "6",
            "decimals": "0",
            "position": "1",
            "key": True,
            "text": "Client",
            "rollname": "MANDT",
        },
        {
            "field": "BELNR",
            "type": "CHAR",
            "inttype": "C",
            "length": "10",
            "int_length": "20",
            "decimals": "0",
            "position": "2",
            "key": True,
            "text": "Document Number",
            "rollname": "BELNR_D",
        },
    ]


def test_rfc_catalog_resource_uses_read_table_and_policy_limit(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(resources, "_connector", lambda destination=None: FakeSDKConnector(calls))
    monkeypatch.setenv("SAPMCP_MAX_ROWS", "10")

    catalog = resources.search_rfc_catalog("BAPI_USER", limit=50)

    assert calls == ["RFC_READ_TABLE"]
    assert catalog["uri"] == "sap://catalog/rfc?prefix=BAPI_USER"
    assert catalog["limit"] == 10
    assert catalog["functions"] == ["BAPI_USER_GET_DETAIL"]


def test_rfc_catalog_cache_is_reused_across_requested_limits(monkeypatch):
    calls: list[int] = []

    class MultiRowCatalogConnector(FakeSDKConnector):
        def call_function(self, function_name, **kwargs):
            if function_name.upper() != "RFC_READ_TABLE":
                return super().call_function(function_name, **kwargs)
            calls.append(kwargs["import_params"]["ROWCOUNT"])
            fields = [row["FIELDNAME"] for row in kwargs["input_tables"]["FIELDS"]]
            rows = [
                {"FUNCNAME": "Z_ALPHA", "FMODE": "R"},
                {"FUNCNAME": "Z_BETA", "FMODE": "R"},
                {"FUNCNAME": "Z_GAMMA", "FMODE": "R"},
            ]
            return {
                "FIELDS": [{"FIELDNAME": field} for field in fields],
                "DATA": [{"WA": "\t".join(row.get(field, "") for field in fields)} for row in rows],
            }

    monkeypatch.setattr(resources, "_connector", lambda destination=None: MultiRowCatalogConnector([]))
    monkeypatch.setenv("SAPMCP_MAX_ROWS", "10")

    one = resources.search_rfc_catalog("Z_", limit=1)
    three = resources.search_rfc_catalog("Z_", limit=3)

    assert calls == [10]
    assert one["limit"] == 1
    assert one["functions"] == ["Z_ALPHA"]
    assert three["limit"] == 3
    assert three["functions"] == ["Z_ALPHA", "Z_BETA", "Z_GAMMA"]


def test_rfc_catalog_prefix_is_escaped_as_literal(monkeypatch):
    seen_kwargs: list[dict] = []

    class CaptureCatalogConnector(FakeSDKConnector):
        def call_function(self, function_name, **kwargs):
            seen_kwargs.append(kwargs)
            return super().call_function(function_name, **kwargs)

    monkeypatch.setattr(resources, "_connector", lambda destination=None: CaptureCatalogConnector([]))

    resources.search_rfc_catalog("' OR '1'='1", limit=1)

    assert seen_kwargs[0]["input_tables"]["OPTIONS"] == [{"TEXT": "FUNCNAME LIKE ''' OR ''1''=''1%'"}]
