import os
import time
import logging
from ctypes import *
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class SapRFCConnector:
    """
    Lightweight SAP RFC connector using sapnwrfc.dll directly via ctypes.
    Supports importing parameters, tables, and nested tables (recursive).
    """

    # ===============================
    # RFC Structures
    # ===============================

    class RFC_ERROR_INFO(Structure):
        _fields_ = [
            ("code", c_long),
            ("group", c_long),
            ("key", c_wchar * 128),
            ("message", c_wchar * 512),
            ("abapMsgClass", c_wchar * 21),
            ("abapMsgType", c_wchar * 2),
            ("abapMsgNumber", c_wchar * 4),
            ("abapMsgV1", c_wchar * 51),
            ("abapMsgV2", c_wchar * 51),
            ("abapMsgV3", c_wchar * 51),
            ("abapMsgV4", c_wchar * 51),
        ]

    class RFC_CONNECTION_PARAMETER(Structure):
        _fields_ = [("name", c_wchar_p), ("value", c_wchar_p)]

    class RFC_FUNCTION_DESC_HANDLE(c_void_p):
        pass

    class RFC_FUNCTION_HANDLE(c_void_p):
        pass

    class RFC_TABLE_HANDLE(c_void_p):
        pass

    # ===============================
    # Initialization
    # ===============================

    def __init__(self, dll_directory="C:\\nwrfcsdk\\lib"):
        self.dll_directory = dll_directory
        self.dll_path = os.path.join(dll_directory, "sapnwrfc.dll")

        os.add_dll_directory(self.dll_directory)

        self.error_info = self.RFC_ERROR_INFO()
        self.sap_lib = None
        self.connection_handle = None

        self._load_dll()

    # ===============================
    # DLL & Prototypes
    # ===============================

    def _load_dll(self):
        self.sap_lib = windll.LoadLibrary(self.dll_path)
        self._setup_function_prototypes()
        logger.info("SAP RFC DLL loaded successfully")

    def _setup_function_prototypes(self):
        lib = self.sap_lib

        lib.RfcOpenConnection.argtypes = [
            POINTER(self.RFC_CONNECTION_PARAMETER),
            c_ulong,
            POINTER(self.RFC_ERROR_INFO),
        ]
        lib.RfcOpenConnection.restype = c_void_p

        lib.RfcCloseConnection.argtypes = [c_void_p, POINTER(self.RFC_ERROR_INFO)]
        lib.RfcCloseConnection.restype = c_ulong

        lib.RfcGetFunctionDesc.argtypes = [
            c_void_p,
            c_wchar_p,
            POINTER(self.RFC_ERROR_INFO),
        ]
        lib.RfcGetFunctionDesc.restype = self.RFC_FUNCTION_DESC_HANDLE

        lib.RfcCreateFunction.argtypes = [
            self.RFC_FUNCTION_DESC_HANDLE,
            POINTER(self.RFC_ERROR_INFO),
        ]
        lib.RfcCreateFunction.restype = self.RFC_FUNCTION_HANDLE

        lib.RfcDestroyFunction.argtypes = [
            self.RFC_FUNCTION_HANDLE,
            POINTER(self.RFC_ERROR_INFO),
        ]

        lib.RfcInvoke.argtypes = [
            c_void_p,
            self.RFC_FUNCTION_HANDLE,
            POINTER(self.RFC_ERROR_INFO),
        ]

        lib.RfcGetTable.argtypes = [
            c_void_p,
            c_wchar_p,
            POINTER(self.RFC_TABLE_HANDLE),
            POINTER(self.RFC_ERROR_INFO),
        ]

        lib.RfcAppendNewRow.argtypes = [
            self.RFC_TABLE_HANDLE,
            POINTER(self.RFC_ERROR_INFO),
        ]
        lib.RfcAppendNewRow.restype = c_void_p

        lib.RfcGetRowCount.argtypes = [
            self.RFC_TABLE_HANDLE,
            POINTER(c_ulong),
            POINTER(self.RFC_ERROR_INFO),
        ]

        lib.RfcMoveToNextRow.argtypes = [
            self.RFC_TABLE_HANDLE,
            POINTER(self.RFC_ERROR_INFO),
        ]

        lib.RfcGetCurrentRow.argtypes = [
            self.RFC_TABLE_HANDLE,
            POINTER(self.RFC_ERROR_INFO),
        ]
        lib.RfcGetCurrentRow.restype = c_void_p

        lib.RfcSetString.argtypes = [
            c_void_p,
            c_wchar_p,
            c_wchar_p,
            c_ulong,
            POINTER(self.RFC_ERROR_INFO),
        ]

        lib.RfcGetString.argtypes = [
            c_void_p,
            c_wchar_p,
            c_wchar_p,
            c_ulong,
            POINTER(c_ulong),
            POINTER(self.RFC_ERROR_INFO),
        ]

    # ===============================
    # Connection
    # ===============================

    def connect(self):
        params = [
            ("ASHOST", os.getenv("SAP_HOST")),
            ("SYSNR", os.getenv("SAP_SYSNR")),
            ("CLIENT", os.getenv("SAP_CLIENT")),
            ("USER", os.getenv("SAP_USER")),
            ("PASSWD", os.getenv("SAP_PASS")),
        ]

        conn_params = (self.RFC_CONNECTION_PARAMETER * len(params))()
        for i, (k, v) in enumerate(params):
            conn_params[i].name = k
            conn_params[i].value = v

        start = time.time()
        self.connection_handle = self.sap_lib.RfcOpenConnection(
            conn_params, len(params), byref(self.error_info)
        )

        if not self.connection_handle:
            raise RuntimeError(self._format_error("OpenConnection"))

        logger.info(f"SAP connected in {time.time() - start:.2f}s")

    def disconnect(self):
        if self.connection_handle:
            self.sap_lib.RfcCloseConnection(
                self.connection_handle, byref(self.error_info)
            )
            self.connection_handle = None

    # ===============================
    # RFC Execution
    # ===============================

    def call_function(self, function_name, **params):
        if not self.connection_handle:
            self.connect()

        func_desc = self.sap_lib.RfcGetFunctionDesc(
            self.connection_handle, function_name, byref(self.error_info)
        )

        func_handle = self.sap_lib.RfcCreateFunction(
            func_desc, byref(self.error_info)
        )

        input_tables = params.pop("input_tables", {})
        output_tables = params.pop("tables", [])
        output_fields = params.pop("table_fields", {})
        nested_fields = params.pop("nested_fields", {})
        output_params = params.pop("output_params", [])

        for table_name, rows in input_tables.items():
            self.set_table_parameter(func_handle, table_name, rows)

        for name, value in params.items():
            self.sap_lib.RfcSetString(
                func_handle, name, str(value), len(str(value)), byref(self.error_info)
            )

        self.sap_lib.RfcInvoke(
            self.connection_handle, func_handle, byref(self.error_info)
        )

        result = {}

        for table in output_tables:
            result[table] = self.extract_table_data(
                func_handle,
                table,
                output_fields.get(table),
                512,
                nested_fields,
            )

        for param in output_params:
            buffer = create_unicode_buffer(512)
            length = c_ulong()
            self.sap_lib.RfcGetString(
                func_handle, param, buffer, 512, byref(length), byref(self.error_info)
            )
            result[param] = buffer.value

        self.sap_lib.RfcDestroyFunction(func_handle, byref(self.error_info))
        return result

    # ===============================
    # Table Handling (INCLUDING NESTED)
    # ===============================

    def set_table_parameter(self, func_handle, table_name, rows):
        table_handle = self.RFC_TABLE_HANDLE()
        self.sap_lib.RfcGetTable(
            func_handle, table_name, byref(table_handle), byref(self.error_info)
        )

        for row in rows:
            struct_handle = self.sap_lib.RfcAppendNewRow(
                table_handle, byref(self.error_info)
            )

            for field, value in row.items():
                if isinstance(value, list):
                    self._fill_nested_table(struct_handle, field, value)
                else:
                    self.sap_lib.RfcSetString(
                        struct_handle,
                        field,
                        str(value),
                        len(str(value)),
                        byref(self.error_info),
                    )

    def _fill_nested_table(
        self, parent_handle, table_field_name, rows, level=1, max_level=3
    ):
        if level > max_level:
            return

        table_handle = self.RFC_TABLE_HANDLE()
        rc = self.sap_lib.RfcGetTable(
            parent_handle, table_field_name, byref(table_handle), byref(self.error_info)
        )
        if rc != 0:
            return

        for row in rows:
            struct_handle = self.sap_lib.RfcAppendNewRow(
                table_handle, byref(self.error_info)
            )
            for field, value in row.items():
                if isinstance(value, list):
                    self._fill_nested_table(
                        struct_handle, field, value, level + 1, max_level
                    )
                else:
                    self.sap_lib.RfcSetString(
                        struct_handle,
                        field,
                        str(value),
                        len(str(value)),
                        byref(self.error_info),
                    )

    # ===============================
    # Extraction
    # ===============================

    def extract_table_data(
        self, func_handle, table_name, fields, buffer_size=512, nested_fields=None
    ):
        table_handle = self.RFC_TABLE_HANDLE()
        rc = self.sap_lib.RfcGetTable(
            func_handle, table_name, byref(table_handle), byref(self.error_info)
        )
        if rc != 0:
            return []

        row_count = c_ulong()
        self.sap_lib.RfcGetRowCount(
            table_handle, byref(row_count), byref(self.error_info)
        )

        result = []
        for i in range(row_count.value):
            if i > 0:
                self.sap_lib.RfcMoveToNextRow(
                    table_handle, byref(self.error_info)
                )

            row = {}
            for field in fields or []:
                buffer = create_unicode_buffer(buffer_size)
                length = c_ulong()
                self.sap_lib.RfcGetString(
                    table_handle,
                    field,
                    buffer,
                    buffer_size,
                    byref(length),
                    byref(self.error_info),
                )
                row[field] = buffer.value

            if nested_fields:
                current = self.sap_lib.RfcGetCurrentRow(
                    table_handle, byref(self.error_info)
                )
                for nested_table, nested_cols in nested_fields.items():
                    row[nested_table] = self._extract_nested_table(
                        current, nested_table, nested_cols
                    )

            result.append(row)

        return result

    def _extract_nested_table(self, struct_handle, table_name, fields):
        table_handle = self.RFC_TABLE_HANDLE()
        rc = self.sap_lib.RfcGetTable(
            struct_handle, table_name, byref(table_handle), byref(self.error_info)
        )
        if rc != 0:
            return []

        row_count = c_ulong()
        self.sap_lib.RfcGetRowCount(
            table_handle, byref(row_count), byref(self.error_info)
        )

        result = []
        for i in range(row_count.value):
            if i > 0:
                self.sap_lib.RfcMoveToNextRow(
                    table_handle, byref(self.error_info)
                )

            row = {}
            for field in fields:
                buffer = create_unicode_buffer(512)
                length = c_ulong()
                self.sap_lib.RfcGetString(
                    table_handle,
                    field,
                    buffer,
                    512,
                    byref(length),
                    byref(self.error_info),
                )
                row[field] = buffer.value

            result.append(row)

        return result

    # ===============================
    # Utils
    # ===============================

    def _format_error(self, operation):
        return (
            f"SAP RFC error during {operation}: "
            f"{self.error_info.code} - {self.error_info.message}"
        )
