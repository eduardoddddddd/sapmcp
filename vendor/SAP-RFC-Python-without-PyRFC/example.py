from sap_rfc_connector import SapRFCConnector

# Initialize connector
sap = SapRFCConnector(dll_directory="C:/nwrfcsdk/lib")

# Connect to SAP
sap.connect()

# Call RFC function
result = sap.call_function(
    "ZMFTEST_GET_CONDICAO_PAGAMENTO",
    tables=["ET_RESPONSE"],
    table_fields={
        "ET_RESPONSE": [
            "ZTERM",
            "TEXT1",
            "ZTAG1",
            "RATPZ",
            "STATUS"
        ]
    }
)

# Print first results
for item in result["ET_RESPONSE"][:5]:
    print(item)

# Close connection
sap.disconnect()
