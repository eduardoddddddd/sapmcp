from __future__ import annotations

import copy
import threading
import time
from ctypes import byref, c_uint
from typing import Any, Callable, TypeVar

from . import _connector
from .config import DANGEROUS_PATTERNS, READ_ONLY_PATTERNS, SafetyPolicy, SapConnectionConfig, list_destinations
from .read_table import build_rfc_read_table_request, normalize_table_name, sap_like_prefix
from .sap_rfc import SapRFCConnector

T = TypeVar("T")

CacheValue = tuple[Any, float | None]
_CACHE: dict[str, CacheValue] = {}
_CACHE_LOCK = threading.Lock()

TTL_SYSTEM_INFO = 60
TTL_FUNCTION_INTERFACE = 600
TTL_TABLE_SCHEMA = 600
TTL_RFC_CATALOG = 300
TTL_INFINITE: float | None = None


def invalidate_cache(prefix: str | None = None) -> int:
    """Clear all resource cache entries, or only entries whose key starts with prefix."""
    with _CACHE_LOCK:
        if prefix is None:
            count = len(_CACHE)
            _CACHE.clear()
            return count
        keys = [key for key in _CACHE if key.startswith(prefix) or f"/{prefix}" in key]
        for key in keys:
            del _CACHE[key]
        return len(keys)


def _cache_get_or_load(key: str, ttl_seconds: float | None, loader: Callable[[], T]) -> T:
    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached is not None:
            value, expires_at = cached
            if expires_at is None or expires_at > now:
                return copy.deepcopy(value)
            del _CACHE[key]

    value = loader()
    expires_at = None if ttl_seconds is None else now + ttl_seconds
    with _CACHE_LOCK:
        _CACHE[key] = (copy.deepcopy(value), expires_at)
    return copy.deepcopy(value)


def _policy() -> SafetyPolicy:
    return SafetyPolicy.from_env()


def _safe_config(config: SapConnectionConfig) -> dict[str, Any]:
    # Do not expose PASSWD or SDK filesystem paths in resources.
    return {key: value for key, value in config.sanitized().items() if key != "PASSWD"}


def _destination_config(destination: str | None) -> SapConnectionConfig:
    return SapConnectionConfig.from_destination(destination)


def _destination_name(destination: str | None) -> str:
    return _destination_config(destination).destination


def _ns(destination: str | None) -> str:
    return f"destination/{_destination_name(destination)}"


def _resource_uri(destination: str | None, suffix: str) -> str:
    if _destination_name(destination) == "default":
        return f"sap://{suffix}"
    return f"sap://{_destination_name(destination)}/{suffix}"


def _sdk_version(sap: SapRFCConnector) -> str | None:
    lib = getattr(sap, "sap_lib", None)
    if lib is None or not hasattr(lib, "RfcGetVersion"):
        return None
    try:
        major = c_uint()
        minor = c_uint()
        patch = c_uint()
        lib.RfcGetVersion(byref(major), byref(minor), byref(patch))
        return f"{major.value}.{minor.value}.{patch.value}"
    except Exception:
        return None


def get_destinations() -> dict[str, Any]:
    """Cached `sap://destinations` payload."""

    def load() -> dict[str, Any]:
        destinations: list[dict[str, Any]] = []
        for name in list_destinations():
            try:
                config = SapConnectionConfig.from_destination(name)
                destinations.append(
                    {
                        "name": name,
                        "sap_params": _safe_config(config),
                    }
                )
            except Exception as exc:
                destinations.append({"name": name, "error": str(exc)})
        return {
            "uri": "sap://destinations",
            "ttl_seconds": None,
            "destinations": destinations,
        }

    return _cache_get_or_load("destinations", TTL_INFINITE, load)


