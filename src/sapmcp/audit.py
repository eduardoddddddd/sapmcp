from __future__ import annotations

import functools
import hashlib
import inspect
import json
import os
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, TypeVar

try:
    import fcntl
except ImportError:  # pragma: no cover - fcntl is available on macOS/Linux
    fcntl = None  # type: ignore[assignment]

from .config import DEFAULT_DESTINATION_NAME, SafetyPolicy, SapConnectionConfig
from .sap_rfc import SapRFCError

F = TypeVar("F", bound=Callable[..., Any])
SENSITIVE_KEYS = {"pass", "passwd", "password", "sap_pass", "sap_password", "secret", "token"}


def sapmcp_home() -> Path:
    return Path(os.getenv("SAPMCP_HOME", "~/.sapmcp")).expanduser()


def audit_log_path(day: datetime | None = None) -> Path:
    day = day or datetime.now(timezone.utc)
    return sapmcp_home() / f"audit-{day.strftime('%Y%m%d')}.jsonl"


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key).lower()
            if any(sensitive in key_text for sensitive in SENSITIVE_KEYS):
                continue
            redacted[str(key)] = _redact(item)
        return redacted
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return [_redact(item) for item in value]
    return value


def params_hash(payload: dict[str, Any]) -> str:
    sanitized = _redact(payload)
    encoded = json.dumps(sanitized, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _function_from_params(tool_name: str, payload: dict[str, Any]) -> str | None:
    if payload.get("function_name"):
        return str(payload["function_name"]).strip().upper()
    if payload.get("funcname"):
        return str(payload["funcname"]).strip().upper()
    if tool_name == "sap_ping":
        return "RFC_PING"
    if tool_name in {"sap_read_table", "sap_search_rfc"}:
        return "RFC_READ_TABLE"
    if tool_name == "sap_describe_rfc":
        return "RFC_GET_FUNCTION_INTERFACE"
    basis_functions = {
        "sap_get_short_dumps": "RFC_GET_SHORT_DUMP_LIST",
        "sap_get_syslog": "RSLG_READ_SYSLOG",
        "sap_get_locks": "ENQUEUE_READ",
        "sap_get_workprocesses": "TH_WPINFO",
        "sap_get_update_requests": "BAPI_UPDREQUEST_GETLIST",
        "sap_get_rfc_queue": "RFC_READ_TABLE",
        "sap_get_jobs": "BAPI_XBP_JOB_SELECT",
        "sap_get_user_audit": "BAPI_USER_GET_DETAIL",
        "sap_health_check": "STFC_CONNECTION",
    }
    if tool_name in basis_functions:
        return basis_functions[tool_name]
    return None


def _audit_context(function_name: str | None, payload: dict[str, Any]) -> dict[str, Any]:
    requested_destination = payload.get("destination")
    try:
        config = SapConnectionConfig.from_destination(str(requested_destination) if requested_destination not in (None, "") else None)
        params = config.params
    except Exception:
        config = None
        params = {}
    dangerous = False
    if function_name:
        try:
            dangerous = bool(SafetyPolicy.from_env().classify(function_name).get("dangerous"))
        except Exception:
            dangerous = False
    return {
        "destination": config.destination if config is not None else (str(requested_destination) if requested_destination else DEFAULT_DESTINATION_NAME),
        "sid": params.get("R3NAME") or os.getenv("SAP_SID") or os.getenv("SAP_SYSTEM_ID") or params.get("ASHOST"),
        "mandt": params.get("CLIENT"),
        "user": params.get("USER"),
        "dangerous": dangerous,
        "confirmed": bool(payload.get("confirm_dangerous", False)),
    }


def _redact_text(text: str | None) -> str | None:
    if text is None:
        return None
    redacted = text
    for env_name, secret in os.environ.items():
        key = env_name.lower()
        if any(sensitive in key for sensitive in SENSITIVE_KEYS) and secret:
            redacted = redacted.replace(secret, "********")
    redacted = re.sub(r"(?i)(pass(word)?|passwd|token|secret)\s*[:=]\s*\S+", r"\1=********", redacted)
    return redacted


def _error_info(exc: BaseException) -> tuple[int, str | None, str | None]:
    if isinstance(exc, SapRFCError):
        return int(exc.code), exc.key or None, _redact_text(exc.message or str(exc))
    return 1, exc.__class__.__name__, _redact_text(str(exc))


@contextmanager
def _exclusive_lock(fh: Any):
    if fcntl is None:
        yield
        return
    fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
    try:
        yield
    finally:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def _write_record(record: dict[str, Any]) -> None:
    path = audit_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        with _exclusive_lock(fh):
            fh.write(json.dumps(record, sort_keys=True, ensure_ascii=False, default=str) + "\n")
            fh.flush()
            os.fsync(fh.fileno())


def audited(tool_name: str) -> Callable[[F], F]:
    """Audit a FastMCP tool invocation to a daily JSONL file."""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                bound = inspect.signature(func).bind_partial(*args, **kwargs)
                payload = dict(bound.arguments)
            except Exception:
                payload = dict(kwargs)
                if args:
                    payload["_args"] = list(args)
            function_name = _function_from_params(tool_name, payload)
            context = _audit_context(function_name, payload)
            start = perf_counter()
            rc = 0
            error_key: str | None = None
            error_message: str | None = None
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                rc, error_key, error_message = _error_info(exc)
                raise
            finally:
                duration_ms = round((perf_counter() - start) * 1000, 3)
                record = {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "tool": tool_name,
                    "function": function_name,
                    "params_hash": params_hash(payload),
                    "rc": rc,
                    "duration_ms": duration_ms,
                    "destination": context["destination"],
                    "sid": context["sid"],
                    "mandt": context["mandt"],
                    "user": context["user"],
                    "dangerous": context["dangerous"],
                    "confirmed": context["confirmed"],
                    "error_key": error_key,
                    "error_message": error_message,
                }
                _write_record(record)

        return wrapper  # type: ignore[return-value]

    return decorator


def tail_audit(n: int = 50) -> list[dict[str, Any]]:
    path = audit_log_path()
    if not path.exists():
        return []
    limit = max(0, int(n))
    if limit == 0:
        return []
    lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    records: list[dict[str, Any]] = []
    for line in lines:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            records.append({"raw": line})
    return records
