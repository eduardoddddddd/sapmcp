from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Literal

from . import _connector
from .audit import audited
from .config import SafetyPolicy, SapConnectionConfig
from .read_table import (
    build_rfc_read_table_request,
    normalize_job_status,
    normalize_sap_date,
    normalize_sap_user,
    normalize_table_name,
    sap_eq,
    sap_ge,
    sap_le,
)
from .sap_rfc import SapRFCError


def _policy() -> SafetyPolicy:
    return SafetyPolicy.from_env()


def _destination_name(destination: str | None) -> str:
    return SapConnectionConfig.from_destination(destination).destination


def _today() -> str:
    return datetime.now().strftime("%Y%m%d")


def _date_range(date_from: str | None = None, date_to: str | None = None) -> tuple[str, str]:
    start = normalize_sap_date(date_from or _today(), name="date_from")
    end = normalize_sap_date(date_to or start, name="date_to")
    return start, end


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _first(row: dict[str, Any], *names: str, default: str = "") -> str:
    upper = {str(key).upper(): value for key, value in row.items()}
    for name in names:
        value = upper.get(name.upper())
        if value not in (None, ""):
            return _clean(value)
    return default


def _first_int(row: dict[str, Any], *names: str, default: int = 0) -> int:
    raw = _first(row, *names)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _rows(result: dict[str, Any], *names: str) -> list[dict[str, Any]]:
    for name in names:
        value = result.get(name)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    for value in result.values():
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def _function_missing(exc: BaseException) -> bool:
    if not isinstance(exc, SapRFCError):
        return False
    text = f"{exc.operation} {exc.key} {exc.message}".upper()
    return "RFCGETFUNCTIONDESC" in text or "RFC_GET_FUNCTION_DESC" in text or "FUNCTION_NOT_FOUND" in text or "FU_NOT_FOUND" in text or "NOT_FOUND" in text


def _no_data(exc: BaseException) -> bool:
    if not isinstance(exc, SapRFCError):
        return False
    text = f"{exc.key} {exc.message}".upper()
    return "E_WITHOUT_DATA" in text or "NO_DATA" in text


def _unavailable(function_name: str, exc: BaseException | str) -> dict[str, Any]:
    reason = exc if isinstance(exc, str) else str(exc)
    return {"available": False, "function": function_name, "reason": reason}


def _has_function(sap: Any, function_name: str) -> bool:
    if hasattr(sap, "has_function"):
        try:
            return bool(sap.has_function(function_name))
        except Exception:
            return False
    return True


def _call(sap: Any, function_name: str, **kwargs: Any) -> dict[str, Any]:
    function_name = function_name.strip().upper()
    _policy().assert_allowed(function_name)
    if not _has_function(sap, function_name):
        raise LookupError(f"RFC {function_name} no existe o no está disponible")
    try:
        return sap.call_function(function_name, **kwargs)
    except Exception as exc:
        if _function_missing(exc):
            raise LookupError(str(exc)) from exc
        raise


def _policy_allows(function_name: str) -> tuple[bool, PermissionError | None]:
    try:
        _policy().assert_allowed(function_name)
    except PermissionError as exc:
        return False, exc
    return True, None


def _read_table(sap: Any, table: str, fields: list[str], where: list[str] | None = None, *, rowcount: int = 200, rowskips: int = 0) -> list[dict[str, str]]:
    request = build_rfc_read_table_request(
        table,
        fields,
        where,
        rowcount=rowcount,
        rowskips=rowskips,
        delimiter="\t",
        include_field_metadata=False,
    )
    try:
        result = _call(
            sap,
            "RFC_READ_TABLE",
            **request.call_kwargs(),
        )
    except SapRFCError as exc:
        # RFC_READ_TABLE raises E_WITHOUT_DATA for valid empty selections/tables.
        # Basis smoke tools should report count=0 instead of failing the whole tool.
        if _no_data(exc):
            return []
        raise
    metadata = _rows(result, "FIELDS")
    names = [_first(row, "FIELDNAME") for row in metadata] or request.fields
    parsed: list[dict[str, str]] = []
    for raw in _rows(result, "DATA"):
        parts = _first(raw, "WA").split("\t")
        parsed.append({name.upper(): parts[index].strip() if index < len(parts) else "" for index, name in enumerate(names)})
    return parsed


