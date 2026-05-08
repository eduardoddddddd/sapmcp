from __future__ import annotations

import logging
import sys
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from . import _connector
from .basis import (
    sap_get_jobs,
    sap_get_locks,
    sap_get_rfc_queue,
    sap_get_short_dumps,
    sap_get_syslog,
    sap_get_update_requests,
    sap_get_user_audit,
    sap_get_workprocesses,
)
from . import prompts as prompt_templates
from .audit import audited, tail_audit
from .config import SafetyPolicy, SapConnectionConfig, list_destinations, runtime_status
from .health import sap_health_check
from .read_table import build_rfc_read_table_request
from .resources import (
    describe_rfc_interface,
    get_destinations,
    get_function_interface,
    get_policy_allowlist,
    get_system_info,
    get_table_schema,
    invalidate_cache,
    search_rfc_catalog,
)
from .snapshot import search_snapshot, snapshot_resource

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

mcp = FastMCP("sapmcp")


def _policy() -> SafetyPolicy:
    return SafetyPolicy.from_env()


def _limit_rows(rows: list[dict[str, Any]], max_rows: int) -> list[dict[str, Any]]:
    return rows[: max(0, max_rows)]


@mcp.resource(
    "sap://system/info",
    name="SAP system info",
    description="Cached STFC_CONNECTION ping plus sanitized SAP connection info.",
    mime_type="application/json",
)
def sap_resource_system_info() -> dict[str, Any]:
    return get_system_info()


@mcp.resource(
    "sap://{destination}/system/info",
    name="SAP system info by destination",
    description="Cached STFC_CONNECTION ping plus sanitized SAP connection info for a named destination.",
    mime_type="application/json",
)
def sap_resource_system_info_destination(destination: str) -> dict[str, Any]:
    return get_system_info(destination)


@mcp.resource(
    "sap://policy/allowlist",
    name="SAP safety policy",
    description="Cached read-only/dangerous RFC patterns and active allowlist.",
    mime_type="application/json",
)
def sap_resource_policy_allowlist() -> dict[str, Any]:
    return get_policy_allowlist()


@mcp.resource(
    "sap://{destination}/policy/allowlist",
    name="SAP safety policy by destination",
    description="Cached read-only/dangerous RFC patterns and active allowlist for a named destination.",
    mime_type="application/json",
)
def sap_resource_policy_allowlist_destination(destination: str) -> dict[str, Any]:
    return get_policy_allowlist(destination)


@mcp.resource(
    "sap://function/{name}/interface",
    name="SAP RFC function interface",
    description="Cached RFC_GET_FUNCTION_INTERFACE result for a function module.",
    mime_type="application/json",
)
def sap_resource_function_interface(name: str) -> dict[str, Any]:
    return get_function_interface(name)


@mcp.resource(
    "sap://{destination}/function/{name}/interface",
    name="SAP RFC function interface by destination",
    description="Cached RFC_GET_FUNCTION_INTERFACE result for a function module in a named destination.",
    mime_type="application/json",
)
def sap_resource_function_interface_destination(destination: str, name: str) -> dict[str, Any]:
    return get_function_interface(name, destination)


@mcp.resource(
    "sap://table/{name}/schema",
    name="SAP table schema",
    description="Cached DDIF_FIELDINFO_GET schema for a table/view.",
    mime_type="application/json",
)
def sap_resource_table_schema(name: str) -> dict[str, Any]:
    return get_table_schema(name)


@mcp.resource(
    "sap://{destination}/table/{name}/schema",
    name="SAP table schema by destination",
    description="Cached DDIF_FIELDINFO_GET schema for a table/view in a named destination.",
    mime_type="application/json",
)
def sap_resource_table_schema_destination(destination: str, name: str) -> dict[str, Any]:
    return get_table_schema(name, destination)


