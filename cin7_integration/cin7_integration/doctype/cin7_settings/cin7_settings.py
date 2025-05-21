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



# --- Sync CIN7 Customers to ERPNext
@frappe.whitelist()
def sync_customers():
    cin7 = frappe.get_single("CIN7 Settings")
    if not cin7.enable:
        frappe.throw(_("CIN7 Integration is not enabled."))

    url = "https://inventory.dearsystems.com/ExternalApi/Customers"
    errors = []
    customers = []

    # Fetch CIN7 customers
    try:
        response = cin7._get(url)
        customers = response.get("Customers", [])
        if not isinstance(customers, list):
            raise ValueError("Invalid CIN7 response: 'Customers' is not a list.")
        frappe.logger().info(f"Fetched {len(customers)} customers from CIN7")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "CIN7 Customer Sync - Fetch Error")
        log_cin7(title="CIN7 Customer Sync - Fetch Error", method="GET", url=url, status="Failed", response=frappe.get_traceback())
        frappe.throw(_("Unable to fetch customers from CIN7."))

    for c in customers:
        try:
            customer_id = c.get("ID")
            customer_name = c.get("Name") or "Unnamed Customer"

            if not customer_id:
                continue

            # Create or update Customer
            customer_docname = frappe.db.exists("Customer", {"custom_cin7_customer_id": customer_id})
            customer = frappe.get_doc("Customer", customer_docname) if customer_docname else frappe.new_doc("Customer")

            updated_fields = {
                "customer_name": customer_name,
                "customer_type": "Company",
                "customer_group": "Commercial",
                "territory": "All Territories",
                "custom_cin7_customer_id": customer_id
            }

            customer.update(updated_fields)
            customer.save(ignore_permissions=True)

            # Insert or Update all addresses
            addresses = c.get("Addresses", [])
            valid_types = {"Billing", "Shipping"}

            for idx, addr in enumerate(addresses):
                addr_type = (addr.get("Type") or "").strip().title()
                if addr_type not in valid_types:
                    continue

                line1 = addr.get("Line1") or "Unknown Address Line 1"
                line2 = addr.get("Line2") or ""
                city = addr.get("City") or "Unknown City"
                state = addr.get("State") or ""
                pincode = addr.get("Postcode") or ""
                country = addr.get("Country") or "Australia"
                address_title = f"{customer_name}"

                addr_filter = {
                    "address_title": address_title,
                    "address_line1": line1,
                    "city": city,
                    "country": country
                }

                existing_address_name = frappe.db.exists("Address", addr_filter)
                if not existing_address_name:
                    # Insert new address
                    address = frappe.get_doc({
                        "doctype": "Address",
                        "address_title": address_title,
                        "address_type": addr_type,
                        "address_line1": line1,
                        "address_line2": line2,
                        "city": city,
                        "state": state,
                        "pincode": pincode,
                        "country": country,
                        "links": [{
                            "link_doctype": "Customer",
                            "link_name": customer.name
                        }]
                    })
                    address.insert(ignore_permissions=True)
                else:
                    # Update existing address if values differ
                    address = frappe.get_doc("Address", existing_address_name)
                    updated = False

                    if address.address_line2 != line2:
                        address.address_line2 = line2
                        updated = True
                    if address.state != state:
                        address.state = state
                        updated = True
                    if address.pincode != pincode:
                        address.pincode = pincode
                        updated = True
                    if address.address_type != addr_type:
                        address.address_type = addr_type
                        updated = True

                    if updated:
                        address.save(ignore_permissions=True)

            # Insert or Update all contacts
            contacts = c.get("Contacts", [])
            for idx, contact in enumerate(contacts):
                name = contact.get("Name") or f"{customer_name} Contact {idx+1}"
                phone = contact.get("Phone") or contact.get("MobilePhone") or ""
                email = contact.get("Email") or ""

                contact_key = {"first_name": name, "email_id": email}
                existing_contact_name = frappe.db.exists("Contact", contact_key)

                if not existing_contact_name:
                    # Insert new contact
                    contact_doc = frappe.get_doc({
                        "doctype": "Contact",
                        "first_name": name,
                        "email_ids": [{"email_id": email, "is_primary": 1}] if email else [],
                        "phone_nos": [{"phone": phone, "is_primary_phone": 1}] if phone else [],
                        "links": [{
                            "link_doctype": "Customer",
                            "link_name": customer.name
                        }]
                    })
                    contact_doc.insert(ignore_permissions=True)
                else:
                    # Update existing contact if phone/email changed
                    contact_doc = frappe.get_doc("Contact", existing_contact_name)
                    updated = False

                    if email and (not contact_doc.email_ids or contact_doc.email_ids[0].email_id != email):
                        contact_doc.email_ids = [{"email_id": email, "is_primary": 1}]
                        updated = True
                    if phone and (not contact_doc.phone_nos or contact_doc.phone_nos[0].phone != phone):
                        contact_doc.phone_nos = [{"phone": phone, "is_primary_phone": 1}]
                        updated = True

                    if updated:
                        contact_doc.save(ignore_permissions=True)

        except Exception:
            msg = f"Failed to sync customer: {c.get('Name')}"
            errors.append(msg)
            frappe.log_error(frappe.get_traceback(), msg)

    # Final log
    status = "Success" if not errors else "Partial Success"
    log_cin7(
        title="CIN7 Customer Sync",
        method="GET",
        url=url,
        status=status,
        response=json.dumps(customers if not errors else {"errors": errors}, indent=2)
    )

    if errors:
        frappe.msgprint(title="CIN7 Customer Sync - Issues Found", msg="<br>".join(errors), indicator='orange')
    else:
        frappe.msgprint(f"Successfully synced {len(customers)} customers from CIN7.")

    return f"{status}: {len(customers)} customers processed"



