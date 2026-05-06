from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from sapmcp.config import SafetyPolicy, SapConnectionConfig
from sapmcp.sap_rfc import MAX_STRING_BUFFER, RFC_BUFFER_TOO_SMALL, SapRFCConnector, _uc_buffer


def _set_ptr(ptr, value):
    ptr._obj.value = value


def make_fake_sdk(**overrides):
    fake = SimpleNamespace()
    defaults = {
        "RfcOpenConnection": Mock(return_value=100),
        "RfcCloseConnection": Mock(return_value=0),
        "RfcCancel": Mock(return_value=0),
        "RfcGetFunctionDesc": Mock(return_value=101),
        "RfcCreateFunction": Mock(return_value=102),
        "RfcDestroyFunction": Mock(return_value=0),
        "RfcInvoke": Mock(return_value=0),
        "RfcGetTable": Mock(side_effect=lambda container, name, table_ptr, err: (_set_ptr(table_ptr, 201), 0)[1]),
        "RfcAppendNewRow": Mock(return_value=301),
        "RfcGetRowCount": Mock(side_effect=lambda table, count_ptr, err: (_set_ptr(count_ptr, 1), 0)[1]),
        "RfcMoveToFirstRow": Mock(return_value=0),
        "RfcMoveToNextRow": Mock(return_value=0),
        "RfcGetCurrentRow": Mock(return_value=301),
        "RfcGetString": Mock(side_effect=lambda container, field, buffer, size, length_ptr, err: (setattr(buffer, "value", ""), _set_ptr(length_ptr, 0), 0)[2]),
        "RfcSetString": Mock(return_value=0),
        "RfcGetInt": Mock(side_effect=lambda container, field, value_ptr, err: (_set_ptr(value_ptr, 42), 0)[1]),
        "RfcGetFieldDescByIndex": Mock(return_value=1),
    }
    defaults.update(overrides)
    for name, value in defaults.items():
        setattr(fake, name, value)
    return fake


def make_connector(fake):
    connector = SapRFCConnector.__new__(SapRFCConnector)
    connector.config = SapConnectionConfig(params={"ASHOST": "sap", "SYSNR": "00", "CLIENT": "100", "USER": "u", "PASSWD": "p"})
    connector.error_info = SapRFCConnector.RFC_ERROR_INFO()
    connector.sap_lib = fake
    connector.connection_handle = 100
    connector.library_path = "fake-sapnwrfc"
    connector._setup_function_prototypes()
    return connector


def test_get_string_retries_buffer_too_small_once():
    value = "valor ampliado"
    calls = []

    def rfc_get_string(container, field, buffer, size, length_ptr, err):
        calls.append(size)
        if len(calls) == 1:
            _set_ptr(length_ptr, len(value) + 1)
            return RFC_BUFFER_TOO_SMALL
        buffer.value = value
        _set_ptr(length_ptr, len(value))
        return 0

    connector = make_connector(make_fake_sdk(RfcGetString=Mock(side_effect=rfc_get_string)))

    assert connector.get_string(301, "TEXT", buffer_size=4) == value
    assert calls == [4, len(value) + 2]


def test_get_string_aborts_when_requested_length_exceeds_one_mib():
    def rfc_get_string(container, field, buffer, size, length_ptr, err):
        _set_ptr(length_ptr, MAX_STRING_BUFFER + 1)
        return RFC_BUFFER_TOO_SMALL

    connector = make_connector(make_fake_sdk(RfcGetString=Mock(side_effect=rfc_get_string)))

    with pytest.raises(BufferError, match="max=1048576"):
        connector.get_string(301, "TEXT", buffer_size=4)


def test_extract_table_data_uses_get_int_for_int_field():
    def describe_int(container, index, desc_ptr, err):
        desc = desc_ptr._obj
        name = _uc_buffer("COUNT")
        for i, code in enumerate(name):
            desc.name[i] = code
        desc.type = 8  # RFCTYPE_INT
        return 0

    fake = make_fake_sdk(RfcGetFieldDescByIndex=Mock(side_effect=describe_int))
    connector = make_connector(fake)

    rows = connector.extract_table_data(102, "ET_DATA", ["COUNT"])

    assert rows == [{"COUNT": 42}]
    assert fake.RfcGetInt.call_count == 1
    assert fake.RfcGetString.call_count == 0


def test_assert_allowed_messages_are_ordered_and_parseable():
    with pytest.raises(PermissionError, match=r"RFC Z_CREATE_THING blocked: reason=dangerous"):
        SafetyPolicy(read_only=True, allowed_rfc=["Z_SAFE_READ"]).assert_allowed("Z_CREATE_THING")

    with pytest.raises(PermissionError, match=r"RFC RFC_PING blocked: reason=not_in_allowlist"):
        SafetyPolicy(read_only=False, allowed_rfc=["Z_SAFE_READ"]).assert_allowed("RFC_PING")

    with pytest.raises(PermissionError, match=r"RFC Z_SAFE_READ blocked: reason=read_only_unknown_read"):
        SafetyPolicy(read_only=True).assert_allowed("Z_SAFE_READ")


def test_call_function_timeout_cancels_and_invalidates_connection(monkeypatch):
    def slow_invoke(connection, function, err):
        time.sleep(0.05)
        return 0

    fake = make_fake_sdk(RfcInvoke=Mock(side_effect=slow_invoke))
    connector = make_connector(fake)
    monkeypatch.setenv("SAPMCP_RFC_TIMEOUT", "0.001")

    with pytest.raises(TimeoutError, match="timed out"):
        connector.call_function("RFC_PING")

    assert connector.connection_handle is None
    assert fake.RfcCancel.call_count == 1
