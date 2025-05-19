# Copyright (c) 2025, Jaspreet Singh Sodhi and contributors
# For license information, please see license.txt

import frappe
import requests
import json
from frappe import _
from frappe.model.document import Document

from cin7_integration.cin7_integration.doctype.cin7_integration_log.cin7_integration_log import log_cin7

class CIN7Settings(Document):

    def before_save(self):
        if not self.cin7_account_id or not self.cin7_api_key:
            frappe.throw("CIN7 Account ID and API Key are required fields.")

    def _get(self, *args, **kwargs):
        kwargs["headers"] = {
            "api-auth-accountid": self.cin7_account_id,
            "api-auth-applicationkey": self.cin7_api_key,
            "Accept": "application/json"
        }

        try:
            response = requests.get(*args, **kwargs)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "CIN7 API Request Failed")
            frappe.throw("Unable to reach CIN7. Please check your network or credentials.")

        if response.status_code != 200:
            try:
                error_body = response.json()
            except Exception:
                error_body = response.text
            frappe.log_error(json.dumps(error_body, indent=2), f"CIN7 GET Error {response.status_code}")
            frappe.throw(f"CIN7 API returned {response.status_code}: {error_body}")

        try:
            return response.json()
        except ValueError:
            frappe.log_error(response.text, "Invalid JSON from CIN7")
            frappe.throw("CIN7 returned an invalid or non-JSON response.")

    def _post(self, *args, **kwargs):
        kwargs["headers"] = {
            "api-auth-accountid": self.cin7_account_id,
            "api-auth-applicationkey": self.cin7_api_key,
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(*args, **kwargs)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "CIN7 API Request Failed")
            frappe.throw("Unable to reach CIN7. Please check your network or credentials.")

        if response.status_code != 200:
            try:
                error_body = response.json()
            except Exception:
                error_body = response.text
            frappe.log_error(json.dumps(error_body, indent=2), f"CIN7 POST Error {response.status_code}")
            frappe.throw(f"CIN7 API returned {response.status_code}: {error_body}")

        try:
            return response.json()
        except ValueError:
            frappe.log_error(response.text, "Invalid JSON from CIN7")
            frappe.throw("CIN7 returned an invalid or non-JSON response.")


# ------------------------
# Sync Methods
# ------------------------

@frappe.whitelist()
def sync_items():
    cin7 = frappe.get_single("CIN7 Settings")
    if not cin7.enable:
        frappe.throw("CIN7 Integration is not enabled.")

    items = get_cin7_items(cin7)
    frappe.msgprint(f"Fetched {len(items)} items from CIN7.")
    log_cin7(
        title="CIN7 Item Sync",
        method="GET",
        voucher_type="Item",
        url="https://inventory.dearsystems.com/ExternalApi/Products",
        status="Success",
        response=json.dumps(items, indent=2)
    )
    return items


@frappe.whitelist()
def sync_customers():
    cin7 = frappe.get_single("CIN7 Settings")
    if not cin7.enable:
        frappe.throw("CIN7 Integration is not enabled.")

    customers = get_cin7_customers(cin7)
    frappe.msgprint(f"Fetched {len(customers)} customers from CIN7.")
    log_cin7(
        title="CIN7 Customer Sync",
        method="GET",
        url="https://inventory.dearsystems.com/ExternalApi/Customers",
        status="Success",
        response=json.dumps(customers, indent=2)
    )
    return customers

@frappe.whitelist()
def sync_item_groups():
    cin7 = frappe.get_single("CIN7 Settings")
    if not cin7.enable:
        frappe.throw("CIN7 Integration is not enabled.")

    groups = get_cin7_item_groups(cin7)
    frappe.msgprint(f"Fetched {len(groups)} categories from CIN7.")
    log_cin7(
        title="CIN7 Item Group Sync",
        method="GET",
        url="https://inventory.dearsystems.com/ExternalApi/v2/ref/category",
        status="Success",
        response=json.dumps(groups, indent=2)
    )
    return f"Fetched {len(groups)} item groups from CIN7."


# ------------------------
# API CALLS (Internal)
# ------------------------

def get_cin7_items(cin7, page=1, limit=50):
    url = f"https://inventory.dearsystems.com/ExternalApi/Products?Page={page}"
    res = cin7._get(url)
    if isinstance(res, dict) and "Products" in res:
        frappe.logger().info(f"Fetched {len(res['Products'])} CIN7 items from page {page}")
        return res["Products"]
    frappe.throw("Unexpected CIN7 item response format.")


def get_cin7_customers(cin7, page=1, limit=50):
    url = f"https://inventory.dearsystems.com/ExternalApi/Customers?Page={page}"
    res = cin7._get(url)
    if isinstance(res, dict) and "Customers" in res:
        frappe.logger().info(f"Fetched {len(res['Customers'])} CIN7 customers from page {page}")
        return res["Customers"]
    frappe.throw("Unexpected CIN7 customer response format.")


def get_cin7_item_groups(cin7):
    url = "https://inventory.dearsystems.com/ExternalApi/v2/ref/category?"
    res = cin7._get(url)
    if isinstance(res, dict) and "CategoryList" in res:
        frappe.logger().info(f"Fetched {len(res['CategoryList'])} CIN7 item groups")

        return res["CategoryList"]




    frappe.throw("Unexpected CIN7 item group response format.")