def _mark_latest(rows: list[dict[str, Any]], group_fields: tuple[str, ...]) -> None:
    latest: dict[tuple[str, ...], tuple[str, str, int]] = {}
    for index, row in enumerate(rows):
        key = tuple(_clean(row.get(field)) for field in group_fields)
        stamp = (_clean(row.get("fecha")), _clean(row.get("hora")), index)
        if key not in latest or stamp > latest[key]:
            latest[key] = stamp
    for index, row in enumerate(rows):
        key = tuple(_clean(row.get(field)) for field in group_fields)
        stamp = (_clean(row.get("fecha")), _clean(row.get("hora")), index)
        explicit = _clean(row.get("last")).upper()
        row["last"] = explicit in {"X", "1", "TRUE", "YES", "Y"} if explicit else stamp == latest.get(key)


def _dump_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "fecha": _first(row, "DATUM", "DATE", "AEDAT", "FECHA"),
        "hora": _first(row, "UZEIT", "TIME", "HORA"),
        "usuario": _first(row, "UNAME", "USER", "USERNAME"),
        "programa": _first(row, "PROG", "PROGRAM", "ABAP_PROGRAM", "REPID"),
        "ahost": _first(row, "AHOST", "HOST", "SERVER"),
        "t100msg": _first(row, "T100MSG", "ERROR", "ERRID", "MESSAGE", "TEXT"),
        "uname": _first(row, "UNAME", "USER", "USERNAME"),
        "last": _first(row, "LAST", "IS_LAST"),
    }


@audited("sap_get_short_dumps")
def sap_get_short_dumps(
    date_from: str | None = None,
    date_to: str | None = None,
    user: str | None = None,
    destination: str | None = None,
) -> dict[str, Any]:
    """Return ABAP short dumps via RFC_GET_SHORT_DUMP_LIST or SNAP fallback."""
    start, end = _date_range(date_from, date_to)
    username = normalize_sap_user(user)
    with _connector(destination) as sap:
        if _has_function(sap, "RFC_GET_SHORT_DUMP_LIST"):
            try:
                result = _call(
                    sap,
                    "RFC_GET_SHORT_DUMP_LIST",
                    import_params={"DATE_FROM": start, "DATE_TO": end, "UNAME": username},
                    output_tables=["DUMPS", "DUMP_LIST", "SNAPLIST", "ET_DUMPS"],
                    table_fields={
                        "DUMPS": ["DATUM", "UZEIT", "UNAME", "PROG", "AHOST", "T100MSG", "LAST"],
                        "DUMP_LIST": ["DATUM", "UZEIT", "UNAME", "PROG", "AHOST", "T100MSG", "LAST"],
                        "SNAPLIST": ["DATUM", "UZEIT", "UNAME", "PROG", "AHOST", "T100MSG", "LAST"],
                        "ET_DUMPS": ["DATUM", "UZEIT", "UNAME", "PROG", "AHOST", "T100MSG", "LAST"],
                    },
                )
                dumps = [_dump_row(row) for row in _rows(result, "DUMPS", "DUMP_LIST", "SNAPLIST", "ET_DUMPS")]
                source = "RFC_GET_SHORT_DUMP_LIST"
            except LookupError:
                dumps = []
                source = "SNAP"
        else:
            dumps = []
            source = "SNAP"
        if source == "SNAP":
            where = [sap_ge("DATUM", start), sap_le("DATUM", end, connector="AND")]
            if username:
                where.append(sap_eq("UNAME", username, connector="AND"))
            try:
                rows = _read_table(sap, "SNAP", ["DATUM", "UZEIT", "UNAME", "PROG", "AHOST", "T100MSG"], where)
            except LookupError as exc:
                return _unavailable("RFC_GET_SHORT_DUMP_LIST/RFC_READ_TABLE(SNAP)", exc)
            dumps = [_dump_row(row) for row in rows]
    if username:
        dumps = [row for row in dumps if row["usuario"].upper() == username]
    _mark_latest(dumps, ("usuario", "programa", "t100msg"))
    dumps.sort(key=lambda row: (row.get("fecha", ""), row.get("hora", "")), reverse=True)
    return {"available": True, "destination": _destination_name(destination), "source": source, "date_from": start, "date_to": end, "dumps": dumps, "count": len(dumps)}


