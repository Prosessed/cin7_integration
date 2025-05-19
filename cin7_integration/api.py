from frappe import _
import frappe
import requests
import json
from cin7_integration.cin7_integration.doctype.cin7_settings.cin7_settings import Cin7Settings


def get_cin7_items(page=1, limit=50):
    """
    Fetches a paginated list of items from CIN7 Core (Dear Systems)
    and returns the 'Products' list as dictionaries.
    """
    cin7 = frappe.get_single("CIN7 Settings")
    url = f"https://inventory.dearsystems.com/ExternalApi/Products?Page={page}&Limit={limit}"

    try:
        res = cin7._get(url)
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), _("CIN7 Items Fetch Failed"))
        frappe.throw(_("Failed to fetch items from CIN7."))

    if isinstance(res, dict) and "Products" in res:
        frappe.logger().info(f"Fetched {len(res['Products'])} CIN7 items from page {page}")
        return res["Products"]

    frappe.log_error(json.dumps(res, indent=2), "Unexpected CIN7 Response Structure")
    frappe.throw(_("Unexpected response from CIN7. Check API credentials or response format."))




def get_cin7_customers(page=1, limit=50):
    """
    Fetches a paginated list of customers from CIN7 Core (Dear Systems)
    and returns the 'Customers' list as dictionaries.
    """
    cin7 = frappe.get_single("CIN7 Settings")
    url = f"https://inventory.dearsystems.com/ExternalApi/Customers?Page={page}&Limit={limit}"

    try:
        res = cin7._get(url)
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), _("CIN7 Customers Fetch Failed"))
        frappe.throw(_("Failed to fetch customers from CIN7."))

    if isinstance(res, dict) and "Customers" in res:
        frappe.logger().info(f"Fetched {len(res['Customers'])} CIN7 customers from page {page}")
        return res["Customers"]

    frappe.log_error(json.dumps(res, indent=2), "Unexpected CIN7 Response Structure")
    frappe.throw(_("Unexpected response from CIN7. Check API credentials or response format."))



def get_cin7_item_groups():

    """
    Fetches a list of item groups from CIN7 Core (Dear Systems)
    and returns the 'ItemGroups' list as dictionaries.
    """
    cin7 = frappe.get_single("CIN7 Settings")
    url = "https://inventory.dearsystems.com/ExternalApi/v2/ref/category?"

    try:
        res = cin7._get(url)
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), _("CIN7 Item Groups Fetch Failed"))
        frappe.throw(_("Failed to fetch item groups from CIN7."))

    if isinstance(res, dict) and "ItemGroups" in res:
        frappe.logger().info(f"Fetched {len(res['ItemGroups'])} CIN7 item groups")
        return res["ItemGroups"]

    frappe.log_error(json.dumps(res, indent=2), "Unexpected CIN7 Response Structure")
    frappe.throw(_("Unexpected response from CIN7. Check API credentials or response format."))
