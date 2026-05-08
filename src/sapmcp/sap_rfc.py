from __future__ import annotations

import concurrent.futures
import ctypes
import logging
import os
import platform
import threading
import time
from ctypes import (
    POINTER,
    Structure,
    byref,
    c_double,
    c_int,
    c_long,
    c_longlong,
    c_ubyte,
    c_uint,
    c_ushort,
    c_ulong,
    c_void_p,
    c_wchar,
    c_wchar_p,
)
from typing import Any

from .config import SapConnectionConfig, find_nwrfc_library

logger = logging.getLogger(__name__)

RFC_OK = 0
RFC_BUFFER_TOO_SMALL = 23
MAX_STRING_BUFFER = 1024 * 1024
SAP_UC = c_wchar if platform.system().lower() == "windows" else c_ushort
SAP_UC_PTR = c_wchar_p if SAP_UC is c_wchar else POINTER(SAP_UC)


def _uc_buffer(text: str | None = None, *, size: int | None = None):
    if SAP_UC is c_wchar:
        if size is not None:
            return ctypes.create_unicode_buffer(size)
        return ctypes.create_unicode_buffer("" if text is None else str(text))
    if size is not None:
        return (SAP_UC * size)()
    encoded = ("" if text is None else str(text)).encode("utf-16-le")
    values = [int.from_bytes(encoded[index : index + 2], "little") for index in range(0, len(encoded), 2)]
    values.append(0)
    return (SAP_UC * len(values))(*values)


def _uc_ptr(text: str):
    return _uc_buffer(text)


def _uc_to_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if hasattr(value, "value") and isinstance(value.value, str):
        return value.value
    units: list[int] = []
    for item in value:
        code = int(item)
        if code == 0:
            break
        units.append(code)
    data = b"".join(code.to_bytes(2, "little", signed=False) for code in units)
    return data.decode("utf-16-le", errors="replace")


RFCTYPE_NAMES = {
    0: "CHAR",
    1: "DATE",
    2: "BCD",
    3: "TIME",
    4: "BYTE",
    5: "TABLE",
    6: "NUM",
    7: "FLOAT",
    8: "INT",
    9: "INT2",
    10: "INT1",
    14: "NULL",
    16: "ABAPOBJECT",
    17: "STRUCTURE",
    23: "DECF16",
    24: "DECF34",
    28: "XMLDATA",
    29: "STRING",
    30: "XSTRING",
    31: "INT8",
    32: "UTCLONG",
}


class SapRFCError(RuntimeError):
    """Raised when SAP NetWeaver RFC SDK returns an error."""

    def __init__(self, operation: str, error_info: "SapRFCConnector.RFC_ERROR_INFO") -> None:
        self.operation = operation
        self.code = int(error_info.code)
        self.group = int(error_info.group)
        self.key = _uc_to_str(error_info.key)
        self.message = _uc_to_str(error_info.message)
        super().__init__(self.__str__())

    def __str__(self) -> str:
        bits = [f"SAP RFC error during {self.operation}: code={self.code}"]
        if self.key:
            bits.append(f"key={self.key}")
        if self.message:
            bits.append(f"message={self.message}")
        return " | ".join(bits)