def _syslog_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "fecha": _first(row, "DATUM", "DATE", "MSGDATE"),
        "hora": _first(row, "UZEIT", "TIME", "MSGTIME"),
        "instancia": _first(row, "INSTANCE", "SERVER", "HOST", "AHOST"),
        "usuario": _first(row, "UNAME", "USER", "USERNAME"),
        "mandante": _first(row, "MANDT", "CLIENT"),
        "severity": _first(row, "SEVERITY", "MSGTY", "TYPE", "PRIORITY"),
        "mensaje": _first(row, "MESSAGE", "TEXT", "MSG", "LINE", "MSGTEXT"),
    }


@audited("sap_get_syslog")
def sap_get_syslog(
    date_from: str | None = None,
    date_to: str | None = None,
    severity: str | None = None,
    destination: str | None = None,
) -> dict[str, Any]:
    """Read SAP syslog using RSLG_READ_SYSLOG, falling back to BAPI_SYSLOG_READ."""
    start, end = _date_range(date_from, date_to)
    wanted = severity.upper().strip() if severity else None
    with _connector(destination) as sap:
        chosen = None
        for candidate in ("RSLG_READ_SYSLOG", "BAPI_SYSLOG_READ"):
            _policy().assert_allowed(candidate)
            if _has_function(sap, candidate):
                chosen = candidate
                break
        if not chosen:
            return _unavailable("RSLG_READ_SYSLOG/BAPI_SYSLOG_READ", "No hay RFC estándar de syslog disponible")
        try:
            result = _call(
                sap,
                chosen,
                import_params={"DATE_FROM": start, "DATE_TO": end, "SEVERITY": wanted or ""},
                output_tables=["SYSLOG", "ENTRIES", "MESSAGES", "ET_SYSLOG"],
                table_fields={
                    "SYSLOG": ["DATUM", "UZEIT", "INSTANCE", "UNAME", "MANDT", "SEVERITY", "MESSAGE"],
                    "ENTRIES": ["DATUM", "UZEIT", "INSTANCE", "UNAME", "MANDT", "SEVERITY", "MESSAGE"],
                    "MESSAGES": ["DATUM", "UZEIT", "INSTANCE", "UNAME", "MANDT", "SEVERITY", "MESSAGE"],
                    "ET_SYSLOG": ["DATUM", "UZEIT", "INSTANCE", "UNAME", "MANDT", "SEVERITY", "MESSAGE"],
                },
            )
        except LookupError as exc:
            return _unavailable(chosen, exc)
    entries = [_syslog_row(row) for row in _rows(result, "SYSLOG", "ENTRIES", "MESSAGES", "ET_SYSLOG")]
    if wanted:
        entries = [row for row in entries if row["severity"].upper() == wanted]
    return {"available": True, "destination": _destination_name(destination), "source": chosen, "date_from": start, "date_to": end, "entries": entries, "count": len(entries)}


