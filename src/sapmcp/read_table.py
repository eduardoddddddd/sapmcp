from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Literal, Sequence

DEFAULT_DELIMITER = "\t"
MAX_DDIC_NAME_LENGTH = 30
MAX_SAP_USER_LENGTH = 12
MAX_OPTION_TEXT_LENGTH = 512
MAX_LITERAL_LENGTH = 1024
MAX_WHERE_LINES = 100

# DDIC names are usually A-Z/0-9/_ and some SAP namespace objects use /NS/OBJECT.
_DDIC_NAME_RE = re.compile(r"^(?:[A-Z0-9_]+|/[A-Z0-9_]+/[A-Z0-9_]+)$")
_SAP_USER_RE = re.compile(r"^[A-Z0-9_.@/-]+$")
_STATUS_RE = re.compile(r"^[A-Z0-9_-]+$")
_OPTION_FIELD_START_RE = re.compile(
    r"^(?:(?:AND|OR)\s+)?\(*\s*(?:[A-Z0-9_]+|/[A-Z0-9_]+/[A-Z0-9_]+)(?:\s|$|[<>=!])",
    re.IGNORECASE,
)
_LITERAL_TAUTOLOGY_RE = re.compile(r"\b(?:AND|OR)\s+'(?:''|[^'])*'\s*=\s*'(?:''|[^'])*'", re.IGNORECASE)
_SQL_COMMENT_OR_TERMINATOR_RE = re.compile(r"--|/\*|\*/|;")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_ALLOWED_OPERATORS = {"=", "<>", "!=", ">", ">=", "<", "<=", "LIKE"}
_ALLOWED_CONNECTORS = {"AND", "OR"}


@dataclass(frozen=True)
class RfcReadTableRequest:
    """Validated RFC_READ_TABLE call payload.

    ``options`` are the raw OPTION-TEXT strings after validation. ``call_kwargs`` is
    intentionally shaped for ``SapRFCConnector.call_function``.
    """

    table_name: str
    fields: list[str]
    options: list[str]
    rowcount: int
    rowskips: int
    delimiter: str
    no_data: bool
    include_field_metadata: bool

    def call_kwargs(self) -> dict[str, Any]:
        input_tables: dict[str, list[dict[str, Any]]] = {}
        if self.fields:
            input_tables["FIELDS"] = [{"FIELDNAME": field} for field in self.fields]
        if self.options:
            input_tables["OPTIONS"] = [{"TEXT": text} for text in self.options]
        field_metadata = ["FIELDNAME", "OFFSET", "LENGTH", "TYPE", "FIELDTEXT"] if self.include_field_metadata else ["FIELDNAME"]
        return {
            "import_params": {
                "QUERY_TABLE": self.table_name,
                "DELIMITER": self.delimiter,
                "NO_DATA": "X" if self.no_data else "",
                "ROWSKIPS": self.rowskips,
                "ROWCOUNT": self.rowcount,
            },
            "input_tables": input_tables,
            "output_tables": ["FIELDS", "DATA"],
            "table_fields": {"FIELDS": field_metadata, "DATA": ["WA"]},
        }


def _clean_text(value: Any, *, name: str, allow_empty: bool = False) -> str:
    if value is None:
        text = ""
    else:
        text = str(value).strip()
    if not text and not allow_empty:
        raise ValueError(f"{name} no puede estar vacío")
    if _CONTROL_RE.search(text):
        raise ValueError(f"{name} contiene caracteres de control no permitidos")
    return text


def _normalize_ddic_name(value: Any, *, kind: str) -> str:
    text = _clean_text(value, name=kind).upper()
    if len(text) > MAX_DDIC_NAME_LENGTH:
        raise ValueError(f"{kind} excede {MAX_DDIC_NAME_LENGTH} caracteres")
    if not _DDIC_NAME_RE.fullmatch(text):
        raise ValueError(f"{kind} SAP inválido: {text!r}")
    return text


def normalize_table_name(table_name: Any) -> str:
    """Normalize and validate a SAP DDIC table/view name for RFC_READ_TABLE."""

    return _normalize_ddic_name(table_name, kind="table_name")


