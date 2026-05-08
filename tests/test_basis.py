from __future__ import annotations

from typing import Any

import pytest

from sapmcp import basis


@pytest.fixture(autouse=True)
def basis_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SAPMCP_HOME", str(tmp_path))
    monkeypatch.setenv("SAP_ASHOST", "basis.example.local")
    monkeypatch.setenv("SAP_SYSNR", "00")
    monkeypatch.setenv("SAP_CLIENT", "100")
    monkeypatch.setenv("SAP_USER", "RFC_BASIS")
    monkeypatch.setenv("SAP_PASS", "secret")
    monkeypatch.setenv("SAPMCP_READ_ONLY", "true")
    monkeypatch.delenv("SAPMCP_ALLOWED_RFC", raising=False)
    monkeypatch.delenv("SAPMCP_DESTINATIONS", raising=False)
    monkeypatch.delenv("SAPMCP_DEFAULT_DESTINATION", raising=False)
    yield


class FakeBasisConnector:
    def __init__(self, available: set[str] | None = None):
        self.available = {name.upper() for name in (available or set())}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def has_function(self, function_name: str) -> bool:
        return function_name.upper() in self.available

    def call_function(self, function_name: str, **kwargs: Any) -> dict[str, Any]:
        name = function_name.upper()
        self.calls.append((name, kwargs))
        if name not in self.available:
            raise AssertionError(f"Unexpected unavailable RFC call: {name}")
        if name == "RFC_GET_SHORT_DUMP_LIST":
            return {
                "DUMPS": [
                    {"DATUM": "20260506", "UZEIT": "121500", "UNAME": "ALICE", "PROG": "ZREP", "AHOST": "app1", "T100MSG": "MESSAGE_TYPE_X"},
                    {"DATUM": "20260506", "UZEIT": "101500", "UNAME": "ALICE", "PROG": "ZREP", "AHOST": "app1", "T100MSG": "MESSAGE_TYPE_X"},
                    {"DATUM": "20260506", "UZEIT": "091500", "UNAME": "BOB", "PROG": "ZREP2", "AHOST": "app2", "T100MSG": "ASSERTION_FAILED"},
                ]
            }
        if name == "ENQUEUE_READ":
            return {
                "ENQ": [
                    {"GNAME": "BKPF", "GARG": "100010", "GUNAME": "ALICE", "GTARG": "app1", "GTCODE": "FB03", "GTDATE": "20260506", "GTTIME": "120000"},
                    {"GNAME": "MARA", "GARG": "MAT1", "GUNAME": "BOB", "GTARG": "app2", "GTCODE": "MM03", "GTDATE": "20260506", "GTTIME": "120100"},
                ]
            }
        if name == "BAPI_USER_GET_DETAIL":
            return {
                "ADDRESS": {"FULLNAME": "Alice Basis", "E_MAIL": "alice@example.local"},
                "PROFILES": [{"BAPIPROF": "SAP_ALL"}, {"BAPIPROF": "S_A.SYSTEM"}],
                "ACTIVITYGROUPS": [{"AGR_NAME": "Z_BASIS_DISPLAY"}],
            }
        if name == "BAPI_USER_LOCK_STATUS":
            return {"LOCKSTATUS": "0", "WRNG_LOGON": "0"}
        if name == "BAPI_XBP_JOB_SELECT":
            return {
                "JOBLIST": [
                    {"JOBNAME": "FINISHED_JOB", "JOBCOUNT": "001", "STATUS": "F", "SDLSTRTDT": "20260506", "SDLSTRTTM": "130000", "ENDDATE": "20260506", "ENDTIME": "130500", "USERNAME": "BATCH", "RUNTIME": "300", "STEPS": "2"},
                    {"JOBNAME": "ABORTED_JOB", "JOBCOUNT": "002", "STATUS": "A", "SDLSTRTDT": "20260506", "SDLSTRTTM": "120000", "ENDDATE": "20260506", "ENDTIME": "120100", "USERNAME": "BATCH", "RUNTIME": "60", "STEPS": "1"},
                ]
            }
        if name == "BAPI_SYSLOG_READ":
            return {
                "SYSLOG": [
                    {"DATUM": "20260506", "UZEIT": "090000", "INSTANCE": "app1", "UNAME": "ALICE", "MANDT": "100", "SEVERITY": "E", "MESSAGE": "Update error"},
                    {"DATUM": "20260506", "UZEIT": "091000", "INSTANCE": "app1", "UNAME": "BOB", "MANDT": "100", "SEVERITY": "W", "MESSAGE": "Warning"},
                ]
            }
        if name == "RFC_READ_TABLE":
            table = kwargs.get("import_params", {}).get("QUERY_TABLE")
            if table == "USR02":
                return {
                    "FIELDS": [{"FIELDNAME": field} for field in ["BNAME", "GLTGV", "GLTGB", "TRDAT", "LTIME", "UFLAG", "LOCNT"]],
                    "DATA": [{"WA": "ALICE\t20260101\t20261231\t20260505\t081500\t0\t3"}],
                }
            raise AssertionError(f"Unexpected RFC_READ_TABLE table: {table}")
        raise AssertionError(f"Unexpected RFC: {name}")


