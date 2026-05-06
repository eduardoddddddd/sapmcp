from __future__ import annotations

import itertools
import threading
import time
from typing import Any

import pytest

from sapmcp import health


@pytest.fixture(autouse=True)
def health_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SAPMCP_HOME", str(tmp_path))
    monkeypatch.setenv("SAP_ASHOST", "S4D")
    monkeypatch.setenv("SAP_SYSNR", "00")
    monkeypatch.setenv("SAP_CLIENT", "100")
    monkeypatch.setenv("SAP_USER", "RFC_HEALTH")
    monkeypatch.setenv("SAP_PASS", "secret")
    monkeypatch.setenv("SAPMCP_READ_ONLY", "true")
    monkeypatch.delenv("SAPMCP_ALLOWED_RFC", raising=False)
    monkeypatch.delenv("SAPMCP_DESTINATIONS", raising=False)
    monkeypatch.delenv("SAPMCP_DEFAULT_DESTINATION", raising=False)
    for name in list(__import__("os").environ):
        if name.startswith("SAPMCP_HC_"):
            monkeypatch.delenv(name, raising=False)
    yield


class FakeHealthConnector:
    _ids = itertools.count(1)

    def __init__(self, seen_handles: list[int] | None = None, barrier: threading.Barrier | None = None):
        self.connection_handle: int | None = None
        self.seen_handles = seen_handles
        self.barrier = barrier

    def __enter__(self):
        self.connection_handle = next(self._ids)
        if self.seen_handles is not None:
            self.seen_handles.append(self.connection_handle)
        if self.barrier is not None:
            try:
                self.barrier.wait(timeout=1)
            except threading.BrokenBarrierError:
                pass
        return self

    def __exit__(self, exc_type, exc, tb):
        self.connection_handle = None
        return None

    def has_function(self, function_name: str) -> bool:
        return True

    def call_function(self, function_name: str, **kwargs: Any) -> dict[str, Any]:
        name = function_name.upper()
        if name == "STFC_CONNECTION":
            return {"ECHOTEXT": kwargs.get("import_params", {}).get("REQUTEXT", ""), "RESPTEXT": "ok"}
        if name == "ENQUEUE_READ":
            return {"ENQ": []}
        if name == "TH_SERVER_LIST":
            return {"LIST": [{"NAME": "app1"}]}
        if name == "TH_WPINFO":
            return {"WPLIST": [{"WP_NO": "1", "WP_TYP": "DIA", "WP_STATUS": "waiting"}]}
        if name == "RFC_GET_SHORT_DUMP_LIST":
            return {"DUMPS": []}
        if name == "BAPI_UPDREQUEST_GETLIST":
            return {"REQUESTS": []}
        if name == "BAPI_XBP_JOB_SELECT":
            return {"JOBLIST": []}
        if name == "RFC_READ_TABLE":
            table = kwargs.get("import_params", {}).get("QUERY_TABLE")
            if table == "ARFCSSTATE":
                return {"FIELDS": [{"FIELDNAME": field} for field in ["ARFCDEST", "ARFCUSER", "ARFCDATE", "ARFCTIME", "ARFCFNAM", "ARFCSTATE", "ARFCMSG"]], "DATA": []}
            return {"FIELDS": [], "DATA": []}
        return {}


def test_quick_profile_returns_ok_when_ping_responds(monkeypatch):
    monkeypatch.setattr(health, "_connector", lambda destination=None: FakeHealthConnector())
    # basis.py imported _connector separately, so point those helpers at the same fake factory.
    import sapmcp.basis as basis

    monkeypatch.setattr(basis, "_connector", lambda destination=None: FakeHealthConnector())

    result = health.sap_health_check(profile="quick")

    assert result["destination"] == "default"
    assert result["sid"] == "S4D"
    assert result["mandt"] == "100"
    assert result["profile"] == "quick"
    assert result["verdict"] == "ok"
    assert any(check["name"] == "ping" and check["status"] == "ok" for check in result["checks"])


