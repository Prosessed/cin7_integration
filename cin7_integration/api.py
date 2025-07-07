from click import DateTime
import frappe
import requests
import json
from frappe.utils import now_datetime, add_days
from datetime import datetime
from cin7_integration.cin7_integration.doctype.cin7_integration_log.cin7_integration_log import log_cin7


def auto_sync_on_submit(doc, method):
    try:
        if not doc.custom_cin7_sale_id and not doc.custom_cin7_order_id:
            if doc.workflow_state == "Reviewing":
                doc.submit()
                frappe.enqueue(sync_sales_order_to_cin7, queue='default', doc=doc)

    except Exception as e:
        frappe.log_error(f"CIN7 Auto Sync Failed on Submit for {doc.name}: {str(e)}")
        frappe.throw(f"Failed to sync Sales Order with CIN7: {str(e)}")


def sync_sales_order_to_cin7(doc):
    doc = frappe.get_doc("Sales Order", doc.name)
    if not doc.custom_cin7_order_id:
        create_sales_order_on_cin7(doc, method=None)


def create_sales_order_on_cin7(doc, method):
    sale_id = initiate_sales_order_on_cin7(doc)
    if not sale_id:
        return

    # Step 2: Add line items to CIN7 order
    place_order_lines_on_cin7(doc, sale_id=sale_id)

