from __future__ import annotations

import concurrent.futures
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Any, Callable, Literal

from . import _connector
from .audit import audited
from .basis import (
    _call,
    _read_table,
    sap_get_jobs,
    sap_get_locks,
    sap_get_rfc_queue,
    sap_get_short_dumps,
    sap_get_update_requests,
    sap_get_workprocesses,
)
from .config import SafetyPolicy, SapConnectionConfig

CheckStatus = Literal["ok", "warn", "crit", "unknown"]
HealthProfile = Literal["quick", "standard", "deep"]

PROFILE_TIMEOUTS: dict[str, float] = {"quick": 2.0, "standard": 15.0, "deep": 45.0}


@dataclass(frozen=True)
class Threshold:
    warn: int
    crit: int

    def as_dict(self) -> dict[str, int]:
        return {"warn": self.warn, "crit": self.crit}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _threshold(key: str, warn_default: int, crit_default: int) -> Threshold:
    prefix = f"SAPMCP_HC_{key.upper()}"
    return Threshold(warn=_env_int(f"{prefix}_WARN", warn_default), crit=_env_int(f"{prefix}_CRIT", crit_default))


def _thresholds() -> dict[str, Threshold]:
    return {
        "dumps_24h": _threshold("DUMPS", 5, 20),
        "locks_total": _threshold("LOCKS", 50, 200),
        "update_pending": _threshold("UPDATE_PENDING", 1, 10),
        "update_err": _threshold("UPDATE_ERR", 1, 1),
        "trfc_pending": _threshold("TRFC", 20, 100),
        "jobs_aborted_24h": _threshold("JOBS_ABORTED", 1, 5),
        "workprocesses_priv": _threshold("WP_PRIV", 1, 2),
        "workprocesses_stopped": _threshold("WP_STOPPED", 1, 1),
    }


def _status_for_count(value: int, threshold: Threshold) -> CheckStatus:
    if value >= threshold.crit:
        return "crit"
    if value >= threshold.warn:
        return "warn"
    return "ok"


def _check(name: str, status: CheckStatus, value: Any, threshold: Any = None, *, duration_ms: float = 0.0, error: str | None = None) -> dict[str, Any]:
    return {"name": name, "status": status, "value": value, "threshold": threshold, "duration_ms": round(duration_ms, 3), "error": error}


