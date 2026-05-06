from __future__ import annotations

import logging

from sapmcp import snapshot
from sapmcp.config import SapConnectionConfig


FIELDS = ["ID", "VALUE"]


def _rows(start: int, count: int) -> list[dict[str, str]]:
    return [{"ID": str(index), "VALUE": f"row-{index}"} for index in range(start, start + count)]


class FakePagedSDK:
    def __init__(self, pages_by_rowskips: dict[int, list[dict[str, str]]] | None = None, *, page_size: int | None = None):
        self.pages_by_rowskips = pages_by_rowskips or {}
        self.page_size = page_size
        self.calls: list[int] = []

    def call_function(self, function_name: str, **kwargs):
        assert function_name == "RFC_READ_TABLE"
        rowskips = int(kwargs["import_params"]["ROWSKIPS"])
        rowcount = int(kwargs["import_params"]["ROWCOUNT"])
        fields = [row["FIELDNAME"] for row in kwargs["input_tables"]["FIELDS"]]
        self.calls.append(rowskips)
        if self.page_size is not None:
            page = _rows(rowskips, self.page_size)
        else:
            page = self.pages_by_rowskips.get(rowskips, [])
        if rowcount >= 0:
            page = page[:rowcount]
        return {
            "FIELDS": [{"FIELDNAME": field} for field in fields],
            "DATA": [{"WA": "\t".join(row.get(field, "") for field in fields)} for row in page],
        }


class FakeBuildSnapshotConnector:
    DATA = {
        "TFDIR": [
            {"FUNCNAME": "RFC_PING", "PNAME": "SAPLSTFC"},
            {"FUNCNAME": "BAPI_USER_GET_DETAIL", "PNAME": "SAPLSUSO"},
        ],
        "DD02L": [{"TABNAME": "T000", "TABCLASS": "TRANSP"}],
        "DD03L": [],
    }

    def __init__(self, config: SapConnectionConfig):
        self.config = config

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def call_function(self, function_name: str, **kwargs):
        assert function_name == "RFC_READ_TABLE"
        table = kwargs["import_params"]["QUERY_TABLE"]
        rowskips = int(kwargs["import_params"]["ROWSKIPS"])
        rowcount = int(kwargs["import_params"]["ROWCOUNT"])
        fields = [row["FIELDNAME"] for row in kwargs["input_tables"]["FIELDS"]]
        page = self.DATA[table][rowskips : rowskips + rowcount]
        return {
            "FIELDS": [{"FIELDNAME": field} for field in fields],
            "DATA": [{"WA": "\t".join(row.get(field, "") for field in fields)} for row in page],
        }


def test_full_pages_stop_only_on_empty_page():
    page_size = 3
    pages = {offset: _rows(offset, page_size) for offset in range(0, 5 * page_size, page_size)}
    pages[5 * page_size] = []
    sap = FakePagedSDK(pages)

    rows = snapshot.read_table_paged(sap, "ZBIG", FIELDS, page_size=page_size)

    assert len(rows) == 5 * page_size
    assert sap.calls == [0, 3, 6, 9, 12, 15]
    assert snapshot._LAST_PAGINATION["ZBIG"] == {"pages": 6, "rows": 15, "stopped_by": "empty"}


def test_short_intermediate_page_does_not_stop_pagination():
    page_size = 4
    pages = {
        0: _rows(0, 4),
        4: _rows(4, 4),
        8: _rows(8, 2),
        10: _rows(10, 4),
        14: [],
    }
    sap = FakePagedSDK(pages)

    rows = snapshot.read_table_paged(sap, "ZSHORT_THEN_MORE", FIELDS, page_size=page_size)

    assert [row["ID"] for row in rows] == [str(index) for index in range(14)]
    assert sap.calls == [0, 4, 8, 10, 14]
    assert snapshot._LAST_PAGINATION["ZSHORT_THEN_MORE"] == {"pages": 5, "rows": 14, "stopped_by": "empty"}


def test_repeated_page_stops_as_stagnant_and_warns(caplog):
    page_size = 2
    repeated = _rows(0, 2)
    sap = FakePagedSDK({0: repeated, 2: repeated})

    with caplog.at_level(logging.WARNING, logger=snapshot.logger.name):
        rows = snapshot.read_table_paged(sap, "ZSTAGNANT", FIELDS, page_size=page_size)

    assert rows == repeated
    assert sap.calls == [0, 2]
    assert snapshot._LAST_PAGINATION["ZSTAGNANT"] == {"pages": 2, "rows": 2, "stopped_by": "stagnant"}
    assert "duplicate page indicates no effective ROWSKIPS progress" in caplog.text


def test_max_pages_is_reported_when_limit_is_reached():
    page_size = 2
    sap = FakePagedSDK(page_size=page_size)

    rows = snapshot.read_table_paged(sap, "ZMAX", FIELDS, page_size=page_size, max_pages=3)

    assert len(rows) == 3 * page_size
    assert sap.calls == [0, 2, 4]
    assert snapshot._LAST_PAGINATION["ZMAX"] == {"pages": 3, "rows": 6, "stopped_by": "max_pages"}


def test_immediate_empty_page_stops_with_zero_rows():
    sap = FakePagedSDK({0: []})

    rows = snapshot.read_table_paged(sap, "ZEMPTY", FIELDS, page_size=10)

    assert rows == []
    assert sap.calls == [0]
    assert snapshot._LAST_PAGINATION["ZEMPTY"] == {"pages": 1, "rows": 0, "stopped_by": "empty"}


def test_build_snapshot_returns_pagination_diagnostics(monkeypatch, tmp_path):
    monkeypatch.setenv("SAPMCP_HOME", str(tmp_path))
    monkeypatch.setenv("SAP_ASHOST", "dev.example")
    monkeypatch.setenv("SAP_SYSNR", "00")
    monkeypatch.setenv("SAP_CLIENT", "100")
    monkeypatch.setenv("SAP_USER", "RFC_USER")
    monkeypatch.setenv("SAP_PASS", "secret")
    monkeypatch.setenv("SAP_R3NAME", "D01")
    monkeypatch.delenv("SAPMCP_USE_KEYRING", raising=False)
    monkeypatch.setattr(snapshot, "SapRFCConnector", FakeBuildSnapshotConnector)

    data = snapshot.build_snapshot(page_size=1)

    assert data["pagination"] == {
        "TFDIR": {"pages": 3, "rows": 2, "stopped_by": "empty"},
        "DD02L": {"pages": 2, "rows": 1, "stopped_by": "empty"},
        "DD03L": {"pages": 1, "rows": 0, "stopped_by": "empty"},
    }