def normalize_field_name(field_name: Any) -> str:
    """Normalize and validate a SAP DDIC field name for RFC_READ_TABLE."""

    return _normalize_ddic_name(field_name, kind="field_name")


def normalize_field_names(fields: Iterable[Any] | None) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for field in fields or []:
        name = normalize_field_name(field)
        if name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def normalize_sap_user(user: Any, *, required: bool = False) -> str:
    """Normalize a classic SAP user name (BNAME/XUBNAME) and reject SQL-like payloads."""

    text = _clean_text(user, name="user", allow_empty=not required).upper()
    if not text:
        return ""
    if len(text) > MAX_SAP_USER_LENGTH:
        raise ValueError(f"user SAP excede {MAX_SAP_USER_LENGTH} caracteres")
    if not _SAP_USER_RE.fullmatch(text):
        raise ValueError(f"user SAP inválido: {text!r}")
    return text


def normalize_sap_date(value: Any, *, name: str = "date", required: bool = True) -> str:
    """Validate a SAP date literal in YYYYMMDD format."""

    text = _clean_text(value, name=name, allow_empty=not required)
    if not text:
        return ""
    if not re.fullmatch(r"\d{8}", text):
        raise ValueError(f"{name} debe tener formato YYYYMMDD")
    try:
        datetime.strptime(text, "%Y%m%d")
    except ValueError as exc:
        raise ValueError(f"{name} no es una fecha válida YYYYMMDD") from exc
    return text


def normalize_job_status(status: Any, *, required: bool = False) -> str:
    """Normalize a SAP job/update status token without accepting WHERE fragments."""

    text = _clean_text(status, name="status", allow_empty=not required).upper()
    if not text:
        return ""
    if len(text) > 20:
        raise ValueError("status SAP excede 20 caracteres")
    if not _STATUS_RE.fullmatch(text):
        raise ValueError(f"status SAP inválido: {text!r}")
    return text


def sap_literal(value: Any) -> str:
    """Return a single-quoted SAP SQL literal with embedded quotes doubled."""

    text = "" if value is None else str(value)
    if len(text) > MAX_LITERAL_LENGTH:
        raise ValueError(f"literal SAP excede {MAX_LITERAL_LENGTH} caracteres")
    if _CONTROL_RE.search(text) or "\n" in text or "\r" in text:
        raise ValueError("literal SAP contiene caracteres de control no permitidos")
    return "'" + text.replace("'", "''") + "'"


def sap_option(field: Any, operator: str, value: Any, *, connector: Literal["AND", "OR"] | None = None) -> str:
    """Build one safe RFC_READ_TABLE OPTION line for a field/literal comparison."""

    field_name = normalize_field_name(field)
    op = str(operator).strip().upper()
    if op not in _ALLOWED_OPERATORS:
        raise ValueError(f"operador RFC_READ_TABLE no permitido: {operator!r}")
    prefix = ""
    if connector is not None:
        conn = str(connector).strip().upper()
        if conn not in _ALLOWED_CONNECTORS:
            raise ValueError(f"conector RFC_READ_TABLE no permitido: {connector!r}")
        prefix = f"{conn} "
    return f"{prefix}{field_name} {op} {sap_literal(value)}"


def sap_eq(field: Any, value: Any, *, connector: Literal["AND", "OR"] | None = None) -> str:
    return sap_option(field, "=", value, connector=connector)


def sap_ge(field: Any, value: Any, *, connector: Literal["AND", "OR"] | None = None) -> str:
    return sap_option(field, ">=", value, connector=connector)


def sap_le(field: Any, value: Any, *, connector: Literal["AND", "OR"] | None = None) -> str:
    return sap_option(field, "<=", value, connector=connector)


def sap_like_prefix(field: Any, prefix: Any, *, connector: Literal["AND", "OR"] | None = None) -> str:
    return sap_option(field, "LIKE", f"{'' if prefix is None else str(prefix).strip().upper()}%", connector=connector)