def initiate_sales_order_on_cin7(doc):
    if doc.get("custom_is_synced"):
        frappe.msgprint("Sales Order is already synced with CIN7.")
        return None

    if doc.get("custom_cin7_sale_id") is not None:
        frappe.msgprint('Sales Order Already there on CIN7')
        doc.workflow_state = 'Invoiced'
        frappe.db.commit()
        return None

    cin7_settings = frappe.get_single("CIN7 Settings")
    api_url = "https://inventory.dearsystems.com/ExternalApi/v2/sale"
    headers = {
        "api-auth-accountid": cin7_settings.cin7_account_id,
        "api-auth-applicationkey": cin7_settings.cin7_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    customer_id = frappe.db.get_value("Customer", doc.customer, "custom_cin7_customer_id")
    delivery_date = doc.delivery_date
    delivery_date_obj = datetime.strptime(delivery_date, "%Y-%m-%d").date() if isinstance(delivery_date, str) else delivery_date

    payload = {
        "Customer": doc.customer_name,
        "CustomerID": customer_id,
        "Location": "Main Warehouse",
        "Type": "Simple Sale",
        "Status": "DRAFT",
        "SkipQuote": True,
        # "SaleOrderDate": doc.delivery_date.strftime("%Y/%m/%d"),
        "SaleOrderDate": delivery_date_obj.strftime("%Y/%m/%d"),
        "TaxCalculation": "Inclusive"
    }

    try:
        response = requests.post(api_url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        data = response.json()

        if data.get("ID"):
            sale_id = data["ID"]
            doc.db_set("custom_cin7_order_id", sale_id)
            frappe.msgprint(f"Sales Order initiated in CIN7. ID: {sale_id}")
            log_cin7('CIN7 INITIATE ORDER', 'POST', api_url, 'CIN7 INITIATE SUCCESS')
            return sale_id
        else:
            frappe.throw("CIN7 API responded without Sale ID.")

    except Exception as e:
        error_message = response.text if 'response' in locals() else str(e)
        log_cin7('CIN7 INITIATE ORDER', 'POST', api_url, response=error_message[:140])
        frappe.log_error(f"Response from CIN7:\n{error_message}\n\nTraceback:\n{frappe.get_traceback()}", "CIN7 Initiate Order Failed")
        frappe.throw(f"Failed to initiate Sales Order in CIN7: {error_message}")

def place_order_lines_on_cin7(doc, sale_id=None):
    sale_id = sale_id or doc.custom_cin7_order_id
    if not sale_id:
        frappe.throw("Missing SaleID. Cannot place order lines.")

    cin7_settings = frappe.get_single("CIN7 Settings")
    api_url = "https://inventory.dearsystems.com/ExternalApi/v2/sale/order"
    headers = {
        "api-auth-accountid": cin7_settings.cin7_account_id,
        "api-auth-applicationkey": cin7_settings.cin7_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    payload = {
        "SaleID": sale_id,
        "Status": "DRAFT",
        "Memo": doc.custom_note,
        "Lines": []
    }

    for item in doc.items:
        tax_rule = item.item_tax_template.split(" - ")[0].strip() if item.item_tax_template else "Tax on Sales"
        tax_percentage = 10 if tax_rule == "GST on Income" else 0
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



def create_erpnext_sales_order_from_cin7(sale_data: dict) -> str | None:
    try:
        sale_id = sale_data.get("SaleID")
        if frappe.db.exists("Sales Order", {"custom_cin7_sale_id": sale_id}):
            frappe.logger().info(f"[SKIP] Sales Order already exists for CIN7 SaleID: {sale_id}")
            return None

        customer_name = sale_data.get("Customer")
        frappe.logger().info(f"[DEBUG] Customer in sale_data: {customer_name}")

        if not customer_name or not frappe.db.exists("Customer", customer_name):
            frappe.log_error(f"Missing or unknown customer: {customer_name}")
            return None

        doc = frappe.new_doc("Sales Order")
        doc.naming_series = "SO-"
        doc.customer = customer_name


        order_date_str = sale_data.get("OrderDate")
        order_date = datetime.fromisoformat(order_date_str).date() if order_date_str else None

        if not order_date:
            frappe.logger().error(f"[ERROR] Invalid or missing Order Date from CIN7 for SaleID: {sale_id} & order_date_str: {order_date_str}")

            frappe.throw("Invalid or missing Order Date from CIN7")

        doc.transaction_date = sale_data.get("OrderDate")
        doc.delivery_date = add_days(doc.transaction_date, 1)
        doc.po_no = sale_data.get("SaleOrderNumber")
        doc.custom_cin7_sale_id = sale_id
        doc.base_total = sale_data.get("TotalBeforeTax") or 0
        doc.total_taxes_and_charges = sale_data.get("Tax") or 0
        doc.total = sale_data.get("Total") or 0
        doc.taxes_and_charges = None

        for line in sale_data.get("Lines", []):
            doc.append("items", {
                "item_code": line.get("SKU"),
                "item_name": line.get("Name"),
                "description": line.get("Comment") or line.get("Name"),
                "qty": line.get("Quantity"),
                "rate": line.get("Price"),
                "discount_percentage": (line["Discount"] / line["Price"]) * 100 if line.get("Price") else 0,
            })

        doc.insert(ignore_permissions=True)
        doc.submit()
        frappe.db.commit()
        return doc.name

    except Exception as e:
        frappe.log_error(
            title="Sales Order Sync Failed",
            message=f"Error creating Sales Order for {sale_data.get('SaleOrderNumber')}: {str(e)}"
        )
        return None




def get_cin7_sale_ids(saleStatus: str, start_page: int = 1) -> list:
    cin7_settings = frappe.get_single("CIN7 Settings")
    base_url = "https://inventory.dearsystems.com/ExternalApi/v2/saleList"

    headers = {
        "api-auth-accountid": cin7_settings.cin7_account_id,
        "api-auth-applicationkey": cin7_settings.cin7_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    sale_list = []
    page = start_page

    try:
        while True:
            url = f"{base_url}?Page={page}&Status={saleStatus}"
            response = requests.get(url, headers=headers)

            if response.status_code != 200:
                frappe.log_error(f"CIN7 API Error: {response.status_code} - {response.text}")
                break

            data = response.json()
            sales = data.get("SaleList", [])
            total = data.get("Total", 0)

            for sale in sales:
                sale_list.append({
                    "SaleID": sale.get("SaleID"),
                    "Customer": sale.get("Customer"),
                    "OrderDate": sale.get("OrderDate")
                })

            if page * 100 >= total:
                break

            page += 1

        return sale_list

    except Exception as e:
        frappe.log_error(f"Error occurred while fetching sales ID - {str(e)}")
        return []


def get_cin7_sale_order_details(sale_id: str) -> dict | None:
    try:
        cin7_settings = frappe.get_single("CIN7 Settings")
        url = f"https://inventory.dearsystems.com/ExternalApi/v2/sale/order?SaleID={sale_id}"

        headers = {
            "api-auth-accountid": cin7_settings.cin7_account_id,
            "api-auth-applicationkey": cin7_settings.cin7_api_key,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()

    except Exception as e:
        frappe.log_error(f"Error fetching CIN7 order {sale_id}: {str(e)}")
        return None