def test_sap_get_short_dumps_with_simulated_dumps(monkeypatch):
    fake = FakeBasisConnector({"RFC_GET_SHORT_DUMP_LIST"})
    monkeypatch.setattr(basis, "_connector", lambda destination=None: fake)

    result = basis.sap_get_short_dumps(date_from="20260506", date_to="20260506", user="ALICE")

    assert result["available"] is True
    assert result["source"] == "RFC_GET_SHORT_DUMP_LIST"
    assert result["count"] == 2
    assert result["dumps"][0]["fecha"] == "20260506"
    assert result["dumps"][0]["hora"] == "121500"
    assert result["dumps"][0]["usuario"] == "ALICE"
    assert result["dumps"][0]["last"] is True
    assert result["dumps"][1]["last"] is False


def test_sap_get_locks_with_two_locks(monkeypatch):
    fake = FakeBasisConnector({"ENQUEUE_READ"})
    monkeypatch.setattr(basis, "_connector", lambda destination=None: fake)

    result = basis.sap_get_locks()

    assert result["available"] is True
    assert result["count"] == 2
    assert result["locks"] == [
        {"gname": "BKPF", "garg": "100010", "guname": "ALICE", "gtarg": "app1", "gtcode": "FB03", "gtdate": "20260506", "gttime": "120000"},
        {"gname": "MARA", "garg": "MAT1", "guname": "BOB", "gtarg": "app2", "gtcode": "MM03", "gtdate": "20260506", "gttime": "120100"},
    ]


def test_sap_get_user_audit_detects_sap_all(monkeypatch):
    fake = FakeBasisConnector({"BAPI_USER_GET_DETAIL", "BAPI_USER_LOCK_STATUS", "RFC_READ_TABLE"})
    monkeypatch.setattr(basis, "_connector", lambda destination=None: fake)

    result = basis.sap_get_user_audit("alice")

    assert result["available"] is True
    assert result["user"] == "ALICE"
    assert result["fullname"] == "Alice Basis"
    assert result["sap_all"] is True
    assert result["profiles"] == ["SAP_ALL", "S_A.SYSTEM"]
    assert result["roles"] == ["Z_BASIS_DISPLAY"]
    assert result["lastlogon"] == "20260505 081500"
    assert result["failed_logons"] == 3


def test_sap_get_jobs_filters_status(monkeypatch):
    fake = FakeBasisConnector({"BAPI_XBP_JOB_SELECT"})
    monkeypatch.setattr(basis, "_connector", lambda destination=None: fake)

    result = basis.sap_get_jobs(status="F", top_n=50, since_days=1)

    assert result["available"] is True
    assert result["count"] == 1
    assert result["jobs"][0]["jobname"] == "FINISHED_JOB"
    assert result["jobs"][0]["status"] == "F"
    assert result["jobs"][0]["steps"] == 2


def test_sap_get_syslog_falls_back_to_bapi_syslog_read(monkeypatch):
    fake = FakeBasisConnector({"BAPI_SYSLOG_READ"})
    monkeypatch.setattr(basis, "_connector", lambda destination=None: fake)

    result = basis.sap_get_syslog(date_from="20260506", date_to="20260506", severity="E")

    assert result["available"] is True
    assert result["source"] == "BAPI_SYSLOG_READ"
    assert result["count"] == 1
    assert result["entries"][0]["mensaje"] == "Update error"
    assert fake.calls[0][0] == "BAPI_SYSLOG_READ"


class CapturingReadTableConnector:
    def __init__(self):
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def has_function(self, function_name: str) -> bool:
        return function_name.upper() == "RFC_READ_TABLE"

    def call_function(self, function_name: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append((function_name.upper(), kwargs))
        fields = [row["FIELDNAME"] for row in kwargs.get("input_tables", {}).get("FIELDS", [])]
        return {"FIELDS": [{"FIELDNAME": field} for field in fields], "DATA": []}


def test_short_dump_snap_fallback_builds_safe_options(monkeypatch):
    fake = CapturingReadTableConnector()
    monkeypatch.setattr(basis, "_connector", lambda destination=None: fake)

    result = basis.sap_get_short_dumps(date_from="20260506", date_to="20260506", user="alice")

    assert result["available"] is True
    assert result["source"] == "SNAP"
    assert fake.calls == [
        (
            "RFC_READ_TABLE",
            {
                "import_params": {"QUERY_TABLE": "SNAP", "DELIMITER": "\t", "NO_DATA": "", "ROWSKIPS": 0, "ROWCOUNT": 200},
                "input_tables": {
                    "FIELDS": [
                        {"FIELDNAME": "DATUM"},
                        {"FIELDNAME": "UZEIT"},
                        {"FIELDNAME": "UNAME"},
                        {"FIELDNAME": "PROG"},
                        {"FIELDNAME": "AHOST"},
                        {"FIELDNAME": "T100MSG"},
                    ],
                    "OPTIONS": [{"TEXT": "DATUM >= '20260506'"}, {"TEXT": "AND DATUM <= '20260506'"}, {"TEXT": "AND UNAME = 'ALICE'"}],
                },
                "output_tables": ["FIELDS", "DATA"],
                "table_fields": {"FIELDS": ["FIELDNAME"], "DATA": ["WA"]},
            },
        )
    ]


@pytest.mark.parametrize("payload", ["' OR '1'='1", "USER' AND '1'='1"])
def test_user_audit_rejects_injection_payload_before_connector(monkeypatch, payload):
    called = False

    def connector(destination=None):
        nonlocal called
        called = True
        return CapturingReadTableConnector()

    monkeypatch.setattr(basis, "_connector", connector)

    with pytest.raises(ValueError):
        basis.sap_get_user_audit(payload)

    assert called is False