@audited("sap_get_locks")
def sap_get_locks(table: str | None = None, user: str | None = None, destination: str | None = None) -> dict[str, Any]:
    """Read SAP enqueue locks via ENQUEUE_READ."""
    table_name = normalize_table_name(table) if table else ""
    username = normalize_sap_user(user)
    with _connector(destination) as sap:
        try:
            result = _call(
                sap,
                "ENQUEUE_READ",
                import_params={"GNAME": table_name, "GUNAME": username},
                output_tables=["ENQ"],
                table_fields={
                    "ENQ": ["GNAME", "GARG", "GUNAME", "GTARG", "GTCODE", "GTDATE", "GTTIME"],
                },
            )
        except LookupError as exc:
            return _unavailable("ENQUEUE_READ", exc)
    locks = [
        {
            "gname": _first(row, "GNAME"),
            "garg": _first(row, "GARG"),
            "guname": _first(row, "GUNAME"),
            "gtarg": _first(row, "GTARG"),
            "gtcode": _first(row, "GTCODE"),
            "gtdate": _first(row, "GTDATE"),
            "gttime": _first(row, "GTTIME"),
        }
        for row in _rows(result, "ENQ", "LOCKS", "ET_ENQ")
    ]
    if table_name:
        locks = [row for row in locks if row["gname"].upper() == table_name]
    if username:
        locks = [row for row in locks if row["guname"].upper() == username]
    return {"available": True, "destination": _destination_name(destination), "locks": locks, "count": len(locks)}


def _wp_row(row: dict[str, Any], server: str = "") -> dict[str, Any]:
    return {
        "server": server or _first(row, "SERVER", "INSTANCE", "HOST", "WP_SERVER"),
        "numero": _first(row, "WP_NO", "NO", "NUMBER", "WP_INDEX"),
        "tipo": _first(row, "WP_TYP", "TYPE", "WPTYPE"),
        "status": _first(row, "WP_STATUS", "STATUS", "STATE"),
        "usuario": _first(row, "USER", "UNAME", "USERNAME", "WP_BNAME"),
        "mandante": _first(row, "CLIENT", "MANDT", "WP_MANDT"),
        "programa": _first(row, "PROGRAM", "REPORT", "PROG", "WP_REPORT"),
        "tiempo": _first(row, "TIME", "ELTIME", "RUNTIME", "WP_ELTIME"),
        "tabla": _first(row, "TABLE", "TABNAME", "WP_TABLE"),
    }


@audited("sap_get_workprocesses")
def sap_get_workprocesses(server: str | None = None, destination: str | None = None) -> dict[str, Any]:
    """Read SAP work processes via TH_WPINFO, aggregating TH_SERVER_LIST when server is omitted."""
    processes: list[dict[str, Any]] = []
    with _connector(destination) as sap:
        try:
            servers = [server] if server else []
            if not servers:
                result = _call(sap, "TH_SERVER_LIST", output_tables=["LIST"], table_fields={"LIST": ["NAME", "HOST"]})
                servers = [_first(row, "NAME", "SERVER", "HOST") for row in _rows(result, "LIST", "SERVERS") if _first(row, "NAME", "SERVER", "HOST")]
            if not servers:
                servers = [""]
            for srv in servers:
                result = _call(
                    sap,
                    "TH_WPINFO",
                    import_params={"SRVNAME": srv or ""},
                    output_tables=["WPLIST"],
                    table_fields={"WPLIST": ["WP_NO", "WP_TYP", "WP_STATUS", "WP_BNAME", "WP_MANDT", "WP_REPORT", "WP_ELTIME", "WP_TABLE"]},
                )
                processes.extend(_wp_row(row, srv or "") for row in _rows(result, "WPLIST", "WPINFO", "LIST"))
        except LookupError as exc:
            return _unavailable("TH_WPINFO/TH_SERVER_LIST", exc)
    return {"available": True, "destination": _destination_name(destination), "workprocesses": processes, "count": len(processes)}