# --- Sync CIN7 Items to ERPNext
@frappe.whitelist()
def sync_items():
    """Sync CIN7 items to ERPNext"""
    cin7 = frappe.get_single("CIN7 Settings")
    if not cin7.enable:
        frappe.throw(_("CIN7 Integration is not enabled."))

    url = "https://inventory.dearsystems.com/ExternalApi/Products?Page=1"
    errors = []
    items = []

    # Fetch CIN7 Items
    try:
        res = cin7._get(url)
        if isinstance(res, dict) and "Products" in res:
            items = res["Products"]
            frappe.logger().info(f"Fetched {len(items)} CIN7 items")
        else:
            raise ValueError("Invalid CIN7 response format.")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "CIN7 Item Sync - Fetch Error")
        log_cin7(title="CIN7 Item Sync - Fetch Error", method="GET", url=url, status="Failed", response=frappe.get_traceback())
        frappe.throw(_("Unable to fetch items from CIN7."))

    # Create or Update Items
    for item_data in items:
        item_id = item_data.get("ID")
        item_name = item_data.get("Name")

        if not item_id:
            continue

        try:
            brand = item_data.get("Brand")
            uom = item_data.get("UOM")

            # create brand if not exists
            if brand and not frappe.db.exists("Brand", brand):
                frappe.get_doc({
                    "doctype": "Brand",
                    "brand": brand
                }).insert(ignore_permissions=True)

            # create uom if not exists
            if uom and not frappe.db.exists("UOM", uom):
                frappe.get_doc({
                    "doctype": "UOM",
                    "uom_name": uom,
                }).insert(ignore_permissions=True)

            existing_item = frappe.db.exists("Item", item_id)

            if not existing_item:
                # insert new item
                item = frappe.get_doc({
                    "doctype": "Item",
                    "item_code": item_id,
                    "custom_cin7_item_id": item_id,
                    "brand": brand,
                    "item_name": item_name,
                    "description": item_data.get("Description"),
                    "custom_publish_on_app": 1,
                    "item_group": item_data.get("Category") or "All Item Groups",
                    "stock_uom": item_data.get("UOM"),
                })
                item.insert(ignore_permissions=True)
            else:
                # update existing item
                item = frappe.get_doc("Item", item_id)
                updated = False

                if item.item_name != item_name:
                    item.item_name = item_name
                    updated = True
                if item.description != item_data.get("Description"):
                    item.description = item_data.get("Description")
                    updated = True
                if item.brand != brand:
                    item.brand = brand
                    updated = True
                if item.stock_uom != item_data.get("UOM"):
                    item.stock_uom = item_data.get("UOM")
                    updated = True
                if item.item_group != (item_data.get("Category") or "All Item Groups"):
                    item.item_group = item_data.get("Category") or "All Item Groups"
                    updated = True

                if updated:
                    item.save(ignore_permissions=True)

            # Insert or Update Item Price
            if item_data.get("AverageCost"):
                if not frappe.db.exists("Item Price", {"item_code": item_id, "price_list": "Standard Selling"}):
                    frappe.get_doc({
                        "doctype": "Item Price",
                        "item_code": item_id,
                        "price_list": "Standard Selling",
                        "price_list_rate": item_data.get("AverageCost")
                    }).insert(ignore_permissions=True)

        except Exception:
            msg = f"Failed to create/update Item: {item_name}"
            errors.append(msg)
            frappe.log_error(frappe.get_traceback(), msg)

    # Final log
    status = "Success" if not errors else "Partial Success"
    log_cin7(
        title="CIN7 Item Sync",
        method="GET",
        url=url,
        status=status,
        response=json.dumps(items if not errors else {"errors": errors}, indent=2)
    )

    if errors:
        frappe.msgprint(title="CIN7 Item Sync - Issues Found", msg="<br>".join(errors), indicator='orange')
    else:
        frappe.msgprint(f"Successfully processed {len(items)} CIN7 items.")

    return f"{status}: {len(items)} items processed"


