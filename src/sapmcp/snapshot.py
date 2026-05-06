from __future__ import annotations

import argparse
import fnmatch
import gzip
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from .audit import sapmcp_home
from .config import SafetyPolicy, SapConnectionConfig
from .sap_rfc import SapRFCConnector

SNAPSHOT_VERSION = 1
DELIMITER = "\t"

TABLE_SPECS: dict[str, list[str]] = {
    "TFDIR": ["FUNCNAME", "PNAME"],
    "DD02L": ["TABNAME", "TABCLASS"],
    "DD03L": ["TABNAME", "FIELDNAME", "ROLLNAME", "POSITION", "KEYFLAG", "INTTYPE"],
}


def snapshot_sid(config: SapConnectionConfig | None = None) -> str:
    config = config or SapConnectionConfig.from_env()
    raw = config.params.get("R3NAME") or os.getenv("SAP_SID") or os.getenv("SAP_SYSTEM_ID") or config.params.get("ASHOST") or "SAP"
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(raw).upper()).strip("_") or "SAP"


def snapshot_path(sid: str | None = None) -> Path:
    sid = sid or snapshot_sid()
    return sapmcp_home() / f"catalog-{sid}.json.gz"


def find_snapshot_path(sid: str | None = None) -> Path | None:
    if sid:
        path = snapshot_path(sid)
        return path if path.exists() else None
    try:
        preferred = snapshot_path()
        if preferred.exists():
            return preferred
    except Exception:
        pass
    candidates = sorted(sapmcp_home().glob("catalog-*.json.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def _parse_read_table(result: dict[str, Any]) -> list[dict[str, str]]:
    fields = [row.get("FIELDNAME", "") for row in result.get("FIELDS", [])]
    rows: list[dict[str, str]] = []
    for raw in result.get("DATA", []):
        parts = str(raw.get("WA", "")).split(DELIMITER)
        rows.append({name: parts[index].strip() if index < len(parts) else "" for index, name in enumerate(fields)})
    return rows


def read_table_paged(sap: SapRFCConnector, table_name: str, fields: list[str], *, page_size: int = 500, max_pages: int | None = None) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    rowskips = 0
    pages = 0
    while True:
        result = sap.call_function(
            "RFC_READ_TABLE",
            import_params={
                "QUERY_TABLE": table_name,
                "DELIMITER": DELIMITER,
                "NO_DATA": "",
                "ROWSKIPS": rowskips,
                "ROWCOUNT": page_size,
            },
            input_tables={"FIELDS": [{"FIELDNAME": field} for field in fields]},
            output_tables=["FIELDS", "DATA"],
            table_fields={
                "FIELDS": ["FIELDNAME", "OFFSET", "LENGTH", "TYPE", "FIELDTEXT"],
                "DATA": ["WA"],
            },
        )
        page = _parse_read_table(result)
        rows.extend(page)
        pages += 1
        if len(page) < page_size:
            break
        if max_pages is not None and pages >= max_pages:
            break
        rowskips += len(page)
    return rows


def build_snapshot(*, page_size: int | None = None, max_pages: int | None = None, output_path: Path | None = None) -> dict[str, Any]:
    SafetyPolicy.from_env().assert_allowed("RFC_READ_TABLE")
    config = SapConnectionConfig.from_env()
    sid = snapshot_sid(config)
    page_size = page_size or int(os.getenv("SAPMCP_SNAPSHOT_PAGE_SIZE", "500"))
    if max_pages is None and os.getenv("SAPMCP_SNAPSHOT_MAX_PAGES"):
        max_pages = int(os.environ["SAPMCP_SNAPSHOT_MAX_PAGES"])
    with SapRFCConnector(config) as sap:
        tfdir = read_table_paged(sap, "TFDIR", TABLE_SPECS["TFDIR"], page_size=page_size, max_pages=max_pages)
        dd02l = read_table_paged(sap, "DD02L", TABLE_SPECS["DD02L"], page_size=page_size, max_pages=max_pages)
        dd03l = read_table_paged(sap, "DD03L", TABLE_SPECS["DD03L"], page_size=page_size, max_pages=max_pages)
    snapshot = {
        "version": SNAPSHOT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "sid": sid,
        "source": "sapmcp-snapshot",
        "counts": {"rfc": len(tfdir), "tables": len(dd02l), "fields": len(dd03l)},
        "rfc": tfdir,
        "tables": dd02l,
        "fields": dd03l,
    }
    write_snapshot(snapshot, output_path or snapshot_path(sid))
    return snapshot


def write_snapshot(snapshot: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump(snapshot, fh, ensure_ascii=False, sort_keys=True)
    return path


def load_snapshot(path: Path | None = None) -> dict[str, Any] | None:
    path = path or find_snapshot_path()
    if path is None or not path.exists():
        return None
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def snapshot_resource() -> dict[str, Any]:
    path = find_snapshot_path()
    if path is None:
        return {"uri": "sap://catalog/snapshot", "exists": False, "message": "No catalog snapshot found in ~/.sapmcp"}
    data = load_snapshot(path) or {}
    payload = dict(data)
    payload.update({"uri": "sap://catalog/snapshot", "exists": True, "path": str(path)})
    return payload


def _matches(value: str, pattern: str) -> bool:
    value_upper = value.upper()
    pattern_upper = pattern.upper()
    if "*" in pattern_upper or "?" in pattern_upper:
        return fnmatch.fnmatchcase(value_upper, pattern_upper)
    return pattern_upper in value_upper


def search_snapshot(kind: Literal["rfc", "table"], pattern: str, *, limit: int = 100) -> dict[str, Any]:
    data = load_snapshot()
    if data is None:
        return {"kind": kind, "pattern": pattern, "exists": False, "rows_returned": 0, "rows": []}
    normalized_kind = kind.lower()
    if normalized_kind == "rfc":
        source = data.get("rfc", [])
        key = "FUNCNAME"
    elif normalized_kind == "table":
        source = data.get("tables", [])
        key = "TABNAME"
    else:
        raise ValueError("kind debe ser 'rfc' o 'table'")
    rows = [row for row in source if _matches(str(row.get(key, "")), pattern)]
    return {
        "kind": normalized_kind,
        "pattern": pattern,
        "exists": True,
        "snapshot_sid": data.get("sid"),
        "rows_returned": min(len(rows), max(0, int(limit))),
        "rows": rows[: max(0, int(limit))],
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="sapmcp-snapshot", description="Genera snapshot offline gzip del catálogo SAP para sapmcp.")
    parser.add_argument("--page-size", type=int, default=None, help="Tamaño de página RFC_READ_TABLE. Default SAPMCP_SNAPSHOT_PAGE_SIZE o 500.")
    parser.add_argument("--max-pages", type=int, default=None, help="Límite opcional de páginas por tabla para pruebas/control.")
    parser.add_argument("--output", type=Path, default=None, help="Ruta output .json.gz. Default ~/.sapmcp/catalog-{SID}.json.gz")
    args = parser.parse_args(argv)
    snapshot = build_snapshot(page_size=args.page_size, max_pages=args.max_pages, output_path=args.output)
    path = args.output or snapshot_path(str(snapshot["sid"]))
    # CLI output only; MCP stdio server does not call this entrypoint. Keep package stdout clean.
    sys.stderr.write(json.dumps({"ok": True, "path": str(path), "counts": snapshot["counts"]}, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