@mcp.resource(
    "sap://catalog/rfc?prefix={prefix}",
    name="SAP RFC catalog search",
    description="Cached TFDIR prefix search for RFC function modules.",
    mime_type="application/json",
)
def sap_resource_rfc_catalog(prefix: str) -> dict[str, Any]:
    return search_rfc_catalog(prefix)


@mcp.resource(
    "sap://{destination}/catalog/rfc?prefix={prefix}",
    name="SAP RFC catalog search by destination",
    description="Cached TFDIR prefix search for RFC function modules in a named destination.",
    mime_type="application/json",
)
def sap_resource_rfc_catalog_destination(destination: str, prefix: str) -> dict[str, Any]:
    return search_rfc_catalog(prefix, destination=destination)


@mcp.resource(
    "sap://destinations",
    name="SAP configured destinations",
    description="Configured logical SAP destinations with sanitized parameters.",
    mime_type="application/json",
)
def sap_resource_destinations() -> dict[str, Any]:
    return get_destinations()


@mcp.resource(
    "sap://catalog/snapshot",
    name="SAP offline catalog snapshot",
    description="Serves the local gzip JSON snapshot from ~/.sapmcp if present.",
    mime_type="application/json",
)
def sap_resource_catalog_snapshot() -> dict[str, Any]:
    return snapshot_resource()


@mcp.prompt(
    name="basis_triage_sistema",
    title="Triage Basis de sistema",
    description="Playbook conservador para validar conexión, mandantes e información básica del sistema SAP.",
)
def basis_triage_sistema(sid: str | None = None) -> list[dict[str, str]]:
    return prompt_templates.basis_triage_sistema(sid)


@mcp.prompt(
    name="inspeccionar_pedido_venta",
    title="Inspeccionar pedido de venta",
    description="Playbook read-only para consultar cabecera, posiciones, entregas y estado de un pedido SD.",
)
def inspeccionar_pedido_venta(vbeln: str) -> list[dict[str, str]]:
    return prompt_templates.inspeccionar_pedido_venta(vbeln)


@mcp.prompt(
    name="seguimiento_idoc",
    title="Seguimiento de IDoc",
    description="Playbook read-only para leer un IDoc y su histórico de estados EDIDS.",
)
def seguimiento_idoc(docnum: str) -> list[dict[str, str]]:
    return prompt_templates.seguimiento_idoc(docnum)


@mcp.prompt(
    name="revisar_jobs_largos",
    title="Revisar jobs largos",
    description="Playbook read-only para seleccionar y ordenar jobs largos vía BAPI_XBP_JOB_SELECT.",
)
def revisar_jobs_largos(top_n: int = 10, dias: int = 7) -> list[dict[str, str]]:
    return prompt_templates.revisar_jobs_largos(top_n=top_n, dias=dias)


@mcp.prompt(
    name="informe_sociedad",
    title="Informe por sociedad",
    description="Playbook read-only para conteo BKPF por BLART y top proveedores/clientes.",
)
def informe_sociedad(bukrs: str, gjahr: str) -> list[dict[str, str]]:
    return prompt_templates.informe_sociedad(bukrs, gjahr)


@mcp.prompt(
    name="pre_change_check",
    title="Pre-change check",
    description="Checklist humano obligatorio antes de cualquier llamada confirm_dangerous=true.",
)
def pre_change_check(funcname: str, descripcion: str) -> list[dict[str, str]]:
    return prompt_templates.pre_change_check(funcname, descripcion)


@mcp.prompt(
    name="health_check_response",
    title="Responder health check",
    description="Guía para convertir el JSON de sap_health_check en un resumen operativo en español.",
)
def health_check_response(health_json: dict[str, Any] | str) -> list[dict[str, str]]:
    return prompt_templates.health_check_response(health_json)


@mcp.tool()
def sap_config_status(destination: str | None = None) -> dict[str, Any]:
    """Show SAP MCP runtime configuration without exposing secrets."""
    config = SapConnectionConfig.from_destination(destination)
    status = runtime_status(config, _policy())
    status["destination"] = config.destination
    status["destinations"] = list_destinations()
    return status


