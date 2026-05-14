from __future__ import annotations

from sapmcp import snapshot
from sapmcp.config import SapConnectionConfig


class FakeSnapshotConnector:
    DATA = {
        "TFDIR": [
            {"FUNCNAME": "BAPI_USER_GET_DETAIL", "PNAME": "SAPLSUSO"},
            {"FUNCNAME": "RFC_PING", "PNAME": "SAPLSTFC"},
        ],
        "DD02L": [
            {"TABNAME": "BKPF", "TABCLASS": "TRANSP"},
            {"TABNAME": "T000", "TABCLASS": "TRANSP"},
        ],
        "DD03L": [
            {"TABNAME": "BKPF", "FIELDNAME": "BUKRS", "ROLLNAME": "BUKRS", "POSITION": "1", "KEYFLAG": "X", "INTTYPE": "C"},
            {"TABNAME": "BKPF", "FIELDNAME": "BELNR", "ROLLNAME": "BELNR_D", "POSITION": "2", "KEYFLAG": "X", "INTTYPE": "C"},
        ],
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


def test_snapshot_writes_expected_schema_and_searches_offline(monkeypatch, tmp_path):
    monkeypatch.setenv("SAPMCP_HOME", str(tmp_path))
    monkeypatch.setenv("SAP_ASHOST", "dev.example")
    monkeypatch.setenv("SAP_SYSNR", "00")
    monkeypatch.setenv("SAP_CLIENT", "100")
    monkeypatch.setenv("SAP_USER", "RFC_USER")
    monkeypatch.setenv("SAP_PASS", "secret")
    monkeypatch.setenv("SAP_R3NAME", "D01")
    monkeypatch.delenv("SAPMCP_USE_KEYRING", raising=False)
    monkeypatch.setattr(snapshot, "SapRFCConnector", FakeSnapshotConnector)

    data = snapshot.build_snapshot(page_size=1)
    path = snapshot.snapshot_path("D01")

    assert path.exists()
    assert data["version"] == 1
    assert data["sid"] == "D01"
    assert data["counts"] == {"rfc": 2, "tables": 2, "fields": 2}
    assert data["rfc"][0] == {"FUNCNAME": "BAPI_USER_GET_DETAIL", "PNAME": "SAPLSUSO"}
    assert data["tables"][0] == {"TABNAME": "BKPF", "TABCLASS": "TRANSP"}
    assert data["fields"][0]["FIELDNAME"] == "BUKRS"

    loaded = snapshot.load_snapshot(path)
    assert loaded["counts"] == data["counts"]

    rfc_search = snapshot.search_snapshot("rfc", "BAPI_USER")
    assert rfc_search["exists"] is True
    assert rfc_search["rows"] == [{"FUNCNAME": "BAPI_USER_GET_DETAIL", "PNAME": "SAPLSUSO"}]

    table_search = snapshot.search_snapshot("table", "BK*")
    assert table_search["rows"] == [{"TABNAME": "BKPF", "TABCLASS": "TRANSP"}]

    resource = snapshot.snapshot_resource()
    assert resource["exists"] is True
    assert resource["sid"] == "D01"
    assert resource["rfc"][0]["FUNCNAME"] == "BAPI_USER_GET_DETAIL"


def test_find_snapshot_path_fallback_on_exception(monkeypatch, tmp_path):
    monkeypatch.setenv("SAPMCP_HOME", str(tmp_path))

    # Create a candidate snapshot file
    candidate_path = tmp_path / "catalog-OTHER.json.gz"
    candidate_path.touch()

    # Mock snapshot_path to raise an exception
    def mock_snapshot_path(*args, **kwargs):
        raise RuntimeError("Preferred path error")

    monkeypatch.setattr(snapshot, "snapshot_path", mock_snapshot_path)

    # find_snapshot_path should catch the exception and return the candidate
    result = snapshot.find_snapshot_path()
    assert result == candidate_path
