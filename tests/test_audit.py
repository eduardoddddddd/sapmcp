from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json

import pytest

from sapmcp.audit import audited, audit_log_path, params_hash, tail_audit


@pytest.fixture(autouse=True)
def audit_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SAPMCP_HOME", str(tmp_path))
    monkeypatch.setenv("SAP_ASHOST", "DEV")
    monkeypatch.setenv("SAP_SYSNR", "00")
    monkeypatch.setenv("SAP_CLIENT", "100")
    monkeypatch.setenv("SAP_USER", "RFC_AUDIT")
    monkeypatch.setenv("SAP_PASS", "super-secret")
    monkeypatch.delenv("SAPMCP_USE_KEYRING", raising=False)
    monkeypatch.delenv("SAPMCP_DESTINATIONS", raising=False)
    monkeypatch.delenv("SAPMCP_DEFAULT_DESTINATION", raising=False)
    yield


def test_audited_writes_jsonl_hashes_params_and_omits_password():
    @audited("sap_rfc_call")
    def fake_tool(function_name: str, import_params: dict[str, str], confirm_dangerous: bool = False):
        return {"ok": True}

    result = fake_tool(
        function_name="BAPI_USER_GET_DETAIL",
        import_params={"USERNAME": "ALICE", "PASSWORD": "must-not-leak"},
        confirm_dangerous=False,
    )

    assert result == {"ok": True}
    path = audit_log_path()
    line = path.read_text(encoding="utf-8").strip()
    record = json.loads(line)

    assert record["tool"] == "sap_rfc_call"
    assert record["destination"] == "default"
    assert record["function"] == "BAPI_USER_GET_DETAIL"
    assert record["rc"] == 0
    assert record["sid"] == "DEV"
    assert record["mandt"] == "100"
    assert record["user"] == "RFC_AUDIT"
    assert record["confirmed"] is False
    assert len(record["params_hash"]) == 64
    assert record["params_hash"] == params_hash(
        {
            "function_name": "BAPI_USER_GET_DETAIL",
            "import_params": {"USERNAME": "ALICE", "PASSWORD": "must-not-leak"},
            "confirm_dangerous": False,
        }
    )
    assert "super-secret" not in line
    assert "must-not-leak" not in line
    assert "ALICE" not in line
    assert tail_audit(1) == [record]


def test_audited_records_rc_and_error_on_exception():
    @audited("sap_read_table")
    def failing_tool(table_name: str):
        raise ValueError("boom")

    with pytest.raises(ValueError):
        failing_tool(table_name="T000")

    record = json.loads(audit_log_path().read_text(encoding="utf-8").strip())
    assert record["tool"] == "sap_read_table"
    assert record["function"] == "RFC_READ_TABLE"
    assert record["rc"] == 1
    assert record["error_key"] == "ValueError"
    assert record["error_message"] == "boom"


def test_audited_concurrent_writes_keep_valid_jsonl():
    @audited("sap_ping")
    def fake_tool(index: int):
        return {"index": index}

    with ThreadPoolExecutor(max_workers=8) as executor:
        assert list(executor.map(fake_tool, range(40))) == [{"index": index} for index in range(40)]

    lines = audit_log_path().read_text(encoding="utf-8").splitlines()
    assert len(lines) == 40
    records = [json.loads(line) for line in lines]
    assert {record["tool"] for record in records} == {"sap_ping"}
    assert {record["function"] for record in records} == {"RFC_PING"}