@mcp.tool()
def sap_safety_check(function_name: str) -> dict[str, Any]:
    """Classify whether an RFC function is known read-only, dangerous, or allowlisted."""
    return _policy().classify(function_name)


@mcp.tool()
def sap_resources_invalidate(prefix: str | None = None) -> dict[str, Any]:
    """Invalidate the in-memory MCP resources cache, optionally by key prefix."""
    removed = invalidate_cache(prefix)
    return {"ok": True, "prefix": prefix, "removed": removed}


@mcp.tool()
@audited("sap_search_rfc")
def sap_search_rfc(prefix: str, limit: int = 50, destination: str | None = None) -> dict[str, Any]:
    """Search RFC function modules in TFDIR by prefix using the same cache as sap://catalog/rfc."""
    return search_rfc_catalog(prefix, limit=limit, destination=destination)


@mcp.tool()
def sap_audit_tail(n: int = 50) -> list[dict[str, Any]]:
    """Return the last N JSON audit records from today's audit log."""
    return tail_audit(n)


@mcp.tool()
def sap_catalog_search(kind: Literal["rfc", "table"], pattern: str) -> dict[str, Any]:
    """Search RFCs or tables in the offline snapshot without touching SAP."""
    if kind not in {"rfc", "table"}:
        raise ValueError("kind debe ser 'rfc' o 'table'")
    return search_snapshot(kind, pattern)


@mcp.tool()
@audited("sap_ping")
def sap_ping(destination: str | None = None) -> dict[str, Any]:
    """Open a SAP RFC connection and call RFC_PING."""
    policy = _policy()
    policy.assert_allowed("RFC_PING")
    with _connector(destination) as sap:
        sap.call_function("RFC_PING")
    config = SapConnectionConfig.from_destination(destination)
    return {"ok": True, "function": "RFC_PING", "destination": config.destination}


@mcp.tool()
@audited("sap_rfc_call")
def sap_rfc_call(
    function_name: str,
    import_params: dict[str, Any] | None = None,
    input_tables: dict[str, list[dict[str, Any]]] | None = None,
    output_tables: list[str] | None = None,
    table_fields: dict[str, list[str]] | None = None,
    output_params: list[str] | None = None,
    nested_fields: dict[str, dict[str, list[str]]] | None = None,
    confirm_dangerous: bool = False,
    buffer_size: int = 4096,
    destination: str | None = None,
) -> dict[str, Any]:
    """
    Call any RFC-enabled function module with explicit parameters and expected outputs.

    The host LLM should first inspect/choose a function, then call this tool. Safety policy is
    enforced by environment variables, especially SAPMCP_READ_ONLY and SAPMCP_ALLOWED_RFC.
    """
    policy = _policy()
    policy.assert_allowed(function_name, confirm_dangerous=confirm_dangerous)
    with _connector(destination) as sap:
        return sap.call_function(
            function_name,
            import_params=import_params or {},
            input_tables=input_tables or {},
            output_tables=output_tables or [],
            table_fields=table_fields or {},
            output_params=output_params or [],
            nested_fields=nested_fields or {},
            buffer_size=buffer_size,
        )


@mcp.tool()
@audited("sap_describe_rfc")
def sap_describe_rfc(function_name: str, destination: str | None = None) -> dict[str, Any]:
    """
    Try to describe a function module interface using RFC_GET_FUNCTION_INTERFACE.

    Requires the RFC user to be authorized for RFC_GET_FUNCTION_INTERFACE. If unavailable,
    ask BASIS to allow it or provide the function interface manually.
    """
    return describe_rfc_interface(function_name, destination)


