from __future__ import annotations

import pytest

from sapmcp.read_table import (
    build_rfc_read_table_request,
    normalize_field_name,
    normalize_sap_date,
    normalize_sap_user,
    normalize_table_name,
    sap_eq,
    validate_where_options,
)


@pytest.mark.parametrize("payload", ["' OR '1'='1", "USER' AND '1'='1"])
def test_sap_user_rejects_injection_payloads(payload):
    with pytest.raises(ValueError):
        normalize_sap_user(payload, required=True)


@pytest.mark.parametrize("name", ["USR02;DELETE", "USR02 WHERE 1=1", "BNAME'", "BKPF.FIELD"])
def test_table_and_field_names_reject_invalid_values(name):
    with pytest.raises(ValueError):
        normalize_table_name(name)
    with pytest.raises(ValueError):
        normalize_field_name(name)


def test_sap_date_validates_real_yyyymmdd():
    assert normalize_sap_date("20260508") == "20260508"
    with pytest.raises(ValueError):
        normalize_sap_date("20261301")
    with pytest.raises(ValueError):
        normalize_sap_date("2026-05-08")


def test_sap_literal_builder_escapes_quote_payload_as_literal():
    option = sap_eq("BNAME", "' OR '1'='1")

    assert option == "BNAME = ''' OR ''1''=''1'"


def test_advanced_where_rejects_obvious_injection_shapes():
    with pytest.raises(ValueError):
        validate_where_options(["' OR '1'='1"], advanced=True)
    with pytest.raises(ValueError):
        validate_where_options(["USER' AND '1'='1"], advanced=True)
    with pytest.raises(ValueError):
        validate_where_options(["BNAME = 'ALICE' OR '1'='1'"], advanced=True)


def test_build_rfc_read_table_request_validates_and_shapes_payload():
    request = build_rfc_read_table_request("usr02", ["bname", "trdat"], [sap_eq("BNAME", "ALICE")], rowcount=500, rowskips=2, max_rows=100)

    assert request.table_name == "USR02"
    assert request.fields == ["BNAME", "TRDAT"]
    assert request.rowcount == 100
    assert request.call_kwargs()["input_tables"]["OPTIONS"] == [{"TEXT": "BNAME = 'ALICE'"}]