# ------------ Item Group Sync -----------
@frappe.whitelist()
def sync_item_groups():
    """Sync CIN7 item groups to ERPNext"""
    cin7 = frappe.get_single("CIN7 Settings")
    if not cin7.enable:
        frappe.throw(_("CIN7 Integration is not enabled."))

    url = "https://inventory.dearsystems.com/ExternalApi/v2/ref/category"
    errors = []
    groups = []

    # Fetch from CIN7
    try:
        response = cin7._get(url)
        if isinstance(response, dict) and "CategoryList" in response:
            groups = response["CategoryList"]
            frappe.logger().info(f"Fetched {len(groups)} CIN7 item groups")
        else:
            raise ValueError("Invalid CIN7 response format.")
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "CIN7 Item Group Sync - Fetch Error")
        log_cin7(title="CIN7 Item Group Sync - Fetch Error", method="GET", url=url, status="Failed", response=frappe.get_traceback())
        frappe.throw(_("Unable to fetch item groups from CIN7."))

    # Create or Update in ERPNext
    for group in groups:
        name = group.get("Name")
        if not name:
            continue

        try:
            existing_group = frappe.db.exists("Item Group", {"item_group_name": name})

            if not existing_group:
                frappe.get_doc({
                    "doctype": "Item Group",
                    "item_group_name": name,
                    "is_group": 0
                }).insert(ignore_permissions=True)
            else:
                doc = frappe.get_doc("Item Group", name)
                if doc.is_group != 0:
                    doc.is_group = 0
                    doc.save(ignore_permissions=True)

        except Exception:
            msg = f"Failed to create/update Item Group: {name}"
            errors.append(msg)
            frappe.log_error(frappe.get_traceback(), msg)

    status = "Success" if not errors else "Partial Success"
    log_cin7(
        title="CIN7 Item Group Sync",
        method="GET",
        url=url,
        status=status,
        response=json.dumps(groups if not errors else {"errors": errors}, indent=2)
    )

    if errors:
        frappe.msgprint(title="CIN7 Item Group Sync - Issues Found", msg="<br>".join(errors), indicator='orange')
    else:
        frappe.msgprint(f"Successfully processed {len(groups)} item groups from CIN7.")

    return f"{status}: {len(groups)} groups processed"