@mcp.tool()
@audited("sap_read_table")
def sap_read_table(
    table_name: str,
    fields: list[str] | None = None,
    where: list[str] | None = None,
    rowcount: int | None = None,
    rowskips: int = 0,
    delimiter: str = "\t",
    no_data: bool = False,
    destination: str | None = None,
) -> dict[str, Any]:
    """
    Read a SAP transparent table/view via RFC_READ_TABLE with a row limit.

    `where` is an advanced compatibility escape hatch containing raw SAP OPTION
    strings, e.g. ["BUKRS = '1000'", "AND GJAHR = '2026'"]. Prefer purpose-built
    tools/resources that build safe OPTIONS centrally. The default delimiter is a
    tab to reduce collisions with SAP text values. SAP truncates DATA-WA to 512
    bytes server-side; for wide tables use a purpose-built Z-RFC/BAPI or
    /BODS/RFC_READ_TABLE2 when available.
    """
    policy = _policy()
    policy.assert_allowed("RFC_READ_TABLE")
    max_rows = policy.max_rows
    effective_rowcount = rowcount if rowcount is not None else max_rows
    request = build_rfc_read_table_request(
        table_name,
        fields,
        where,
        rowcount=effective_rowcount,
        rowskips=rowskips,
        delimiter=delimiter,
        no_data=no_data,
        max_rows=max_rows,
        include_field_metadata=True,
        advanced_where=True,
    )

    with _connector(destination) as sap:
        result = sap.call_function(
            "RFC_READ_TABLE",
            **request.call_kwargs(),
        )

    metadata = result.get("FIELDS", [])
    raw_rows = _limit_rows(result.get("DATA", []), request.rowcount)
    selected_fields = [row.get("FIELDNAME", "") for row in metadata] or request.fields
    parsed_rows: list[dict[str, str]] = []
    for raw in raw_rows:
        wa = raw.get("WA", "")
        parts = wa.split(request.delimiter) if request.delimiter else [wa]
        parsed_rows.append({name: parts[index].strip() if index < len(parts) else "" for index, name in enumerate(selected_fields)})

    return {
        "table": request.table_name,
        "destination": SapConnectionConfig.from_destination(destination).destination,
        "rowcount_requested": request.rowcount,
        "rows_returned": len(parsed_rows),
        "fields": metadata,
        "rows": parsed_rows,
        "raw": raw_rows if no_data else None,
    }


@mcp.tool()
def sap_prompt_protocol(prompt: str) -> dict[str, Any]:
    """
    Return an execution protocol for a human SAP prompt.

    The MCP server does not contain its own LLM. The host LLM should use this protocol plus the
    RFC tools to translate human intent into safe SAP actions.
    """
    return {
        "prompt": prompt,
        "protocol": [
            "1. Interpretar intención SAP: objeto de negocio, sistema (ECC/S4), sociedad/mandante, periodo y límites.",
            "2. Preferir BAPIs/RFCs estándar de lectura: BAPI_*_GET*, RFC_READ_TABLE solo para exploración limitada.",
            "3. Ejecutar sap_describe_rfc antes de sap_rfc_call si no se conoce la interfaz exacta.",
            "4. Para cambios en SAP, pedir confirmación humana y usar SAPMCP_ALLOW_DANGEROUS=true + confirm_dangerous=true.",
            "5. Devolver resumen funcional, RFCs usados, filtros, recuentos y riesgos/errores SAP.",
        ],
        "available_tools": ["sap_ping", "sap_describe_rfc", "sap_read_table", "sap_rfc_call", "sap_safety_check"],
    }


mcp.tool()(sap_get_short_dumps)
mcp.tool()(sap_get_syslog)
mcp.tool()(sap_get_locks)
mcp.tool()(sap_get_workprocesses)
mcp.tool()(sap_get_update_requests)
mcp.tool()(sap_get_rfc_queue)
mcp.tool()(sap_get_jobs)
mcp.tool()(sap_get_user_audit)
mcp.tool()(sap_health_check)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