def get_system_info(destination: str | None = None) -> dict[str, Any]:
    """Cached `sap://system/info` payload."""

    def load() -> dict[str, Any]:
        config = _destination_config(destination)
        with _connector(config.destination) as sap:
            stfc = sap.call_function(
                "STFC_CONNECTION",
                import_params={"REQUTEXT": "sapmcp ping"},
                output_params=["ECHOTEXT", "RESPTEXT"],
            )
            sdk_version = _sdk_version(sap)
        return {
            "uri": _resource_uri(config.destination, "system/info"),
            "destination": config.destination,
            "ttl_seconds": TTL_SYSTEM_INFO,
            "sap_params": _safe_config(config),
            "sdk_version": sdk_version,
            "stfc_connection": stfc,
        }

    return _cache_get_or_load(f"{_ns(destination)}/system/info", TTL_SYSTEM_INFO, load)


def get_policy_allowlist(destination: str | None = None) -> dict[str, Any]:
    """Cached `sap://policy/allowlist` payload."""

    def load() -> dict[str, Any]:
        config = _destination_config(destination)
        policy = _policy()
        return {
            "uri": _resource_uri(config.destination, "policy/allowlist"),
            "destination": config.destination,
            "ttl_seconds": None,
            "policy": {
                "read_only": policy.read_only,
                "allow_dangerous": policy.allow_dangerous,
                "allowed_rfc": policy.allowed_rfc,
                "max_rows": policy.max_rows,
            },
            "read_only_patterns": READ_ONLY_PATTERNS,
            "dangerous_patterns": DANGEROUS_PATTERNS,
            "active_allowlist": policy.allowed_rfc,
        }

    return _cache_get_or_load(f"{_ns(destination)}/policy/allowlist", TTL_INFINITE, load)


def describe_rfc_interface(function_name: str, destination: str | None = None) -> dict[str, Any]:
    """Call RFC_GET_FUNCTION_INTERFACE. Shared by tool and resource."""
    _policy().assert_allowed("RFC_GET_FUNCTION_INTERFACE")
    config = _destination_config(destination)
    with _connector(config.destination) as sap:
        result = sap.call_function(
            "RFC_GET_FUNCTION_INTERFACE",
            import_params={"FUNCNAME": function_name.strip().upper()},
            # Some SAP releases expose only PARAMS in RFC_GET_FUNCTION_INTERFACE.
            # Requesting a non-existent EXCEPTION_LIST table makes the low-level SDK
            # return INVALID_PARAMETER, so keep the portable path to PARAMS and add
            # an empty EXCEPTION_LIST for a stable response shape.
            output_tables=["PARAMS"],
            table_fields={
                "PARAMS": [
                    "PARAMETER",
                    "PARAMCLASS",
                    "TABNAME",
                    "FIELDNAME",
                    "EXID",
                    "POSITION",
                    "OFFSET",
                    "INTLENGTH",
                    "DECIMALS",
                    "DEFAULT",
                    "PARAMTEXT",
                    "OPTIONAL",
                ],
            },
        )
    result.setdefault("EXCEPTION_LIST", [])
    return result


def get_function_interface(name: str, destination: str | None = None) -> dict[str, Any]:
    """Cached `sap://function/{name}/interface` payload."""
    function_name = name.strip().upper()
    config = _destination_config(destination)
    return _cache_get_or_load(
        f"{_ns(config.destination)}/function/{function_name}/interface",
        TTL_FUNCTION_INTERFACE,
        lambda: {
            "uri": _resource_uri(config.destination, f"function/{function_name}/interface"),
            "destination": config.destination,
            "function": function_name,
            "ttl_seconds": TTL_FUNCTION_INTERFACE,
            "interface": describe_rfc_interface(function_name, config.destination),
        },
    )


