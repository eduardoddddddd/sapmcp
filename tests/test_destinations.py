from __future__ import annotations

import json
from typing import Any

import pytest

from sapmcp import resources
from sapmcp.audit import audited, audit_log_path
from sapmcp.config import SapConnectionConfig, list_destinations
from sapmcp import server


@pytest.fixture(autouse=True)
def destinations_env(monkeypatch, tmp_path):
    resources.invalidate_cache()
    monkeypatch.setenv("SAPMCP_HOME", str(tmp_path))
    monkeypatch.setenv("SAP_ASHOST", "classic.example.local")
    monkeypatch.setenv("SAP_SYSNR", "00")
    monkeypatch.setenv("SAP_CLIENT", "100")
    monkeypatch.setenv("SAP_USER", "CLASSIC_USER")
    monkeypatch.setenv("SAP_PASS", "classic-secret")
    monkeypatch.setenv("SAPMCP_DESTINATIONS", "DEV,QAS")
    monkeypatch.delenv("SAPMCP_DEFAULT_DESTINATION", raising=False)
    monkeypatch.delenv("SAPMCP_USE_KEYRING", raising=False)
    monkeypatch.setenv("SAP_DEV_ASHOST", "dev.example.local")
    monkeypatch.setenv("SAP_DEV_SYSNR", "01")
    monkeypatch.setenv("SAP_DEV_CLIENT", "110")
    monkeypatch.setenv("SAP_DEV_USER", "DEV_USER")
    monkeypatch.setenv("SAP_DEV_PASS", "dev-secret")
    monkeypatch.setenv("SAP_DEV_LANG", "ES")
    monkeypatch.setenv("SAP_QAS_ASHOST", "qas.example.local")
    monkeypatch.setenv("SAP_QAS_SYSNR", "02")
    monkeypatch.setenv("SAP_QAS_CLIENT", "120")
    monkeypatch.setenv("SAP_QAS_USER", "QAS_USER")
    monkeypatch.setenv("SAP_QAS_PASS", "qas-secret")
    monkeypatch.setenv("SAPMCP_READ_ONLY", "true")
    yield
    resources.invalidate_cache()


class DestinationConnector:
    def __init__(self, calls: list[tuple[str, str]], destination: str | None = None):
        self.calls = calls
        self.destination = destination
        self.sap_lib = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def call_function(self, function_name: str, **kwargs: Any) -> dict[str, Any]:
        logical = self.destination or "default"
        self.calls.append((logical, function_name.upper()))
        if function_name.upper() == "RFC_GET_FUNCTION_INTERFACE":
            func = kwargs.get("import_params", {}).get("FUNCNAME", "")
            return {"PARAMS": [{"PARAMETER": f"{logical}:{func}"}]}
        return {"DESTINATION": logical, "FUNCTION": function_name.upper()}


def test_from_destination_dev_uses_prefixed_sap_env():
    config = SapConnectionConfig.from_destination("DEV")

    assert config.destination == "DEV"
    assert config.params["ASHOST"] == "dev.example.local"
    assert config.params["SYSNR"] == "01"
    assert config.params["CLIENT"] == "110"
    assert config.params["USER"] == "DEV_USER"
    assert config.params["PASSWD"] == "dev-secret"
    assert config.params["LANG"] == "ES"
    assert config.sanitized()["PASSWD"] == "********"


def test_list_destinations_includes_default_and_named():
    assert list_destinations() == ["default", "DEV", "QAS"]


def test_get_function_interface_cache_is_namespaced_by_destination(monkeypatch):
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(resources, "_connector", lambda destination=None: DestinationConnector(calls, destination))

    dev_first = resources.get_function_interface("z_demo", destination="DEV")
    qas_first = resources.get_function_interface("z_demo", destination="QAS")
    dev_second = resources.get_function_interface("Z_DEMO", destination="DEV")

    assert dev_first == dev_second
    assert dev_first["destination"] == "DEV"
    assert qas_first["destination"] == "QAS"
    assert dev_first["interface"]["PARAMS"][0]["PARAMETER"] == "DEV:Z_DEMO"
    assert qas_first["interface"]["PARAMS"][0]["PARAMETER"] == "QAS:Z_DEMO"
    assert calls == [("DEV", "RFC_GET_FUNCTION_INTERFACE"), ("QAS", "RFC_GET_FUNCTION_INTERFACE")]


def test_audit_log_includes_selected_destination():
    @audited("sap_rfc_call")
    def fake_tool(function_name: str, destination: str | None = None):
        return {"ok": True}

    assert fake_tool("BAPI_USER_GET_DETAIL", destination="DEV") == {"ok": True}

    record = json.loads(audit_log_path().read_text(encoding="utf-8").strip())
    assert record["destination"] == "DEV"
    assert record["sid"] == "dev.example.local"
    assert record["mandt"] == "110"
    assert record["user"] == "DEV_USER"
    assert "dev-secret" not in json.dumps(record)


def test_sap_rfc_call_without_destination_uses_classic_default(monkeypatch):
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(server, "_connector", lambda destination=None: DestinationConnector(calls, destination))

    result = server.sap_rfc_call(
        function_name="BAPI_USER_GET_DETAIL",
        import_params={"USERNAME": "ALICE"},
        output_tables=["RETURN"],
    )

    assert calls == [("default", "BAPI_USER_GET_DETAIL")]
    assert result == {"DESTINATION": "default", "FUNCTION": "BAPI_USER_GET_DETAIL"}