def test_standard_with_dumps_over_crit_returns_crit(monkeypatch):
    def fake_dumps(destination=None, thresholds=None):
        return {"name": "dumps_24h", "status": "crit", "value": 20, "threshold": {"warn": 5, "crit": 20}, "duration_ms": 1, "error": None}

    monkeypatch.setattr(health, "_ping_check", lambda destination: {"name": "ping", "status": "ok", "value": {}, "threshold": None, "duration_ms": 1, "error": None})
    monkeypatch.setattr(health, "_dumps_check", lambda destination, thresholds: fake_dumps())
    monkeypatch.setattr(health, "_locks_check", lambda destination, thresholds: {"name": "locks_total", "status": "ok", "value": 0, "threshold": {}, "duration_ms": 1, "error": None})
    monkeypatch.setattr(health, "_workprocess_checks", lambda destination, thresholds: [{"name": "workprocesses_priv", "status": "ok", "value": 0, "threshold": {}, "duration_ms": 1, "error": None}, {"name": "workprocesses_stopped", "status": "ok", "value": 0, "threshold": {}, "duration_ms": 1, "error": None}])
    monkeypatch.setattr(health, "_update_checks", lambda destination, thresholds: [{"name": "update_pending", "status": "ok", "value": 0, "threshold": {}, "duration_ms": 1, "error": None}, {"name": "update_err", "status": "ok", "value": 0, "threshold": {}, "duration_ms": 1, "error": None}])
    monkeypatch.setattr(health, "_trfc_check", lambda destination, thresholds: {"name": "trfc_pending", "status": "ok", "value": 0, "threshold": {}, "duration_ms": 1, "error": None})
    monkeypatch.setattr(health, "_jobs_aborted_check", lambda destination, thresholds: {"name": "jobs_aborted_24h", "status": "ok", "value": 0, "threshold": {}, "duration_ms": 1, "error": None})

    result = health.sap_health_check(profile="standard")

    assert result["verdict"] == "crit"
    assert next(check for check in result["checks"] if check["name"] == "dumps_24h")["value"] == 20


def test_timeout_check_is_unknown_and_verdict_not_ok(monkeypatch):
    old = health.PROFILE_TIMEOUTS.copy()
    monkeypatch.setitem(health.PROFILE_TIMEOUTS, "quick", 0.05)
    monkeypatch.setattr(health, "_ping_check", lambda destination: (time.sleep(0.2) or {"name": "ping", "status": "ok", "value": {}, "threshold": None, "duration_ms": 200, "error": None}))
    monkeypatch.setattr(health, "_locks_check", lambda destination, thresholds: {"name": "locks_total", "status": "ok", "value": 0, "threshold": {}, "duration_ms": 1, "error": None})
    monkeypatch.setattr(health, "_workprocess_checks", lambda destination, thresholds: [{"name": "workprocesses_priv", "status": "ok", "value": 0, "threshold": {}, "duration_ms": 1, "error": None}])

    result = health.sap_health_check(profile="quick")

    timed = [check for check in result["checks"] if check.get("error") == "timeout"]
    assert timed
    assert result["verdict"] != "ok"
    monkeypatch.setattr(health, "PROFILE_TIMEOUTS", old)


def test_verdict_crit_overrides_warn():
    checks = [
        {"name": "a", "status": "warn"},
        {"name": "b", "status": "crit"},
        {"name": "c", "status": "ok"},
    ]
    assert health._global_verdict(checks) == "crit"


def test_parallel_checks_do_not_share_connection_handle(monkeypatch):
    seen: list[int] = []
    barrier = threading.Barrier(2)

    def factory(destination=None):
        return FakeHealthConnector(seen, barrier)

    monkeypatch.setattr(health, "_connector", factory)
    import sapmcp.basis as basis

    monkeypatch.setattr(basis, "_connector", factory)

    result = health.sap_health_check(profile="quick")

    assert result["verdict"] in {"ok", "warn"}
    assert len(seen) >= 2
    assert len(set(seen)) == len(seen)
