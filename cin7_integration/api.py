import frappe
import requests
import json

from cin7_integration.cin7_integration.doctype.cin7_integration_log.cin7_integration_log import log_cin7

def create_sales_order_on_cin7(doc, method):
    if doc.get("custom_is_synced"):
        frappe.msgprint("Sales Order is already synced with CIN7.")
        return

    cin7_settings = frappe.get_single("CIN7 Settings")
    api_url = "https://inventory.dearsystems.com/ExternalApi/Sale"
    headers = {
        "api-auth-accountid": cin7_settings.cin7_account_id,
        "api-auth-applicationkey": cin7_settings.cin7_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    customer_id = frappe.db.get_value("Customer", doc.customer, "custom_cin7_customer_id")
    payload = {
        "Customer": doc.customer_name,
        "CustomerID": customer_id,
        "Location": "Main Warehouse",
        "OrderDate": doc.delivery_date.strftime("%Y/%m/%d"),
        "Note": doc.custom_note or "",
        # "SalesRepresentative": doc.custom_sales_rep,
        "Lines": []
    }

    for item in doc.items:
        payload["Lines"].append({
            "SKU": item.item_name,
            "Quantity": item.qty,
            "Price": item.rate,
            "Total": item.amount,
            "TaxRule": "Tax on Sales"
        })

    try:
        response = requests.post(api_url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        data = response.json()

        if data.get("SaleID") or data.get("ID"):

            doc.db_set("custom_cin7_order_id", data.get("ID"))
            doc.db_set("custom_is_synced", 1)
            frappe.msgprint(f"Sales Order synced with CIN7. Order ID: {data.get('ID')}")
            log_cin7(
            'CIN7 SALES ORDER SYNC',
            'POST',
             api_url,
            "CIN7 API SUCCESS"
        )

        else:
            frappe.throw("CIN7 API responded without SaleID.")

    except Exception as e:
        error_message = response.text if 'response' in locals() else str(e)
        log_cin7(
            'CIN7 SALES ORDER SYNC',
            'POST',
            api_url,
            response = error_message[:140]
        )
        frappe.log_error(f"Response from CIN7:\n{error_message}\n\nTraceback:\n{frappe.get_traceback()}", "CIN7 Sales Order Sync Failed")
        frappe.throw(f"Failed to sync Sales Order with CIN7: {error_message}")