class SapRFCConnector:
    """
    SAP RFC connector using SAP NetWeaver RFC SDK C library directly via ctypes.

    This is based on the vendored reference project, but made cross-platform and MCP-friendly.
    It intentionally avoids pyrfc.
    """

    class RFC_ERROR_INFO(Structure):
        _fields_ = [
            ("code", c_long),
            ("group", c_long),
            ("key", SAP_UC * 128),
            ("message", SAP_UC * 512),
            ("abapMsgClass", SAP_UC * 21),
            ("abapMsgType", SAP_UC * 2),
            ("abapMsgNumber", SAP_UC * 4),
            ("abapMsgV1", SAP_UC * 51),
            ("abapMsgV2", SAP_UC * 51),
            ("abapMsgV3", SAP_UC * 51),
            ("abapMsgV4", SAP_UC * 51),
        ]

    class RFC_CONNECTION_PARAMETER(Structure):
        _fields_ = [("name", SAP_UC_PTR), ("value", SAP_UC_PTR)]

    class RFC_FIELD_DESC(Structure):
        # Matches the leading fields from SAP NW RFC SDK's RFC_FIELD_DESC. The optional
        # tail is intentionally omitted because we only need name/type for safe reads.
        _fields_ = [
            ("name", SAP_UC * 31),
            ("type", c_uint),
            ("nucLength", c_uint),
            ("nucOffset", c_uint),
            ("ucLength", c_uint),
            ("ucOffset", c_uint),
            ("decimals", c_uint),
            ("typeDescHandle", c_void_p),
        ]

    RFC_FUNCTION_DESC_HANDLE = c_void_p
    RFC_FUNCTION_HANDLE = c_void_p
    RFC_TABLE_HANDLE = c_void_p
    RFC_STRUCTURE_HANDLE = c_void_p

    def __init__(self, config: SapConnectionConfig | None = None) -> None:
        self.config = config or SapConnectionConfig.from_env()
        # Kept for compatibility with older tests/fakes; runtime SDK calls use
        # local RFC_ERROR_INFO objects whenever possible.
        self.error_info = self.RFC_ERROR_INFO()
        self.sap_lib: Any = None
        self.connection_handle: c_void_p | None = None
        self._rfc_lock = threading.RLock()
        self._connection_invalidated = False
        self.library_path = find_nwrfc_library(self.config)
        self._load_library()

    def __enter__(self) -> "SapRFCConnector":
        self.connect()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.disconnect()

    def _load_library(self) -> None:
        lib_dir = os.path.dirname(self.library_path)
        if platform.system().lower() == "windows" and hasattr(os, "add_dll_directory"):
            os.add_dll_directory(lib_dir)
            self.sap_lib = ctypes.windll.LoadLibrary(self.library_path)  # type: ignore[attr-defined]
        else:
            # On macOS/Linux SAP also needs dependent libs in DYLD_LIBRARY_PATH/LD_LIBRARY_PATH.
            self.sap_lib = ctypes.CDLL(self.library_path)
        self._setup_function_prototypes()
        logger.info("SAP RFC library loaded: %s", self.library_path)

    def _setup_function_prototypes(self) -> None:
        lib = self.sap_lib
        lib.RfcOpenConnection.argtypes = [POINTER(self.RFC_CONNECTION_PARAMETER), c_ulong, POINTER(self.RFC_ERROR_INFO)]
        lib.RfcOpenConnection.restype = c_void_p

        lib.RfcCloseConnection.argtypes = [c_void_p, POINTER(self.RFC_ERROR_INFO)]
        lib.RfcCloseConnection.restype = c_ulong

        if hasattr(lib, "RfcCancel"):
            lib.RfcCancel.argtypes = [c_void_p, POINTER(self.RFC_ERROR_INFO)]
            lib.RfcCancel.restype = c_ulong

        lib.RfcGetFunctionDesc.argtypes = [c_void_p, SAP_UC_PTR, POINTER(self.RFC_ERROR_INFO)]
        lib.RfcGetFunctionDesc.restype = self.RFC_FUNCTION_DESC_HANDLE

        lib.RfcCreateFunction.argtypes = [self.RFC_FUNCTION_DESC_HANDLE, POINTER(self.RFC_ERROR_INFO)]
        lib.RfcCreateFunction.restype = self.RFC_FUNCTION_HANDLE

        lib.RfcDestroyFunction.argtypes = [self.RFC_FUNCTION_HANDLE, POINTER(self.RFC_ERROR_INFO)]
        lib.RfcDestroyFunction.restype = c_ulong

        lib.RfcInvoke.argtypes = [c_void_p, self.RFC_FUNCTION_HANDLE, POINTER(self.RFC_ERROR_INFO)]
        lib.RfcInvoke.restype = c_ulong

        lib.RfcGetTable.argtypes = [c_void_p, SAP_UC_PTR, POINTER(self.RFC_TABLE_HANDLE), POINTER(self.RFC_ERROR_INFO)]
        lib.RfcGetTable.restype = c_ulong

        lib.RfcAppendNewRow.argtypes = [self.RFC_TABLE_HANDLE, POINTER(self.RFC_ERROR_INFO)]
        lib.RfcAppendNewRow.restype = self.RFC_STRUCTURE_HANDLE

        lib.RfcGetRowCount.argtypes = [self.RFC_TABLE_HANDLE, POINTER(c_ulong), POINTER(self.RFC_ERROR_INFO)]
        lib.RfcGetRowCount.restype = c_ulong

        if hasattr(lib, "RfcMoveToFirstRow"):
            lib.RfcMoveToFirstRow.argtypes = [self.RFC_TABLE_HANDLE, POINTER(self.RFC_ERROR_INFO)]
            lib.RfcMoveToFirstRow.restype = c_ulong

        lib.RfcMoveToNextRow.argtypes = [self.RFC_TABLE_HANDLE, POINTER(self.RFC_ERROR_INFO)]
        lib.RfcMoveToNextRow.restype = c_ulong

        lib.RfcGetCurrentRow.argtypes = [self.RFC_TABLE_HANDLE, POINTER(self.RFC_ERROR_INFO)]
        lib.RfcGetCurrentRow.restype = self.RFC_STRUCTURE_HANDLE

        lib.RfcSetString.argtypes = [c_void_p, SAP_UC_PTR, SAP_UC_PTR, c_ulong, POINTER(self.RFC_ERROR_INFO)]
        lib.RfcSetString.restype = c_ulong

        lib.RfcGetString.argtypes = [c_void_p, SAP_UC_PTR, SAP_UC_PTR, c_ulong, POINTER(c_ulong), POINTER(self.RFC_ERROR_INFO)]
        lib.RfcGetString.restype = c_ulong

        if hasattr(lib, "RfcGetInt"):
            lib.RfcGetInt.argtypes = [c_void_p, SAP_UC_PTR, POINTER(c_int), POINTER(self.RFC_ERROR_INFO)]
            lib.RfcGetInt.restype = c_ulong
        if hasattr(lib, "RfcGetInt8"):
            lib.RfcGetInt8.argtypes = [c_void_p, SAP_UC_PTR, POINTER(c_longlong), POINTER(self.RFC_ERROR_INFO)]
            lib.RfcGetInt8.restype = c_ulong
        if hasattr(lib, "RfcGetDate"):
            lib.RfcGetDate.argtypes = [c_void_p, SAP_UC_PTR, SAP_UC_PTR, POINTER(self.RFC_ERROR_INFO)]
            lib.RfcGetDate.restype = c_ulong
        if hasattr(lib, "RfcGetTime"):
            lib.RfcGetTime.argtypes = [c_void_p, SAP_UC_PTR, SAP_UC_PTR, POINTER(self.RFC_ERROR_INFO)]
            lib.RfcGetTime.restype = c_ulong
        if hasattr(lib, "RfcGetFloat"):
            lib.RfcGetFloat.argtypes = [c_void_p, SAP_UC_PTR, POINTER(c_double), POINTER(self.RFC_ERROR_INFO)]
            lib.RfcGetFloat.restype = c_ulong
        if hasattr(lib, "RfcGetBytes"):
            lib.RfcGetBytes.argtypes = [c_void_p, SAP_UC_PTR, POINTER(c_ubyte), c_ulong, POINTER(c_ulong), POINTER(self.RFC_ERROR_INFO)]
            lib.RfcGetBytes.restype = c_ulong
        if hasattr(lib, "RfcGetXString"):
            lib.RfcGetXString.argtypes = [c_void_p, SAP_UC_PTR, POINTER(c_ubyte), c_ulong, POINTER(c_ulong), POINTER(self.RFC_ERROR_INFO)]
            lib.RfcGetXString.restype = c_ulong
        if hasattr(lib, "RfcGetFieldDescByIndex"):
            lib.RfcGetFieldDescByIndex.argtypes = [c_void_p, c_ulong, POINTER(self.RFC_FIELD_DESC), POINTER(self.RFC_ERROR_INFO)]
            lib.RfcGetFieldDescByIndex.restype = c_ulong
        if hasattr(lib, "RfcGetFieldDescByName"):
            lib.RfcGetFieldDescByName.argtypes = [c_void_p, SAP_UC_PTR, POINTER(self.RFC_FIELD_DESC), POINTER(self.RFC_ERROR_INFO)]
            lib.RfcGetFieldDescByName.restype = c_ulong
        if hasattr(lib, "RfcGetTypeAsString"):
            lib.RfcGetTypeAsString.argtypes = [c_uint]
            lib.RfcGetTypeAsString.restype = SAP_UC_PTR
        if hasattr(lib, "RfcDescribeType"):
            lib.RfcDescribeType.argtypes = [c_void_p, SAP_UC_PTR, POINTER(c_void_p), POINTER(self.RFC_ERROR_INFO)]
            lib.RfcDescribeType.restype = c_ulong

    def _operation_lock(self) -> threading.RLock:
        # Tests build connectors via __new__ to avoid loading the proprietary SDK.
        lock = getattr(self, "_rfc_lock", None)
        if lock is None:
            lock = threading.RLock()
            self._rfc_lock = lock
        return lock

    def _new_error_info(self) -> "SapRFCConnector.RFC_ERROR_INFO":
        return self.RFC_ERROR_INFO()

    def _is_connection_invalidated(self) -> bool:
        return bool(getattr(self, "_connection_invalidated", False))

    def _raise_if_error(self, rc: int, operation: str, error_info: "SapRFCConnector.RFC_ERROR_INFO | None" = None) -> None:
        if rc != RFC_OK:
            raise SapRFCError(operation, error_info or self.error_info)

    def connect(self) -> None:
        with self._operation_lock():
            if self._is_connection_invalidated():
                raise RuntimeError("SAP connection was invalidated after an RFC timeout; create a new SapRFCConnector")
            if self.connection_handle:
                return
            self.config.validate()
            params = [(key, value) for key, value in self.config.params.items() if value not in (None, "")]
            conn_params = (self.RFC_CONNECTION_PARAMETER * len(params))()
            param_buffers: list[Any] = []
            for index, (key, value) in enumerate(params):
                name_buf = _uc_buffer(key)
                value_buf = _uc_buffer(str(value))
                param_buffers.extend([name_buf, value_buf])
                conn_params[index].name = name_buf
                conn_params[index].value = value_buf

            start = time.time()
            error_info = self._new_error_info()
            handle = self.sap_lib.RfcOpenConnection(conn_params, len(params), byref(error_info))
            if not handle:
                raise SapRFCError("RfcOpenConnection", error_info)
            self.connection_handle = handle
            logger.info("SAP connected in %.2fs", time.time() - start)

    def disconnect(self) -> None:
        with self._operation_lock():
            if self.connection_handle:
                error_info = self._new_error_info()
                rc = self.sap_lib.RfcCloseConnection(self.connection_handle, byref(error_info))
                self.connection_handle = None
                self._raise_if_error(rc, "RfcCloseConnection", error_info)

    def has_function(self, function_name: str) -> bool:
        """Return whether an RFC function descriptor is available in the connected SAP system."""
        with self._operation_lock():
            if not self.connection_handle:
                self.connect()
            function_name = function_name.strip().upper()
            error_info = self._new_error_info()
            try:
                return bool(self.sap_lib.RfcGetFunctionDesc(self.connection_handle, _uc_ptr(function_name), byref(error_info)))
            except Exception:
                logger.debug("RfcGetFunctionDesc(%s) failed while checking availability", function_name, exc_info=True)
                return False

    def call_function(
        self,
        function_name: str,
        *,
        import_params: dict[str, Any] | None = None,
        input_tables: dict[str, list[dict[str, Any]]] | None = None,
        output_tables: list[str] | None = None,
        table_fields: dict[str, list[str]] | None = None,
        output_params: list[str] | None = None,
        nested_fields: dict[str, dict[str, list[str]] | list[str]] | None = None,
        buffer_size: int = 4096,
    ) -> dict[str, Any]:
        """Invoke an RFC-enabled function module."""
        with self._operation_lock():
            return self._call_function_locked(
                function_name,
                import_params=import_params,
                input_tables=input_tables,
                output_tables=output_tables,
                table_fields=table_fields,
                output_params=output_params,
                nested_fields=nested_fields,
                buffer_size=buffer_size,
            )

    def _call_function_locked(
        self,
        function_name: str,
        *,
        import_params: dict[str, Any] | None = None,
        input_tables: dict[str, list[dict[str, Any]]] | None = None,
        output_tables: list[str] | None = None,
        table_fields: dict[str, list[str]] | None = None,
        output_params: list[str] | None = None,
        nested_fields: dict[str, dict[str, list[str]] | list[str]] | None = None,
        buffer_size: int = 4096,
    ) -> dict[str, Any]:
        if self._is_connection_invalidated():
            raise RuntimeError("SAP connection was invalidated after an RFC timeout; create a new SapRFCConnector")
        if not self.connection_handle:
            self.connect()

        function_name = function_name.strip().upper()
        import_params = import_params or {}
        input_tables = input_tables or {}
        output_tables = output_tables or []
        table_fields = table_fields or {}
        output_params = output_params or []
        nested_fields = nested_fields or {}

        desc_error = self._new_error_info()
        func_desc = self.sap_lib.RfcGetFunctionDesc(self.connection_handle, _uc_ptr(function_name), byref(desc_error))
        if not func_desc:
            raise SapRFCError(f"RfcGetFunctionDesc({function_name})", desc_error)

        create_error = self._new_error_info()
        func_handle = self.sap_lib.RfcCreateFunction(func_desc, byref(create_error))
        if not func_handle:
            raise SapRFCError(f"RfcCreateFunction({function_name})", create_error)

        destroy_function = True
        try:
            for table_name, rows in input_tables.items():
                self.set_table_parameter(func_handle, table_name, rows)

            for name, value in import_params.items():
                self.set_string(func_handle, name, value)

            rc, invoke_error = self._invoke_with_timeout(func_handle, function_name)
            self._raise_if_error(rc, f"RfcInvoke({function_name})", invoke_error)

            result: dict[str, Any] = {}
            for table in output_tables:
                result[table] = self.extract_table_data(
                    func_handle,
                    table,
                    table_fields.get(table, []),
                    buffer_size=buffer_size,
                    nested_fields=nested_fields.get(table) if isinstance(nested_fields, dict) else None,
                )
            for param in output_params:
                result[param] = self.get_string(func_handle, param, buffer_size=buffer_size)
            return result
        except TimeoutError:
            # RfcCancel is asynchronous; do not destroy the function handle while the worker
            # thread may still be unwinding inside sapnwrfc.
            destroy_function = False
            raise
        finally:
            if destroy_function:
                destroy_error = self._new_error_info()
                rc = self.sap_lib.RfcDestroyFunction(func_handle, byref(destroy_error))
                if rc != RFC_OK:
                    logger.warning("RfcDestroyFunction failed: %s", SapRFCError("RfcDestroyFunction", destroy_error))

    def _rfc_timeout_seconds(self) -> float:
        raw = os.getenv("SAPMCP_RFC_TIMEOUT", "60")
        try:
            timeout = float(raw)
        except ValueError:
            logger.warning("Invalid SAPMCP_RFC_TIMEOUT=%r; using 60 seconds", raw)
            return 60.0
        return max(timeout, 0.001)

    def _invoke_with_timeout(self, func_handle: c_void_p, function_name: str) -> tuple[int, "SapRFCConnector.RFC_ERROR_INFO"]:
        """Invoke RFC with a Python-side timeout guard.

        The SAP NW RFC SDK call itself is synchronous. On timeout we call
        RfcCancel and invalidate this connector because the worker thread may
        still be inside sapnwrfc. The function handle is not destroyed on the
        caller thread while it may be in use; a done callback attempts deferred
        destruction only after RfcInvoke returns.
        """

        if not self.connection_handle:
            raise RuntimeError("SAP connection is not open")
        connection_handle = self.connection_handle
        timeout = self._rfc_timeout_seconds()
        invoke_error = self._new_error_info()
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="sapmcp-rfc-invoke")
        future = executor.submit(self.sap_lib.RfcInvoke, connection_handle, func_handle, byref(invoke_error))
        try:
            return int(future.result(timeout=timeout)), invoke_error
        except concurrent.futures.TimeoutError as exc:
            self._schedule_destroy_after_invoke(future, func_handle, function_name)
            self._cancel_connection_after_timeout()
            raise TimeoutError(f"RfcInvoke({function_name}) timed out after {timeout:g}s") from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _schedule_destroy_after_invoke(self, future: concurrent.futures.Future[Any], func_handle: c_void_p, function_name: str) -> None:
        def destroy_when_done(done: concurrent.futures.Future[Any]) -> None:
            try:
                done.result()
            except Exception:
                logger.debug("RfcInvoke(%s) worker completed after timeout with an exception", function_name, exc_info=True)
            destroy_error = self._new_error_info()
            try:
                rc = self.sap_lib.RfcDestroyFunction(func_handle, byref(destroy_error))
                if rc != RFC_OK:
                    logger.warning("Deferred RfcDestroyFunction(%s) failed: %s", function_name, SapRFCError("RfcDestroyFunction", destroy_error))
            except Exception:
                logger.exception("Deferred RfcDestroyFunction(%s) failed", function_name)

        future.add_done_callback(destroy_when_done)

    def _cancel_connection_after_timeout(self) -> None:
        handle = self.connection_handle
        cancel_error = self._new_error_info()
        try:
            if handle and hasattr(self.sap_lib, "RfcCancel"):
                rc = self.sap_lib.RfcCancel(handle, byref(cancel_error))
                if rc != RFC_OK:
                    logger.warning("RfcCancel returned rc=%s", rc)
        except Exception:
            logger.exception("RfcCancel failed")
        finally:
            self.connection_handle = None
            self._connection_invalidated = True

    def set_string(self, container_handle: c_void_p, field: str, value: Any) -> None:
        text = "" if value is None else str(value)
        error_info = self._new_error_info()
        rc = self.sap_lib.RfcSetString(container_handle, _uc_ptr(field.upper()), _uc_ptr(text), len(text), byref(error_info))
        self._raise_if_error(rc, f"RfcSetString({field})", error_info)

    def get_string(self, container_handle: c_void_p, field: str, *, buffer_size: int = 4096) -> str:
        size = max(1, int(buffer_size))
        error_info = self._new_error_info()
        while True:
            if size > MAX_STRING_BUFFER:
                raise BufferError(f"RfcGetString({field}) requested buffer exceeds {MAX_STRING_BUFFER} bytes")
            buffer = _uc_buffer(size=size)
            length = c_ulong()
            rc = self.sap_lib.RfcGetString(container_handle, _uc_ptr(field.upper()), buffer, size, byref(length), byref(error_info))
            if rc == RFC_OK:
                return _uc_to_str(buffer)
            if rc == RFC_BUFFER_TOO_SMALL:
                requested = int(length.value or 0)
                if requested > MAX_STRING_BUFFER:
                    raise BufferError(f"RfcGetString({field}) requested {requested} bytes; max={MAX_STRING_BUFFER}")
                next_size = max(size * 2, requested + 1 if requested else 0)
                if next_size <= size:
                    next_size = size * 2
                size = next_size
                continue
            self._raise_if_error(rc, f"RfcGetString({field})", error_info)

    def get_int(self, container_handle: c_void_p, field: str) -> int:
        if not hasattr(self.sap_lib, "RfcGetInt"):
            return int(self.get_string(container_handle, field).strip() or 0)
        value = c_int()
        error_info = self._new_error_info()
        rc = self.sap_lib.RfcGetInt(container_handle, _uc_ptr(field.upper()), byref(value), byref(error_info))
        self._raise_if_error(rc, f"RfcGetInt({field})", error_info)
        return int(value.value)

    def get_int8(self, container_handle: c_void_p, field: str) -> int:
        if not hasattr(self.sap_lib, "RfcGetInt8"):
            return int(self.get_string(container_handle, field).strip() or 0)
        value = c_longlong()
        error_info = self._new_error_info()
        rc = self.sap_lib.RfcGetInt8(container_handle, _uc_ptr(field.upper()), byref(value), byref(error_info))
        self._raise_if_error(rc, f"RfcGetInt8({field})", error_info)
        return int(value.value)

    def get_date(self, container_handle: c_void_p, field: str) -> str:
        if not hasattr(self.sap_lib, "RfcGetDate"):
            return self.get_string(container_handle, field, buffer_size=9)
        buffer = _uc_buffer(size=9)
        error_info = self._new_error_info()
        rc = self.sap_lib.RfcGetDate(container_handle, _uc_ptr(field.upper()), buffer, byref(error_info))
        self._raise_if_error(rc, f"RfcGetDate({field})", error_info)
        return _uc_to_str(buffer)

    def get_time(self, container_handle: c_void_p, field: str) -> str:
        if not hasattr(self.sap_lib, "RfcGetTime"):
            return self.get_string(container_handle, field, buffer_size=7)
        buffer = _uc_buffer(size=7)
        error_info = self._new_error_info()
        rc = self.sap_lib.RfcGetTime(container_handle, _uc_ptr(field.upper()), buffer, byref(error_info))
        self._raise_if_error(rc, f"RfcGetTime({field})", error_info)
        return _uc_to_str(buffer)

    def get_float(self, container_handle: c_void_p, field: str) -> float:
        if not hasattr(self.sap_lib, "RfcGetFloat"):
            return float(self.get_string(container_handle, field).strip() or 0)
        value = c_double()
        error_info = self._new_error_info()
        rc = self.sap_lib.RfcGetFloat(container_handle, _uc_ptr(field.upper()), byref(value), byref(error_info))
        self._raise_if_error(rc, f"RfcGetFloat({field})", error_info)
        return float(value.value)

    def get_bytes_hex(self, container_handle: c_void_p, field: str, *, xstring: bool = False, buffer_size: int = 4096) -> str:
        func_name = "RfcGetXString" if xstring and hasattr(self.sap_lib, "RfcGetXString") else "RfcGetBytes"
        if not hasattr(self.sap_lib, func_name):
            return self.get_string(container_handle, field, buffer_size=buffer_size).encode("utf-8", errors="surrogatepass").hex()
        func = getattr(self.sap_lib, func_name)
        size = max(1, int(buffer_size))
        error_info = self._new_error_info()
        while True:
            if size > MAX_STRING_BUFFER:
                raise BufferError(f"{func_name}({field}) requested buffer exceeds {MAX_STRING_BUFFER} bytes")
            buffer = (c_ubyte * size)()
            length = c_ulong()
            rc = func(container_handle, _uc_ptr(field.upper()), buffer, size, byref(length), byref(error_info))
            if rc == RFC_OK:
                return bytes(buffer[: length.value]).hex()
            if rc == RFC_BUFFER_TOO_SMALL:
                requested = int(length.value or 0)
                if requested > MAX_STRING_BUFFER:
                    raise BufferError(f"{func_name}({field}) requested {requested} bytes; max={MAX_STRING_BUFFER}")
                size = max(size * 2, requested + 1 if requested else 0)
                continue
            self._raise_if_error(rc, f"{func_name}({field})", error_info)

    def _type_as_string(self, type_code: int) -> str | None:
        if hasattr(self.sap_lib, "RfcGetTypeAsString"):
            try:
                raw = self.sap_lib.RfcGetTypeAsString(int(type_code))
                if isinstance(raw, bytes):
                    return raw.decode(errors="replace")
                if raw:
                    return _uc_to_str(raw)
            except Exception:
                logger.debug("RfcGetTypeAsString failed for type=%s", type_code, exc_info=True)
        return RFCTYPE_NAMES.get(int(type_code))

    def _normalize_type_name(self, type_name: str | None) -> str | None:
        if not type_name:
            return None
        normalized = str(type_name).upper().strip()
        for prefix in ("RFCTYPE_", "RFC_TYPE_"):
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix) :]
        return normalized

    def _describe_field_type(self, row_handle: c_void_p, field: str, index: int) -> str | None:
        # The SAP NW RFC SDK descriptor APIs expect type-description handles, not arbitrary
        # row/data handles. Calling them against a live SDK row handle can crash the process.
        # Keep descriptor probing enabled for tests/fakes and allow explicit opt-in for labs.
        if isinstance(self.sap_lib, ctypes.CDLL) and os.getenv("SAPMCP_UNSAFE_FIELD_DESCRIBE", "").lower() not in {"1", "true", "yes"}:
            return None
        desc = self.RFC_FIELD_DESC()
        rc: int | None = None
        error_info = self._new_error_info()
        if hasattr(self.sap_lib, "RfcGetFieldDescByName"):
            try:
                rc = self.sap_lib.RfcGetFieldDescByName(row_handle, _uc_ptr(field.upper()), byref(desc), byref(error_info))
            except Exception:
                logger.debug("RfcGetFieldDescByName failed for %s", field, exc_info=True)
                rc = None
        if rc != RFC_OK and hasattr(self.sap_lib, "RfcGetFieldDescByIndex"):
            try:
                rc = self.sap_lib.RfcGetFieldDescByIndex(row_handle, index, byref(desc), byref(error_info))
            except Exception:
                logger.debug("RfcGetFieldDescByIndex failed for %s", field, exc_info=True)
                rc = None
        if rc != RFC_OK:
            return None
        name = _uc_to_str(desc.name).strip().upper()
        if name and name != field.upper():
            logger.debug("Field descriptor mismatch: requested=%s descriptor=%s", field, name)
        return self._normalize_type_name(self._type_as_string(int(desc.type)))

    def _get_field_value(self, row_handle: c_void_p, field: str, index: int, *, buffer_size: int) -> Any:
        field_type = self._describe_field_type(row_handle, field, index)
        try:
            if field_type in {"INT", "INT1", "INT2"}:
                return self.get_int(row_handle, field)
            if field_type == "INT8":
                return self.get_int8(row_handle, field)
            if field_type == "DATE":
                return self.get_date(row_handle, field)
            if field_type == "TIME":
                return self.get_time(row_handle, field)
            if field_type == "FLOAT":
                return self.get_float(row_handle, field)
            if field_type in {"RAW", "BYTE"}:
                return self.get_bytes_hex(row_handle, field, buffer_size=buffer_size)
            if field_type == "XSTRING":
                return self.get_bytes_hex(row_handle, field, xstring=True, buffer_size=buffer_size)
        except Exception:
            logger.debug("Typed read failed for field=%s type=%s; falling back to string", field, field_type, exc_info=True)
        return self.get_string(row_handle, field, buffer_size=buffer_size)

    def set_table_parameter(self, func_handle: c_void_p, table_name: str, rows: list[dict[str, Any]]) -> None:
        table_handle = self.RFC_TABLE_HANDLE()
        error_info = self._new_error_info()
        rc = self.sap_lib.RfcGetTable(func_handle, _uc_ptr(table_name.upper()), byref(table_handle), byref(error_info))
        self._raise_if_error(rc, f"RfcGetTable({table_name})", error_info)
        for row in rows:
            append_error = self._new_error_info()
            struct_handle = self.sap_lib.RfcAppendNewRow(table_handle, byref(append_error))
            if not struct_handle:
                raise SapRFCError(f"RfcAppendNewRow({table_name})", append_error)
            for field, value in row.items():
                if isinstance(value, list):
                    self._fill_nested_table(struct_handle, field, value)
                else:
                    self.set_string(struct_handle, field, value)

    def _fill_nested_table(self, parent_handle: c_void_p, table_field_name: str, rows: list[dict[str, Any]], *, level: int = 1, max_level: int = 3) -> None:
        if level > max_level:
            return
        table_handle = self.RFC_TABLE_HANDLE()
        error_info = self._new_error_info()
        rc = self.sap_lib.RfcGetTable(parent_handle, _uc_ptr(table_field_name.upper()), byref(table_handle), byref(error_info))
        self._raise_if_error(rc, f"RfcGetTable(nested {table_field_name})", error_info)
        for row in rows:
            append_error = self._new_error_info()
            struct_handle = self.sap_lib.RfcAppendNewRow(table_handle, byref(append_error))
            if not struct_handle:
                raise SapRFCError(f"RfcAppendNewRow(nested {table_field_name})", append_error)
            for field, value in row.items():
                if isinstance(value, list):
                    self._fill_nested_table(struct_handle, field, value, level=level + 1, max_level=max_level)
                else:
                    self.set_string(struct_handle, field, value)

    def extract_table_data(
        self,
        func_handle: c_void_p,
        table_name: str,
        fields: list[str],
        *,
        buffer_size: int = 4096,
        nested_fields: dict[str, list[str]] | list[str] | None = None,
    ) -> list[dict[str, Any]]:
        table_handle = self.RFC_TABLE_HANDLE()
        error_info = self._new_error_info()
        rc = self.sap_lib.RfcGetTable(func_handle, _uc_ptr(table_name.upper()), byref(table_handle), byref(error_info))
        self._raise_if_error(rc, f"RfcGetTable({table_name})", error_info)
        row_count = c_ulong()
        count_error = self._new_error_info()
        rc = self.sap_lib.RfcGetRowCount(table_handle, byref(row_count), byref(count_error))
        self._raise_if_error(rc, f"RfcGetRowCount({table_name})", count_error)

        result: list[dict[str, Any]] = []
        if row_count.value == 0:
            return result

        if hasattr(self.sap_lib, "RfcMoveToFirstRow"):
            move_error = self._new_error_info()
            rc = self.sap_lib.RfcMoveToFirstRow(table_handle, byref(move_error))
            self._raise_if_error(rc, f"RfcMoveToFirstRow({table_name})", move_error)

        for index in range(row_count.value):
            if index > 0:
                move_error = self._new_error_info()
                rc = self.sap_lib.RfcMoveToNextRow(table_handle, byref(move_error))
                self._raise_if_error(rc, f"RfcMoveToNextRow({table_name})", move_error)
            row_error = self._new_error_info()
            row_handle = self.sap_lib.RfcGetCurrentRow(table_handle, byref(row_error))
            if not row_handle:
                raise SapRFCError(f"RfcGetCurrentRow({table_name})", row_error)
            row: dict[str, Any] = {}
            for field_index, field in enumerate(fields):
                row[field.upper()] = self._get_field_value(row_handle, field, field_index, buffer_size=buffer_size)
            if isinstance(nested_fields, dict):
                for nested_table, nested_cols in nested_fields.items():
                    row[nested_table.upper()] = self._extract_nested_table(row_handle, nested_table, nested_cols)
            result.append(row)
        return result

    def _extract_nested_table(self, struct_handle: c_void_p, table_name: str, fields: list[str]) -> list[dict[str, Any]]:
        table_handle = self.RFC_TABLE_HANDLE()
        error_info = self._new_error_info()
        rc = self.sap_lib.RfcGetTable(struct_handle, _uc_ptr(table_name.upper()), byref(table_handle), byref(error_info))
        self._raise_if_error(rc, f"RfcGetTable(nested {table_name})", error_info)
        row_count = c_ulong()
        count_error = self._new_error_info()
        rc = self.sap_lib.RfcGetRowCount(table_handle, byref(row_count), byref(count_error))
        self._raise_if_error(rc, f"RfcGetRowCount(nested {table_name})", count_error)
        result: list[dict[str, Any]] = []
        if row_count.value == 0:
            return result
        if hasattr(self.sap_lib, "RfcMoveToFirstRow"):
            move_error = self._new_error_info()
            rc = self.sap_lib.RfcMoveToFirstRow(table_handle, byref(move_error))
            self._raise_if_error(rc, f"RfcMoveToFirstRow(nested {table_name})", move_error)
        for index in range(row_count.value):
            if index > 0:
                move_error = self._new_error_info()
                rc = self.sap_lib.RfcMoveToNextRow(table_handle, byref(move_error))
                self._raise_if_error(rc, f"RfcMoveToNextRow(nested {table_name})", move_error)
            row_error = self._new_error_info()
            row_handle = self.sap_lib.RfcGetCurrentRow(table_handle, byref(row_error))
            if not row_handle:
                raise SapRFCError(f"RfcGetCurrentRow(nested {table_name})", row_error)
            row = {field.upper(): self._get_field_value(row_handle, field, field_index, buffer_size=4096) for field_index, field in enumerate(fields)}
            result.append(row)
        return result
