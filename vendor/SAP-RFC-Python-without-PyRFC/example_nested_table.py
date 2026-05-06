import os
import logging
from datetime import datetime, timedelta
from sap_rfc_connector import SapRFCConnector

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    # Instantiate the SAP connector
    sap_connector = SapRFCConnector()

    try:
        # Connect to SAP (example connection)
        sap_connector.connect()
        logger.info("Successfully connected to SAP")

        # Calculate dates for parameters (last 180 days - example)
        current_date = datetime.now()
        start_date = current_date - timedelta(days=180)
        date_to = current_date.strftime('%Y%m%d')
        date_from = start_date.strftime('%Y%m%d')

        # Parameters for the RFC function for items (example parameters)
        params = {
            "IV_DELTA": "X",
            "IV_ITEM": "X",
            "IV_DATE_FROM": date_from,
            "IV_DATE_TO": date_to
        }

        # Expected fields from the ET_ITEM table (example fields)
        item_fields = [
            "MATNR", "MAKTX", "MEINS", "MEINH", "STEUC", "BRGEW", "UMREZ",
            "TIPO", "STATUS", "CARACTERISTICA", "WERKS", "KONTS", "MEINS_SEM_EXIT", "BSTME"
        ]

        # Call the RFC function to fetch items (example call)
        # Assuming there might be nested tables in WERKS or others, but for this example, we focus on the main table
        result = sap_connector.call_function(
            function_name="ZMFTEST_COMPOSE_ITEM",
            tables=["ET_ITEM"],  # Main output table
            table_fields={"ET_ITEM": item_fields},  # Table fields
            nested_fields={},  # If there are nested tables, add here, e.g., {"ET_BRANCHES": ["WERKS"]}
            **params
        )

        # Check result (example result processing)
        if "ET_ITEM" in result:
            items = result["ET_ITEM"]
            logger.info(f"Total items extracted: {len(items)}")

            # Display first 5 items as example (sample data)
            for i, item in enumerate(items[:5]):
                logger.info(f"Item {i+1}: MATNR={item.get('MATNR', 'SAMPLE123')}, MAKTX={item.get('MAKTX', 'Sample Item Description')}, WERKS={item.get('WERKS', 'BRANCH1;BRANCH2')}")
        else:
            logger.warning("No data found in ET_ITEM table")

    except Exception as e:
        logger.error(f"Error during execution: {str(e)}")
    finally:
        # Disconnect
        sap_connector.disconnect()
        logger.info("Disconnected from SAP")

if __name__ == "__main__":
    main()