@audited("sap_get_update_requests")
def sap_get_update_requests(status: str | None = None, user: str | None = None, destination: str | None = None) -> dict[str, Any]:
    """Read update requests via BAPI_UPDREQUEST_GETLIST."""
    wanted = normalize_job_status(status) or None
    username = normalize_sap_user(user)
    with _connector(destination) as sap:
        try:
            result = _call(
                sap,
                "BAPI_UPDREQUEST_GETLIST",
                import_params={"STATUS": wanted or "", "USER": username},
                output_tables=["REQUESTS", "UPDREQUESTS", "MODINFO", "MODULES"],
                table_fields={
                    "REQUESTS": ["USER", "PROGRAM", "DATE", "TIME", "STATUS", "MODULES"],
                    "UPDREQUESTS": ["USER", "PROGRAM", "DATE", "TIME", "STATUS", "MODULES"],
                    "MODINFO": ["USER", "PROGRAM", "DATE", "TIME", "STATUS", "MODULE"],
                    "MODULES": ["USER", "PROGRAM", "DATE", "TIME", "STATUS", "MODULE"],
                },
            )
        except LookupError as exc:
            return _unavailable("BAPI_UPDREQUEST_GETLIST", exc)
    requests = []
    for row in _rows(result, "REQUESTS", "UPDREQUESTS", "MODINFO", "MODULES"):
        item = {
            "usuario": _first(row, "USER", "UNAME"),
            "programa": _first(row, "PROGRAM", "PROG"),
            "fecha": _first(row, "DATE", "DATUM"),
            "hora": _first(row, "TIME", "UZEIT"),
            "status": _first(row, "STATUS", "STATE"),
            "modulos_pendientes": _first_int(row, "MODULES", "PENDING_MODULES", default=1 if _first(row, "MODULE") else 0),
        }
        requests.append(item)
    if wanted:
        requests = [row for row in requests if row["status"].upper() == wanted]
    if username:
        requests = [row for row in requests if row["usuario"].upper() == username]
    return {"available": True, "destination": _destination_name(destination), "requests": requests, "count": len(requests)}


def _queue_table(queue_type: Literal["trfc", "qrfc_out", "qrfc_in"]) -> tuple[str, list[str]]:
    if queue_type == "trfc":
        return "ARFCSSTATE", ["ARFCDEST", "ARFCUSER", "ARFCDATE", "ARFCTIME", "ARFCFNAM", "ARFCSTATE", "ARFCMSG"]
    if queue_type == "qrfc_out":
        return "TRFCQOUT", ["DEST", "UNAME", "QDATE", "QTIME", "FUNCNAME", "QSTATE", "ERRMESS"]
    return "TRFCQIN", ["DEST", "UNAME", "QDATE", "QTIME", "FUNCNAME", "QSTATE", "ERRMESS"]


@audited("sap_get_rfc_queue")
def sap_get_rfc_queue(queue_type: Literal["trfc", "qrfc_out", "qrfc_in"] = "trfc", destination: str | None = None) -> dict[str, Any]:
    """Read pending/error tRFC or qRFC queue entries from standard queue tables."""
    if queue_type not in {"trfc", "qrfc_out", "qrfc_in"}:
        raise ValueError("queue_type debe ser 'trfc', 'qrfc_out' o 'qrfc_in'")
    table, fields = _queue_table(queue_type)
    with _connector(destination) as sap:
        try:
            rows = _read_table(sap, table, fields, rowcount=SafetyPolicy.from_env().max_rows)
        except LookupError as exc:
            return _unavailable("RFC_READ_TABLE", exc)
    entries = []
    for row in rows:
        status = _first(row, "ARFCSTATE", "QSTATE", "STATUS")
        if status.upper() in {"DONE", "CPICERR=0", "OK", "FINISHED", "COMPLETED"}:
            continue
        entries.append(
            {
                "destino": _first(row, "ARFCDEST", "DEST", "DESTINATION"),
                "usuario": _first(row, "ARFCUSER", "UNAME", "USER"),
                "fecha": _first(row, "ARFCDATE", "QDATE", "DATE"),
                "hora": _first(row, "ARFCTIME", "QTIME", "TIME"),
                "funcion": _first(row, "ARFCFNAM", "FUNCNAME", "FUNCTION"),
                "status": status,
                "mensaje": _first(row, "ARFCMSG", "ERRMESS", "MESSAGE"),
            }
        )
    return {"available": True, "destination": _destination_name(destination), "queue_type": queue_type, "entries": entries, "count": len(entries)}


def _job_datetime(row: dict[str, Any], date_names: tuple[str, ...], time_names: tuple[str, ...]) -> str:
    date = _first(row, *date_names)
    time = _first(row, *time_names)
    if not date and not time:
        return ""
    return f"{date}{' ' + time if time else ''}"