def _timed_check(name: str, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    start = perf_counter()
    try:
        result = fn()
        result.setdefault("name", name)
        result.setdefault("status", "unknown")
        result.setdefault("value", None)
        result.setdefault("threshold", None)
        result.setdefault("error", None)
        result["duration_ms"] = round((perf_counter() - start) * 1000, 3)
        if result.get("error") and result.get("status") == "ok":
            result["status"] = "unknown"
        return result
    except Exception as exc:
        return _check(name, "unknown", None, duration_ms=(perf_counter() - start) * 1000, error=str(exc))


def _date_24h() -> str:
    return (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")


def _ping_check(destination: str | None) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        SafetyPolicy.from_env().assert_allowed("STFC_CONNECTION")
        with _connector(destination) as sap:
            result = _call(
                sap,
                "STFC_CONNECTION",
                import_params={"REQUTEXT": "sapmcp health check"},
                output_params=["ECHOTEXT", "RESPTEXT"],
            )
        return _check("ping", "ok", result, None)

    return _timed_check("ping", run)


def _dumps_check(destination: str | None, thresholds: dict[str, Threshold]) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        result = sap_get_short_dumps(date_from=_date_24h(), date_to=None, user=None, destination=destination)
        if not result.get("available", True):
            return _check("dumps_24h", "unknown", None, thresholds["dumps_24h"].as_dict(), error=str(result.get("reason")))
        count = int(result.get("count", len(result.get("dumps", []))))
        return _check("dumps_24h", _status_for_count(count, thresholds["dumps_24h"]), count, thresholds["dumps_24h"].as_dict())

    return _timed_check("dumps_24h", run)


def _locks_check(destination: str | None, thresholds: dict[str, Threshold]) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        result = sap_get_locks(destination=destination)
        if not result.get("available", True):
            return _check("locks_total", "unknown", None, thresholds["locks_total"].as_dict(), error=str(result.get("reason")))
        count = int(result.get("count", len(result.get("locks", []))))
        return _check("locks_total", _status_for_count(count, thresholds["locks_total"]), count, thresholds["locks_total"].as_dict())

    return _timed_check("locks_total", run)


def _workprocess_checks(destination: str | None, thresholds: dict[str, Threshold]) -> list[dict[str, Any]]:
    start = perf_counter()
    try:
        result = sap_get_workprocesses(destination=destination)
        duration = (perf_counter() - start) * 1000
        if not result.get("available", True):
            error = str(result.get("reason"))
            return [
                _check("workprocesses_priv", "unknown", None, thresholds["workprocesses_priv"].as_dict(), duration_ms=duration, error=error),
                _check("workprocesses_stopped", "unknown", None, thresholds["workprocesses_stopped"].as_dict(), duration_ms=duration, error=error),
            ]
        rows = result.get("workprocesses", [])
        priv = sum(1 for row in rows if str(row.get("status", "")).upper() == "PRIV")
        stopped = sum(1 for row in rows if str(row.get("status", "")).lower() in {"stopped", "stop", "ended"})
        return [
            _check("workprocesses_priv", _status_for_count(priv, thresholds["workprocesses_priv"]), priv, thresholds["workprocesses_priv"].as_dict(), duration_ms=duration),
            _check("workprocesses_stopped", _status_for_count(stopped, thresholds["workprocesses_stopped"]), stopped, thresholds["workprocesses_stopped"].as_dict(), duration_ms=duration),
        ]
    except Exception as exc:
        duration = (perf_counter() - start) * 1000
        return [
            _check("workprocesses_priv", "unknown", None, thresholds["workprocesses_priv"].as_dict(), duration_ms=duration, error=str(exc)),
            _check("workprocesses_stopped", "unknown", None, thresholds["workprocesses_stopped"].as_dict(), duration_ms=duration, error=str(exc)),
        ]


def _update_checks(destination: str | None, thresholds: dict[str, Threshold]) -> list[dict[str, Any]]:
    start = perf_counter()
    try:
        pending = sap_get_update_requests(destination=destination)
        err = sap_get_update_requests(status="ERR", destination=destination)
        duration = (perf_counter() - start) * 1000
        checks: list[dict[str, Any]] = []
        if not pending.get("available", True):
            checks.append(_check("update_pending", "unknown", None, thresholds["update_pending"].as_dict(), duration_ms=duration, error=str(pending.get("reason"))))
        else:
            value = int(pending.get("count", len(pending.get("requests", []))))
            checks.append(_check("update_pending", _status_for_count(value, thresholds["update_pending"]), value, thresholds["update_pending"].as_dict(), duration_ms=duration))
        if not err.get("available", True):
            checks.append(_check("update_err", "unknown", None, thresholds["update_err"].as_dict(), duration_ms=duration, error=str(err.get("reason"))))
        else:
            value = int(err.get("count", len(err.get("requests", []))))
            checks.append(_check("update_err", _status_for_count(value, thresholds["update_err"]), value, thresholds["update_err"].as_dict(), duration_ms=duration))
        return checks
    except Exception as exc:
        duration = (perf_counter() - start) * 1000
        return [
            _check("update_pending", "unknown", None, thresholds["update_pending"].as_dict(), duration_ms=duration, error=str(exc)),
            _check("update_err", "unknown", None, thresholds["update_err"].as_dict(), duration_ms=duration, error=str(exc)),
        ]


def _trfc_check(destination: str | None, thresholds: dict[str, Threshold]) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        result = sap_get_rfc_queue(queue_type="trfc", destination=destination)
        if not result.get("available", True):
            return _check("trfc_pending", "unknown", None, thresholds["trfc_pending"].as_dict(), error=str(result.get("reason")))
        count = int(result.get("count", len(result.get("entries", []))))
        return _check("trfc_pending", _status_for_count(count, thresholds["trfc_pending"]), count, thresholds["trfc_pending"].as_dict())

    return _timed_check("trfc_pending", run)


def _jobs_aborted_check(destination: str | None, thresholds: dict[str, Threshold]) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        result = sap_get_jobs(status="A", since_days=1, destination=destination)
        if not result.get("available", True):
            return _check("jobs_aborted_24h", "unknown", None, thresholds["jobs_aborted_24h"].as_dict(), error=str(result.get("reason")))
        count = int(result.get("count", len(result.get("jobs", []))))
        return _check("jobs_aborted_24h", _status_for_count(count, thresholds["jobs_aborted_24h"]), count, thresholds["jobs_aborted_24h"].as_dict())

    return _timed_check("jobs_aborted_24h", run)


def _active_users_check(destination: str | None) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        SafetyPolicy.from_env().assert_allowed("TH_USER_LIST")
        with _connector(destination) as sap:
            result = _call(
                sap,
                "TH_USER_LIST",
                output_tables=["USRLIST"],
                table_fields={
                    "USRLIST": ["BNAME", "MANDT", "TERM", "TCODE"],
                },
            )
        users = result.get("USRLIST") or result.get("LIST") or result.get("USERS") or []
        return _check("active_users", "ok", len(users), None)

    return _timed_check("active_users", run)


def _t000_check(destination: str | None) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        with _connector(destination) as sap:
            rows = _read_table(sap, "T000", ["MANDT", "MTEXT"], rowcount=50)
        return _check("clients_t000", "ok", {"count": len(rows), "clients": rows}, None)

    return _timed_check("clients_t000", run)


def _server_list_check(destination: str | None) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        SafetyPolicy.from_env().assert_allowed("TH_SERVER_LIST")
        with _connector(destination) as sap:
            result = _call(sap, "TH_SERVER_LIST", output_tables=["LIST"], table_fields={"LIST": ["NAME", "HOST"]})
        servers = result.get("LIST") or result.get("SERVERS") or []
        return _check("servers", "ok", {"count": len(servers), "servers": servers}, None)

    return _timed_check("servers", run)


def _snap_size_check(destination: str | None) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        with _connector(destination) as sap:
            rows = _read_table(sap, "SNAP", ["DATUM", "UZEIT"], rowcount=SafetyPolicy.from_env().max_rows)
        return _check("snap_sample", "ok", {"sample_count": len(rows), "limited_by": SafetyPolicy.from_env().max_rows}, None)

    return _timed_check("snap_sample", run)


def _syslog_size_check(destination: str | None) -> dict[str, Any]:
    # Keep this intentionally light: it reuses the same syslog APIs as the Basis tool via a 24h error/warn-free read.
    from .basis import sap_get_syslog

    def run() -> dict[str, Any]:
        result = sap_get_syslog(date_from=_date_24h(), date_to=None, severity=None, destination=destination)
        if not result.get("available", True):
            return _check("syslog_sample", "unknown", None, None, error=str(result.get("reason")))
        return _check("syslog_sample", "ok", {"sample_count": int(result.get("count", len(result.get("entries", [])))), "source": result.get("source")}, None)

    return _timed_check("syslog_sample", run)


def _flatten(result: dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    return result if isinstance(result, list) else [result]


def _check_plan(profile: HealthProfile, destination: str | None, thresholds: dict[str, Threshold]) -> list[tuple[str, Callable[[], dict[str, Any] | list[dict[str, Any]]]]]:
    plan: list[tuple[str, Callable[[], dict[str, Any] | list[dict[str, Any]]]]] = [("ping", lambda: _ping_check(destination))]
    if profile == "quick":
        plan.extend(
            [
                ("locks_total", lambda: _locks_check(destination, thresholds)),
                ("workprocesses", lambda: _workprocess_checks(destination, thresholds)),
            ]
        )
        return plan
    plan.extend(
        [
            ("dumps_24h", lambda: _dumps_check(destination, thresholds)),
            ("locks_total", lambda: _locks_check(destination, thresholds)),
            ("workprocesses", lambda: _workprocess_checks(destination, thresholds)),
            ("updates", lambda: _update_checks(destination, thresholds)),
            ("trfc_pending", lambda: _trfc_check(destination, thresholds)),
            ("jobs_aborted_24h", lambda: _jobs_aborted_check(destination, thresholds)),
        ]
    )
    if profile == "deep":
        plan.extend(
            [
                ("active_users", lambda: _active_users_check(destination)),
                ("clients_t000", lambda: _t000_check(destination)),
                ("servers", lambda: _server_list_check(destination)),
                ("snap_sample", lambda: _snap_size_check(destination)),
                ("syslog_sample", lambda: _syslog_size_check(destination)),
            ]
        )
    return plan


def _global_verdict(checks: list[dict[str, Any]]) -> Literal["ok", "warn", "crit", "unknown"]:
    statuses = [str(check.get("status", "unknown")) for check in checks]
    if statuses and all(status == "unknown" for status in statuses):
        return "unknown"
    if "crit" in statuses:
        return "crit"
    if "warn" in statuses:
        return "warn"
    if any(status == "unknown" for status in statuses):
        return "warn"
    return "ok"


def _summary(destination: str, verdict: str, checks: list[dict[str, Any]]) -> str:
    counts = {status: sum(1 for check in checks if check.get("status") == status) for status in ("ok", "warn", "crit", "unknown")}
    problematic = [check["name"] for check in checks if check.get("status") in {"warn", "crit", "unknown"}]
    if verdict == "ok":
        return f"{destination}: health check OK ({counts['ok']} checks en verde)."
    return f"{destination}: verdict={verdict}; crit={counts['crit']}, warn={counts['warn']}, unknown={counts['unknown']}. Revisar: {', '.join(problematic[:8])}."


def _run_plan(plan: list[tuple[str, Callable[[], dict[str, Any] | list[dict[str, Any]]]]], timeout_seconds: float) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    start = perf_counter()
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="sapmcp-health")
    futures: dict[concurrent.futures.Future[dict[str, Any] | list[dict[str, Any]]], str] = {executor.submit(fn): name for name, fn in plan}
    try:
        pending = set(futures)
        while pending:
            remaining = timeout_seconds - (perf_counter() - start)
            if remaining <= 0:
                break
            done, pending = concurrent.futures.wait(pending, timeout=remaining, return_when=concurrent.futures.FIRST_COMPLETED)
            for future in done:
                name = futures[future]
                try:
                    checks.extend(_flatten(future.result()))
                except Exception as exc:
                    checks.append(_check(name, "unknown", None, duration_ms=(perf_counter() - start) * 1000, error=str(exc)))
        for future in pending:
            future.cancel()
            checks.append(_check(futures[future], "unknown", None, duration_ms=timeout_seconds * 1000, error="timeout"))
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    order = {name: index for index, (name, _) in enumerate(plan)}
    checks.sort(key=lambda check: order.get(str(check.get("name", "")), len(order)))
    return checks


@audited("sap_health_check")
def sap_health_check(destination: str | None = None, profile: HealthProfile = "standard") -> dict[str, Any]:
    """Run a SAP Basis health check dashboard with configurable thresholds."""
    if profile not in {"quick", "standard", "deep"}:
        raise ValueError("profile debe ser 'quick', 'standard' o 'deep'")
    config = SapConnectionConfig.from_destination(destination)
    started_at = datetime.now(timezone.utc).isoformat()
    start = perf_counter()
    thresholds = _thresholds()
    checks = _run_plan(_check_plan(profile, config.destination, thresholds), PROFILE_TIMEOUTS[profile])
    duration_ms = round((perf_counter() - start) * 1000, 3)
    verdict = _global_verdict(checks)
    return {
        "destination": config.destination,
        "sid": config.params.get("R3NAME") or os.getenv("SAP_SID") or os.getenv("SAP_SYSTEM_ID") or config.params.get("ASHOST"),
        "mandt": config.params.get("CLIENT"),
        "profile": profile,
        "verdict": verdict,
        "started_at": started_at,
        "duration_ms": duration_ms,
        "checks": checks,
        "summary": _summary(config.destination, verdict, checks),
    }