def validate_option_text(text: Any, *, advanced: bool = False) -> str:
    """Validate one RFC_READ_TABLE OPTION line.

    Internal code should prefer ``sap_option``/``sap_eq``/``sap_like_prefix``. The
    generic ``sap_read_table(where=...)`` uses this in advanced mode so legacy SAP
    WHERE snippets continue to work while obvious injection probes and malformed
    option rows are rejected before reaching SAP.
    """

    option = _clean_text(text, name="RFC_READ_TABLE option")
    if len(option) > MAX_OPTION_TEXT_LENGTH:
        raise ValueError(f"RFC_READ_TABLE option excede {MAX_OPTION_TEXT_LENGTH} caracteres")
    if "\n" in option or "\r" in option:
        raise ValueError("RFC_READ_TABLE option no puede contener saltos de línea")
    if _SQL_COMMENT_OR_TERMINATOR_RE.search(option):
        raise ValueError("RFC_READ_TABLE option contiene comentario o terminador SQL no permitido")
    if option.count("'") % 2 != 0:
        raise ValueError("RFC_READ_TABLE option contiene comillas desbalanceadas")
    if not _OPTION_FIELD_START_RE.match(option):
        raise ValueError("RFC_READ_TABLE option debe empezar por un campo SAP válido")
    if advanced and _LITERAL_TAUTOLOGY_RE.search(option):
        raise ValueError("RFC_READ_TABLE option contiene comparación literal sospechosa")
    return option


def validate_where_options(where: Sequence[Any] | None, *, advanced: bool = False) -> list[str]:
    if not where:
        return []
    if len(where) > MAX_WHERE_LINES:
        raise ValueError(f"RFC_READ_TABLE where excede {MAX_WHERE_LINES} líneas")
    return [validate_option_text(text, advanced=advanced) for text in where]


def build_safe_options(*conditions: Any) -> list[dict[str, str]]:
    """Build RFC_READ_TABLE OPTIONS rows from already generated safe conditions."""

    return [{"TEXT": validate_option_text(condition)} for condition in conditions if condition not in (None, "")]


def normalize_delimiter(delimiter: Any) -> str:
    text = "" if delimiter is None else str(delimiter)
    if len(text) > 1:
        raise ValueError("delimiter debe ser vacío o un único carácter")
    if text in {"\n", "\r"} or (_CONTROL_RE.search(text) and text != "\t"):
        raise ValueError("delimiter contiene caracteres de control no permitidos")
    return text


def normalize_non_negative_int(value: Any, *, name: str, default: int | None = None, max_value: int | None = None) -> int:
    raw = default if value is None else value
    if raw is None:
        raise ValueError(f"{name} no puede ser None sin valor por defecto")
    try:
        number = int(str(raw))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} debe ser entero") from exc
    if number < 0:
        raise ValueError(f"{name} debe ser >= 0")
    if max_value is not None:
        number = min(number, int(max_value))
    return number


def build_rfc_read_table_request(
    table_name: Any,
    fields: Iterable[Any] | None = None,
    where: Sequence[Any] | None = None,
    *,
    rowcount: Any = 200,
    rowskips: Any = 0,
    delimiter: Any = DEFAULT_DELIMITER,
    no_data: bool = False,
    max_rows: int | None = None,
    include_field_metadata: bool = True,
    advanced_where: bool = False,
) -> RfcReadTableRequest:
    """Create a validated RFC_READ_TABLE request payload.

    ``advanced_where=True`` is reserved for the public generic tool. Internal Basis
    and resource helpers should build ``where`` with ``sap_option`` helpers instead
    of accepting arbitrary WHERE text.
    """

    normalized_table = normalize_table_name(table_name)
    normalized_fields = normalize_field_names(fields)
    normalized_options = validate_where_options(where, advanced=advanced_where)
    normalized_rowcount = normalize_non_negative_int(rowcount, name="rowcount", default=0, max_value=max_rows)
    normalized_rowskips = normalize_non_negative_int(rowskips, name="rowskips", default=0)
    normalized_delimiter = normalize_delimiter(delimiter)
    return RfcReadTableRequest(
        table_name=normalized_table,
        fields=normalized_fields,
        options=normalized_options,
        rowcount=normalized_rowcount,
        rowskips=normalized_rowskips,
        delimiter=normalized_delimiter,
        no_data=bool(no_data),
        include_field_metadata=include_field_metadata,
    )