def _read_jobs_from_tbtco(sap: Any, since: str, wanted: str | None) -> list[dict[str, str]]:
    where = [sap_ge("SDLSTRTDT", since)]
    if wanted:
        where.append(sap_eq("STATUS", wanted, connector="AND"))
    return _read_table(
        sap,
        "TBTCO",
        ["JOBNAME", "JOBCOUNT", "STATUS", "SDLSTRTDT", "SDLSTRTTM", "ENDDATE", "ENDTIME", "SDLUNAME"],
        where,
        rowcount=SafetyPolicy.from_env().max_rows,
    )


@audited("sap_get_jobs")
def sap_get_jobs(top_n: int = 50, status: str | None = None, since_days: int = 1, destination: str | None = None) -> dict[str, Any]:
    """Read SAP background jobs via BAPI_XBP_JOB_SELECT, with TBTCO fallback.

    In strict allowlist mode the fallback is intentional: if BAPI_XBP_JOB_SELECT
    is not allowed but RFC_READ_TABLE is allowed, sapmcp reads TBTCO instead of
    failing before the fallback path. If neither RFC is allowed, the original
    policy error is preserved.
    """
    wanted = normalize_job_status(status) or None
    since = (datetime.now() - timedelta(days=max(0, int(since_days)))).strftime("%Y%m%d")
    source = "BAPI_XBP_JOB_SELECT"
    with _connector(destination) as sap:
        bapi_allowed, bapi_policy_error = _policy_allows("BAPI_XBP_JOB_SELECT")
        if bapi_allowed:
            try:
                result = _call(
                    sap,
                    "BAPI_XBP_JOB_SELECT",
                    import_params={"EXTERNAL_USER_NAME": SapConnectionConfig.from_destination(destination).params.get("USER", "")},
                    output_tables=["JOB_HEAD"],
                    table_fields={
                        "JOB_HEAD": ["JOBNAME", "JOBCOUNT", "STATUS", "SDLSTRTDT", "SDLSTRTTM", "ENDDATE", "ENDTIME", "SDLUNAME", "STEPCOUNT"],
                    },
                )
            except LookupError as exc:
                rfc_read_allowed, _ = _policy_allows("RFC_READ_TABLE")
                if not rfc_read_allowed:
                    return _unavailable("BAPI_XBP_JOB_SELECT", exc)
                source = "TBTCO"
                rows = _read_jobs_from_tbtco(sap, since, wanted)
                result = {"JOB_HEAD": rows}
            except SapRFCError:
                # Some Basis releases require a structured JOB_SELECT_PARAM import that
                # this lightweight ctypes bridge does not fill yet. Keep the tool useful
                # in read-only mode by falling back to the transparent job header table.
                source = "TBTCO"
                rows = _read_jobs_from_tbtco(sap, since, wanted)
                result = {"JOB_HEAD": rows}
        else:
            rfc_read_allowed, _ = _policy_allows("RFC_READ_TABLE")
            if not rfc_read_allowed:
                if bapi_policy_error is not None:
                    raise bapi_policy_error
                raise PermissionError("RFC BAPI_XBP_JOB_SELECT blocked by policy")
            source = "TBTCO"
            rows = _read_jobs_from_tbtco(sap, since, wanted)
            result = {"JOB_HEAD": rows}
    jobs = []
    for row in _rows(result, "JOB_HEAD", "JOBLIST", "JOBS", "SELECTED_JOBS"):
        item = {
            "jobname": _first(row, "JOBNAME"),
            "jobcount": _first(row, "JOBCOUNT"),
            "status": _first(row, "STATUS", "JOBSTATUS"),
            "runtime": _first(row, "RUNTIME", "DURATION"),
            "start": _job_datetime(row, ("SDLSTRTDT", "STRTDATE", "STARTDATE"), ("SDLSTRTTM", "STRTTIME", "STARTTIME")),
            "end": _job_datetime(row, ("ENDDATE", "END_DATE"), ("ENDTIME", "END_TIME")),
            "user": _first(row, "USERNAME", "USER", "SDLUNAME"),
            "steps": _first_int(row, "STEPS", "STEPCOUNT", default=0),
        }
        jobs.append(item)
    if wanted:
        jobs = [job for job in jobs if job["status"].upper() == wanted]
    jobs.sort(key=lambda job: (job.get("start", ""), job.get("jobname", "")), reverse=True)
    top = max(0, int(top_n))
    return {"available": True, "destination": _destination_name(destination), "source": source, "since": since, "jobs": jobs[:top], "count": len(jobs[:top])}


