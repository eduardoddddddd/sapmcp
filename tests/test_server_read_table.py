from __future__ import annotations

from typing import Any

import pytest

from sapmcp import server


@pytest.fixture(autouse=True)
def server_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SAPMCP_HOME", str(tmp_path))
    monkeypatch.setenv("SAP_ASHOST", "sap.example.local")
    monkeypatch.setenv("SAP_SYSNR", "00")
    monkeypatch.setenv("SAP_CLIENT", "100")
    monkeypatch.setenv("SAP_USER", "RFC_USER")
    monkeypatch.setenv("SAP_PASS", "secret")
    monkeypatch.setenv("SAPMCP_READ_ONLY", "true")
    monkeypatch.setenv("SAPMCP_MAX_ROWS", "25")
    monkeypatch.delenv("SAPMCP_ALLOWED_RFC", raising=False)
    monkeypatch.delenv("SAPMCP_DESTINATIONS", raising=False)
    monkeypatch.delenv("SAPMCP_DEFAULT_DESTINATION", raising=False)
    yield


class FakeReadTableConnector:
    def __init__(self):
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def call_function(self, function_name: str, **kwargs: Any):
        self.calls.append((function_name, kwargs))
        return {
            "FIELDS": [{"FIELDNAME": "BNAME"}],
            "DATA": [{"WA": "ALICE"}],
        }


@pytest.mark.parametrize(
    "kwargs",
    [
        {"table_name": "USR02;DELETE"},
        {"table_name": "USR02", "fields": ["BNAME FROM USR02"]},
        {"table_name": "USR02", "rowskips": -1},
        {"table_name": "USR02", "delimiter": "||"},
        {"table_name": "USR02", "delimiter": "\n"},
    ],
)
def test_sap_read_table_rejects_invalid_inputs_before_connector(monkeypatch, kwargs):
    fake = FakeReadTableConnector()
    monkeypatch.setattr(server, "_connector", lambda destination=None: fake)

    with pytest.raises(ValueError):
        server.sap_read_table(**kwargs)

    assert fake.calls == []


@pytest.mark.parametrize("where", [["' OR '1'='1"], ["USER' AND '1'='1"], ["BNAME = 'ALICE' OR '1'='1'"]])
def test_sap_read_table_advanced_where_rejects_obvious_injection(monkeypatch, where):
    fake = FakeReadTableConnector()
    monkeypatch.setattr(server, "_connector", lambda destination=None: fake)

    with pytest.raises(ValueError):
        server.sap_read_table("USR02", fields=["BNAME"], where=where)

    assert fake.calls == []


def test_sap_read_table_keeps_compatible_valid_advanced_where(monkeypatch):
    fake = FakeReadTableConnector()
    monkeypatch.setattr(server, "_connector", lambda destination=None: fake)

    result = server.sap_read_table("usr02", fields=["bname"], where=["BNAME = 'ALICE'"], rowcount=100)

    assert result["table"] == "USR02"
    assert result["rowcount_requested"] == 25
    assert result["rows"] == [{"BNAME": "ALICE"}]
    assert fake.calls[0][1]["input_tables"]["OPTIONS"] == [{"TEXT": "BNAME = 'ALICE'"}]
