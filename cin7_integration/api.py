import frappe
import requests
import json

from cin7_integration.cin7_integration.doctype.cin7_integration_log.cin7_integration_log import log_cin7



def create_sales_order_on_cin7(doc, method):
    # Step 1: Initiate order in CIN7
    initiate_sales_order_on_cin7(doc)

    # Step 2: Add line items to CIN7 order
    place_order_lines_on_cin7(doc)

def initiate_sales_order_on_cin7(doc):
    if doc.get("custom_is_synced"):
        frappe.msgprint("Sales Order is already synced with CIN7.")
        return

    cin7_settings = frappe.get_single("CIN7 Settings")
    api_url = "https://inventory.dearsystems.com/ExternalApi/v2/sale"
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
        "Type": "Simple Sale",
        "Status": "DRAFT",
        "SkipQuote": True,
        "SaleOrderDate": doc.delivery_date.strftime("%Y/%m/%d"),
        "TaxCalculation": "Inclusive"
    }

    try:
        response = requests.post(api_url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        data = response.json()

        if data.get("ID"):
            doc.db_set("custom_cin7_order_id", data["ID"])
            frappe.msgprint(f"Sales Order initiated in CIN7. ID: {data['ID']}")
            log_cin7('CIN7 INITIATE ORDER', 'POST', api_url, 'CIN7 INITIATE SUCCESS')
        else:
            frappe.throw("CIN7 API responded without Sale ID.")

    except Exception as e:
        error_message = response.text if 'response' in locals() else str(e)
        log_cin7('CIN7 INITIATE ORDER', 'POST', api_url, response=error_message[:140])
        frappe.log_error(f"Response from CIN7:\n{error_message}\n\nTraceback:\n{frappe.get_traceback()}", "CIN7 Initiate Order Failed")
        frappe.throw(f"Failed to initiate Sales Order in CIN7: {error_message}")


def place_order_lines_on_cin7(doc):
    if not doc.get("custom_cin7_order_id"):
        frappe.throw("No CIN7 Order ID found. Please initiate the order first.")

    cin7_settings = frappe.get_single("CIN7 Settings")
    api_url = "https://inventory.dearsystems.com/ExternalApi/v2/sale/order"
    headers = {
        "api-auth-accountid": cin7_settings.cin7_account_id,
        "api-auth-applicationkey": cin7_settings.cin7_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    payload = {
        "SaleID": doc.custom_cin7_order_id,
        "Status": "DRAFT",
        "Memo" : doc.custom_note,
        "Lines": []
    }

    for item in doc.items:

        tax_rule = item.item_tax_template.split(" - ")[0].strip() if item.item_tax_template else "Tax on Sales"

        tax_percentage = 0
        if tax_rule == "GST on Income":
            tax_percentage = 10
        elif tax_rule == "GST Free Income":
            tax_percentage = 0

        tax_amount = round((item.amount or 0) * tax_percentage / 100, 2)

        payload["Lines"].append({
            "SKU": item.item_code,
            "Quantity": item.qty,
            "Price": item.rate,
            "Total": item.amount,
            "TaxRule": tax_rule,
            "Tax": tax_amount
        })
    try:
        response = requests.post(api_url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        doc.db_set("custom_is_synced", 1)
        frappe.msgprint("Hurrah!, Sales Order pushed to CIN7.")
        log_cin7('CIN7 PLACE ORDER', 'POST', api_url, 'CIN7 ORDER SUCCESS')

    except Exception as e:
        error_message = response.text if 'response' in locals() else str(e)
        log_cin7('CIN7 PLACE ORDER', 'POST', api_url, response=error_message[:140])
        frappe.log_error(f"Response from CIN7:\n{error_message}\n\nTraceback:\n{frappe.get_traceback()}", "CIN7 Place Order Failed")
        frappe.throw(f"Failed to place Sales Order lines in CIN7: {error_message}")