@audited("sap_get_user_audit")
def sap_get_user_audit(user: str, destination: str | None = None) -> dict[str, Any]:
    """Combine standard BAPIs and USR02 reads for a read-only user audit."""
    username = normalize_sap_user(user, required=True)
    with _connector(destination) as sap:
        try:
            detail = _call(
                sap,
                "BAPI_USER_GET_DETAIL",
                import_params={"USERNAME": username},
                output_tables=["PROFILES", "ACTIVITYGROUPS", "RETURN"],
                table_fields={
                    "PROFILES": ["BAPIPROF", "BAPIPTEXT", "BAPITYPE", "BAPIAKTPS"],
                    "ACTIVITYGROUPS": ["AGR_NAME", "AGR_TEXT", "FROM_DAT", "TO_DAT"],
                    "RETURN": ["TYPE", "MESSAGE"],
                },
            )
        except LookupError as exc:
            return _unavailable("BAPI_USER_GET_DETAIL", exc)
        lockstatus: dict[str, Any] = {}
        if _has_function(sap, "BAPI_USER_LOCK_STATUS"):
            try:
                lockstatus = _call(sap, "BAPI_USER_LOCK_STATUS", import_params={"USERNAME": username}, output_params=["LOCKSTATUS", "WRNG_LOGON", "LOCAL_LOCK", "GLOB_LOCK"])
            except LookupError:
                lockstatus = {}
        try:
            usr02_rows = _read_table(sap, "USR02", ["BNAME", "GLTGV", "GLTGB", "TRDAT", "LTIME", "UFLAG", "LOCNT"], [sap_eq("BNAME", username)], rowcount=1)
        except LookupError as exc:
            return _unavailable("RFC_READ_TABLE(USR02)", exc)
    usr02 = usr02_rows[0] if usr02_rows else {}
    profiles = [_first(row, "BAPIPROF", "PROFILE") for row in _rows(detail, "PROFILES") if _first(row, "BAPIPROF", "PROFILE")]
    roles = [_first(row, "AGR_NAME", "ROLE") for row in _rows(detail, "ACTIVITYGROUPS", "ROLES") if _first(row, "AGR_NAME", "ROLE")]
    address_raw = detail.get("ADDRESS") if isinstance(detail.get("ADDRESS"), dict) else {}
    address = address_raw if isinstance(address_raw, dict) else {"raw": _clean(detail.get("ADDRESS"))}
    fullname = _first(address, "FULLNAME", "FULL_NAME", "NAME", "LASTNAME") if isinstance(address, dict) else ""
    lastlogon = _first(usr02, "TRDAT")
    if _first(usr02, "LTIME"):
        lastlogon = f"{lastlogon} {_first(usr02, 'LTIME')}".strip()
    lock_payload = lockstatus or {"uflag": _first(usr02, "UFLAG")}
    return {
        "available": True,
        "destination": _destination_name(destination),
        "user": username,
        "fullname": fullname,
        "address": address,
        "lockstatus": lock_payload,
        "lastlogon": lastlogon,
        "valid_from": _first(usr02, "GLTGV"),
        "valid_to": _first(usr02, "GLTGB"),
        "profiles": profiles,
        "roles": roles,
        "sap_all": any(profile.upper() == "SAP_ALL" for profile in profiles),
        "failed_logons": _first_int(usr02, "LOCNT", default=0),
    }