def _schema_fields(ddif_result: dict[str, Any]) -> list[dict[str, Any]]:
    rows = ddif_result.get("DFIES_TAB", [])
    fields: list[dict[str, Any]] = []
    for row in rows:
        fields.append(
            {
                "field": row.get("FIELDNAME", ""),
                "type": row.get("DATATYPE") or row.get("INTTYPE") or row.get("EXID", ""),
                "inttype": row.get("INTTYPE", ""),
                "length": row.get("LENG") or row.get("INTLEN", ""),
                "int_length": row.get("INTLEN", ""),
                "decimals": row.get("DECIMALS", ""),
                "position": row.get("POSITION") or row.get("POSITION", ""),
                "key": str(row.get("KEYFLAG", "")).upper() == "X",
                "text": row.get("FIELDTEXT", ""),
                "rollname": row.get("ROLLNAME", ""),
            }
        )
    return fields


def get_table_schema(name: str, destination: str | None = None) -> dict[str, Any]:
    """Cached `sap://table/{name}/schema` payload."""
    table_name = normalize_table_name(name)
    config = _destination_config(destination)

    def load() -> dict[str, Any]:
        _policy().assert_allowed("DDIF_FIELDINFO_GET")
        with _connector(config.destination) as sap:
            result = sap.call_function(
                "DDIF_FIELDINFO_GET",
                import_params={"TABNAME": table_name, "LANGU": "E"},
                output_tables=["DFIES_TAB"],
                table_fields={
                    "DFIES_TAB": [
                        "FIELDNAME",
                        "POSITION",
                        "KEYFLAG",
                        "INTTYPE",
                        "DATATYPE",
                        "LENG",
                        "INTLEN",
                        "DECIMALS",
                        "FIELDTEXT",
                        "ROLLNAME",
                    ]
                },
            )
        return {
            "uri": _resource_uri(config.destination, f"table/{table_name}/schema"),
            "destination": config.destination,
            "table": table_name,
            "ttl_seconds": TTL_TABLE_SCHEMA,
            "fields": _schema_fields(result),
            "raw": result,
        }

    return _cache_get_or_load(f"{_ns(config.destination)}/table/{table_name}/schema", TTL_TABLE_SCHEMA, load)


def _parse_read_table_rows(result: dict[str, Any]) -> list[dict[str, str]]:
    metadata = result.get("FIELDS", [])
    selected_fields = [row.get("FIELDNAME", "") for row in metadata]
    rows: list[dict[str, str]] = []
    for raw in result.get("DATA", []):
        wa = raw.get("WA", "")
        parts = wa.split("\t")
        rows.append({name: parts[index].strip() if index < len(parts) else "" for index, name in enumerate(selected_fields)})
    return rows


def search_rfc_catalog(prefix: str, limit: int | None = None, destination: str | None = None) -> dict[str, Any]:
    """Cached `sap://catalog/rfc?prefix=...` payload."""
    normalized_prefix = prefix.strip().upper()
    config = _destination_config(destination)
    policy = _policy()
    effective_limit = policy.max_rows if limit is None else min(max(0, int(limit)), policy.max_rows)
    request = build_rfc_read_table_request(
        "TFDIR",
        ["FUNCNAME", "FMODE"],
        [sap_like_prefix("FUNCNAME", normalized_prefix)],
        rowcount=effective_limit,
        rowskips=0,
        delimiter="\t",
        include_field_metadata=True,
    )
    cache_key = f"{_ns(config.destination)}/catalog/rfc?prefix={normalized_prefix}&limit={effective_limit}"

    def load() -> dict[str, Any]:
        policy.assert_allowed("RFC_READ_TABLE")
        with _connector(config.destination) as sap:
            result = sap.call_function(
                "RFC_READ_TABLE",
                **request.call_kwargs(),
            )
        rows = _parse_read_table_rows(result)[:effective_limit]
        return {
            "uri": _resource_uri(config.destination, f"catalog/rfc?prefix={normalized_prefix}"),
            "destination": config.destination,
            "prefix": normalized_prefix,
            "ttl_seconds": TTL_RFC_CATALOG,
            "limit": effective_limit,
            "rows_returned": len(rows),
            "functions": [row.get("FUNCNAME", "") for row in rows if row.get("FUNCNAME")],
            "rows": rows,
        }

    return _cache_get_or_load(cache_key, TTL_RFC_CATALOG, load)
