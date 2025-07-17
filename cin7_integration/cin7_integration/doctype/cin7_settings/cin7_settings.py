# Copyright (c) 2025, Jaspreet Singh Sodhi and contributors
# For license information, please see license.txt

import datetime
from cin7_integration.api import create_erpnext_sales_order_from_cin7, get_cin7_sale_ids, get_cin7_sale_order_details
import frappe
import requests
import json
from frappe.utils import now_datetime, add_days
from frappe import _
from frappe.model.document import Document
from frappe.utils import nowdate, nowtime

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
    import re
    import json

    cin7 = frappe.get_single("CIN7 Settings")
    if not cin7.enable:
        frappe.throw(_("CIN7 Integration is not enabled."))

    base_url = "https://inventory.dearsystems.com/ExternalApi/Customers"
    errors = []
    customers = []
    page = 1
    total = None

    try:
        while True:
            url = f"{base_url}?Page={page}"
            response = cin7._get(url)

            if total is None:
                total = response.get("Total", 0)

            page_customers = response.get("Customers", [])
            if not isinstance(page_customers, list):
                raise ValueError(f"Invalid CIN7 response format on page {page}")

            if not page_customers:
                break

            customers.extend(page_customers)
            frappe.logger().info(f"Fetched {len(page_customers)} customers from CIN7 page {page}")

            if len(customers) >= total:
                break

            page += 1

    except Exception:
        frappe.log_error(frappe.get_traceback(), "CIN7 Customer Sync - Fetch Error")
        log_cin7(title="CIN7 Customer Sync - Fetch Error", method="GET", url=base_url, status="Failed", response=frappe.get_traceback())
        frappe.throw(_("Unable to fetch customers from CIN7."))

    for c in customers:
        try:
            customer_id = c.get("ID")
            customer_name = c.get("Name") or "Unnamed Customer"
            if not customer_id:
                continue

            existing_customer_name = frappe.db.exists("Customer", {"custom_cin7_customer_id": customer_id})
            customer = frappe.get_doc("Customer", existing_customer_name) if existing_customer_name else frappe.new_doc("Customer")

            # Preserve customer_name if already exists
            updated_fields = {
                "customer_type": "Company",
                "customer_group": "Commercial",
                "territory": "All Territories",
                "custom_cin7_customer_id": customer_id,
                "default_price_list": c.get("PriceTier") or "Standard Selling",
            }
            if not existing_customer_name:
                updated_fields["customer_name"] = customer_name  # Set name only if new

            customer.update(updated_fields)
            customer.save(ignore_permissions=True)

            # --------------------
            # Address Handling
            # --------------------
            for addr in c.get("Addresses", []):
                addr_type = (addr.get("Type") or "").strip().title()
                if addr_type not in {"Billing", "Shipping"}:
                    continue

                line1 = addr.get("Line1") or "Unknown Address Line 1"
                line2 = addr.get("Line2") or ""
                city = addr.get("City") or "Unknown City"
                state = addr.get("State") or ""
                pincode = addr.get("Postcode") or ""
                country = addr.get("Country") or "Australia"
                address_title = customer.customer_name  # use existing name

                addr_filter = {
                    "address_title": address_title,
                    "address_line1": line1,
                    "city": city,
                    "country": country
                }

                existing_address_name = frappe.db.exists("Address", addr_filter)
                if not existing_address_name:
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
                        "links": [{"link_doctype": "Customer", "link_name": customer.name}]
                    })
                    address.insert(ignore_permissions=True)
                else:
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

            # --------------------
            # Contact Handling
            # --------------------
            for idx, contact in enumerate(c.get("Contacts", [])):
                name = contact.get("Name") or f"{customer.customer_name} Contact {idx+1}"
                phone = re.sub(r"[^\d+]", "", (contact.get("Phone") or contact.get("MobilePhone") or "").strip())
                phone = phone if re.match(r"^\+?\d{8,15}$", phone) else ""
                email = (contact.get("Email") or "").strip()

                if not phone and not email:
                    continue

                contact_key = {"first_name": name, "email_id": email}
                existing_contact_name = frappe.db.exists("Contact", contact_key)

                if not existing_contact_name:
                    contact_doc = frappe.get_doc({
                        "doctype": "Contact",
                        "first_name": name,
                        "email_ids": [{"email_id": email, "is_primary": 1}] if email else [],
                        "phone_nos": [{"phone": phone, "is_primary_phone": 1}] if phone else [],
                        "links": [{"link_doctype": "Customer", "link_name": customer.name}]
                    })
                    contact_doc.insert(ignore_permissions=True)
                else:
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

    # --------------------
    # Final Logging
    # --------------------
    status = "Success" if not errors else "Failure"
    log_cin7(
        title="CIN7 Customer Sync",
        method="GET",
        url=base_url,
        status=status,
        response=json.dumps(customers if not errors else {"errors": errors}, indent=2)
    )

    if errors:
        frappe.msgprint(title="CIN7 Customer Sync - Issues Found", msg="<br>".join(errors), indicator='orange')
    else:
        frappe.msgprint(f"Successfully synced {len(customers)} customers from CIN7.")

    return f"{status}: {len(customers)} customers processed"



@frappe.whitelist()
def sync_items():
    """Sync CIN7 items to ERPNext (with proper pagination using 'Total')"""
    cin7 = frappe.get_single("CIN7 Settings")
    if not cin7.enable:
        frappe.throw(_("CIN7 Integration is not enabled."))

    base_url = "https://inventory.dearsystems.com/ExternalApi/Products"
    errors = []
    items = []
    page = 1
    total = None

    try:
        while True:
            url = f"{base_url}?Page={page}"
            response = cin7._get(url)

            if total is None:
                total = response.get("Total", 0)

            page_items = response.get("Products", [])
            if not isinstance(page_items, list):
                raise ValueError(f"Invalid CIN7 response format on page {page}")

            items.extend(page_items)
            frappe.logger().info(f"Fetched {len(page_items)} items from CIN7 page {page}")

            if len(items) >= total:
                break

            page += 1

        frappe.logger().info(f"Total CIN7 items fetched: {len(items)}")

        for item_data in items:
            try:
                _process_cin7_item(item_data)
            except Exception:
                item_code = (item_data.get("SKU") or item_data.get("ID") or "").strip()
                msg = f"Failed to process item: {item_code}"
                errors.append(msg)
                frappe.log_error(frappe.get_traceback(), msg)

        status = "Success" if not errors else "Failure"
        log_cin7(
            title="CIN7 Item Sync",
            method="GET",
            url=base_url,
            status=status,
            response=json.dumps(items if not errors else {"errors": errors}, indent=2)
        )

        if errors:
            frappe.msgprint(title="CIN7 Item Sync - Issues Found", msg="<br>".join(errors), indicator='orange')
        else:
            frappe.msgprint(f"Successfully processed {len(items)} CIN7 items.")

        return f"{status}: {len(items)} items processed"

    except Exception:
        frappe.log_error(frappe.get_traceback(), "CIN7 Item Sync - Fetch Error")
        log_cin7(title="CIN7 Item Sync - Fetch Error", method="GET", url=base_url, status="Failed", response=frappe.get_traceback())
        frappe.throw(_("Unable to fetch items from CIN7."))

def _process_cin7_item(item_data):
    cin7_item_id = item_data.get("ID")
    item_code = (item_data.get("SKU") or cin7_item_id).strip()
    item_name = item_data.get("Name")

    if not cin7_item_id:
        return

    brand = item_data.get("Brand")
    uom = item_data.get("UOM")
    category = item_data.get("Category") or "All Item Groups"
    description = item_data.get("Description")
    item_tax_template = item_data.get("SaleTaxRule")

    # Ensure Brand
    if brand and not frappe.db.exists("Brand", brand):
        frappe.get_doc({"doctype": "Brand", "brand": brand}).insert(ignore_permissions=True)

    # Ensure UOM
    if uom:
        uom = uom.strip().title()
        if not frappe.db.exists("UOM", {"uom_name": uom}):
            frappe.get_doc({"doctype": "UOM", "uom_name": uom}).insert(ignore_permissions=True)

    item_name_in_db = frappe.get_value("Item", {"custom_cin7_item_id": cin7_item_id}, "name")

    if not item_name_in_db:
        item = frappe.get_doc({
            "doctype": "Item",
            "item_code": item_code,
            "custom_cin7_item_id": cin7_item_id,
            "brand": brand,
            "item_name": item_name,
            "description": description,
            "custom_publish_on_app": 1,
            "item_group": category,
            "has_batch_no": 1,
            "create_new_batch": 1,
            "stock_uom": uom,
        })
        item.insert(ignore_permissions=True)
        create_item_tax_template(item, item_tax_template)
    else:
        item = frappe.get_doc("Item", item_name_in_db)
        updated = False

        for field, value in {
            "item_name": item_name,
            "description": description,
            "brand": brand,
            "stock_uom": uom,
            "item_group": category
        }.items():
            if getattr(item, field) != value:
                setattr(item, field, value)
                updated = True

        if updated:
            item.save(ignore_permissions=True)

        create_item_tax_template(item, item_tax_template)

    # Handle Price Tiers
    price_tiers = item_data.get("PriceTiers", {})
    for tier_name, tier_price in price_tiers.items():
        if not tier_price or tier_price == 0:
            continue

        if not frappe.db.exists("Price List", tier_name):
            frappe.get_doc({
                "doctype": "Price List",
                "price_list_name": tier_name,
                "selling": 1,
                "enabled": 1
            }).insert(ignore_permissions=True)

        item_price_name = frappe.get_value("Item Price", {"item_code": item_code, "price_list": tier_name}, "name")
        if not item_price_name:
            frappe.get_doc({
                "doctype": "Item Price",
                "item_code": item_code,
                "price_list": tier_name,
                "price_list_rate": tier_price
            }).insert(ignore_permissions=True)
        else:
            item_price = frappe.get_doc("Item Price", item_price_name)
            if item_price.price_list_rate != tier_price:
                item_price.price_list_rate = tier_price
                item_price.save(ignore_permissions=True)

def create_item_tax_template(item_doc, item_tax_template):
    if item_tax_template not in ["GST on Income", "GST Free Income"]:
        return

    tax_rate = 10 if item_tax_template == "GST on Income" else 0
    company = frappe.defaults.get_user_default("Company")
    company_abbr = frappe.get_value("Company", company, "abbr")

    account_name = f"GST {tax_rate}% - {company_abbr}"
    parent_account = f"Duties and Taxes - {company_abbr}"

    if not frappe.db.exists("Account", account_name):
        frappe.get_doc({
            "doctype": "Account",
            "account_name": f"GST {tax_rate}%",
            "parent_account": parent_account,
            "company": company,
            "account_type": "Tax",
            "is_group": 0,
            "root_type": "Liability"
        }).insert(ignore_permissions=True)

    if not frappe.db.exists("Item Tax Template", {"title": item_tax_template, "company": company}):
        frappe.get_doc({
            "doctype": "Item Tax Template",
            "title": item_tax_template,
            "company": company,
            "taxes": [{
                "tax_type": account_name,
                "tax_rate": tax_rate
            }]
        }).insert(ignore_permissions=True)

    template_name = frappe.get_value("Item Tax Template", {
        "title": item_tax_template,
        "company": company
    }, "name")

    if isinstance(item_doc, str):
        item_doc = frappe.get_doc("Item", item_doc)

    item_doc.taxes = []
    item_doc.append("taxes", {
        "item_tax_template": template_name,
        "tax_type": account_name,
        "tax_rate": tax_rate
    })
    item_doc.item_tax_template = template_name
    item_doc.save(ignore_permissions=True)

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

    status = "Success" if not errors else "Failure"
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




# @frappe.whitelist()
# def sync_stock():
#     """Sync CIN7 stock with ERP via Stock Reconciliation. Always creates reconciliation, prevents duplicates, handles pagination."""

#     cin7 = frappe.get_single("CIN7 Settings")
#     if not cin7.enable:
#         frappe.throw(_("CIN7 Integration is not enabled."))

#     base_url = "https://inventory.dearsystems.com/ExternalApi/v2/ref/productavailability"
#     warehouse = "Melbourne Warehouse - IF-M"
#     total_items = None
#     page = 1
#     fetched_count = 0
#     reconciliation_map = {}  # Key: item_code::warehouse, Value: total qty

#     try:
#         while True:
#             url = f"{base_url}?Page={page}"
#             response = cin7._get(url)

#             if total_items is None:
#                 total_items = response.get("Total", 0)

#             stocks = response.get("ProductAvailabilityList", [])
#             if not isinstance(stocks, list):
#                 frappe.log_error(f"[CIN7] Invalid response format at Page {page}", "[CIN7] sync_stock")
#                 frappe.throw(_("Invalid CIN7 response format."))

#             if not stocks:
#                 break

#             for stock in stocks:
#                 sku = stock.get("SKU")
#                 if not sku:
#                     continue

#                 cin7_qty = float(stock.get("Available") or 0)
#                 item_code = frappe.db.get_value("Item", {"item_code": sku})

#                 if not item_code:
#                     continue

#                 key = f"{item_code}::{warehouse}"

#                 if key not in reconciliation_map:
#                     reconciliation_map[key] = {
#                         "item_code": item_code,
#                         "warehouse": warehouse,
#                         "qty": 0
#                     }

#                 reconciliation_map[key]["qty"] += cin7_qty  # Sum StockOnHand for same item

#             fetched_count += len(stocks)
#             if fetched_count >= total_items:
#                 break

#             page += 1

#         reconciliation_items = list(reconciliation_map.values())
#         if not reconciliation_items:
#             return "No matching items found. No Stock Reconciliation created."

#         sr = frappe.new_doc("Stock Reconciliation")
#         sr.company = frappe.defaults.get_user_default("Company")
#         # sr.purpose = "Stock Reconciliation"
#         sr.purpose = "Opening Stock"
#         sr.set("items", [])

#         for item in reconciliation_items:
#             sr.append("items", {
#                 "item_code": item["item_code"],
#                 "warehouse": item["warehouse"],
#                 "qty": item["qty"],
#                 "use_serial_batch_fields": 1
#             })

#         # sr.expense_account = "Stock Adjustment - IF-M"
#         sr.expense_account = "Temporary Opening - IF-M"

#         sr.insert(ignore_permissions=True)
#         sr.submit()

#         return f"Stock Reconciliation {sr.name} created. {len(reconciliation_items)} items updated."

#     except Exception:
#         frappe.log_error(frappe.get_traceback(), "[CIN7] sync_stock: Unhandled Exception")
#         frappe.throw(_("Stock reconciliation failed. Check error log."))


# @frappe.whitelist()
# def sync_stock():
#     """Sync CIN7 stock with ERP via Stock Reconciliation. Always creates reconciliation, prevents duplicates, handles pagination."""

#     cin7 = frappe.get_single("CIN7 Settings")
#     if not cin7.enable:
#         frappe.throw(_("CIN7 Integration is not enabled."))

#     base_url = "https://inventory.dearsystems.com/ExternalApi/v2/ref/productavailability"
#     warehouse = "Melbourne Warehouse - IF-M - L"
#     total_items = None
#     page = 1
#     fetched_count = 0
#     reconciliation_map = {}  # Key: item_code::warehouse, Value: total qty

#     try:
#         while True:
#             url = f"{base_url}?Page={page}"
#             response = cin7._get(url)

#             if total_items is None:
#                 total_items = response.get("Total", 0)

#             stocks = response.get("ProductAvailabilityList", [])
#             if not isinstance(stocks, list):
#                 frappe.log_error(f"[CIN7] Invalid response format at Page {page}", "[CIN7] sync_stock")
#                 frappe.throw(_("Invalid CIN7 response format."))

#             if not stocks:
#                 break

#             for stock in stocks:
#                 sku = stock.get("SKU")
#                 if not sku:
#                     continue

#                 cin7_qty = float(stock.get("Available") or 0)
#                 item_code = frappe.db.get_value("Item", {"item_code": sku})

#                 if not item_code:
#                     continue

#                 key = f"{item_code}::{warehouse}"

#                 if key not in reconciliation_map:
#                     reconciliation_map[key] = {
#                         "item_code": item_code,
#                         "warehouse": warehouse,
#                         "qty": 0
#                     }

#                 reconciliation_map[key]["qty"] += cin7_qty  # Sum StockOnHand for same item

#             fetched_count += len(stocks)
#             if fetched_count >= total_items:
#                 break

#             page += 1

#         reconciliation_items = list(reconciliation_map.values())
#         if not reconciliation_items:
#             return "No matching items found. No Stock Reconciliation created."

#         # Get company and abbreviation dynamically
#         company = frappe.defaults.get_user_default("Company")
#         company_abbr = frappe.db.get_value("Company", company, "abbr")

#         # Check how many stock reconciliations exist for this company
#         existing_sr_count = frappe.db.count("Stock Reconciliation", {"company": company})

#         # Dynamically determine purpose
#         purpose = "Opening Stock" if existing_sr_count == 0 else "Stock Reconciliation"

#         # Create new Stock Reconciliation document
#         sr = frappe.new_doc("Stock Reconciliation")
#         sr.company = company
#         sr.purpose = purpose
#         sr.expense_account = f"Temporary Opening - {company_abbr}"
#         sr.set("items", [])

#         # Add items to the stock reconciliation
#         for item in reconciliation_items:
#             item_qty = max(item["qty"], 0)
#             sr.append("items", {
#                 "item_code": item["item_code"],
#                 "warehouse": item["warehouse"],
#                 "qty": item_qty,
#                 "use_serial_batch_fields": 1
#             })

#         # Insert and submit the stock reconciliation
#         sr.insert(ignore_permissions=True)
#         sr.submit()

#         return f"Stock Reconciliation {sr.name} created. {len(reconciliation_items)} items updated."

#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "[CIN7] sync_stock: Unhandled Exception")
#         frappe.throw(_("Stock reconciliation failed. Check error log."))


@frappe.whitelist()
def sync_stock():
    """Sync CIN7 stock with ERP via Stock Reconciliation. Creates/updates reconciliation, handles pagination, and batch updates."""

    # Fetch CIN7 settings
    cin7 = frappe.get_single("CIN7 Settings")
    if not cin7.enable:
        frappe.throw(_("CIN7 Integration is not enabled."))

    base_url = "https://inventory.dearsystems.com/ExternalApi/v2/ref/productavailability"
    page = 1
    total_items = None
    reconciliation_map = {}
    warehouse = "Melbourne Warehouse - IF-M - L"

    try:
        # Pagination to fetch all items
        while True:
            url = f"{base_url}?Page={page}"
            response = cin7._get(url)

            if total_items is None:
                total_items = response.get("Total", 0)

            stocks = response.get("ProductAvailabilityList", [])
            if not isinstance(stocks, list):
                frappe.log_error(f"[CIN7] Invalid response format at Page {page}", "[CIN7] sync_stock")
                frappe.throw(_("Invalid CIN7 response format."))

            if not stocks:
                break

            for stock in stocks:
                sku = stock.get("SKU")
                if not sku:
                    continue

                cin7_qty = float(stock.get("Available") or 0)
                item_code = frappe.db.get_value("Item", {"item_code": sku})

                if not item_code:
                    continue

                current_stock_qty = frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty")

                if current_stock_qty == cin7_qty:
                    continue

                key = f"{item_code}"
                if key not in reconciliation_map:
                   reconciliation_map[key] = {"item_code": item_code, "warehouse": warehouse, "qty": 0}

                reconciliation_map[key]["qty"] = cin7_qty

            page += 1
            if len(stocks) >= total_items:
                break

        reconciliation_items = list(reconciliation_map.values())
        if not reconciliation_items:
            return "No matching items found. No Stock Reconciliation created."

        company = frappe.defaults.get_user_default("Company")
        company_abbr = frappe.db.get_value("Company", company, "abbr")
        existing_sr_count = frappe.db.count("Stock Reconciliation", {"company": company})
        purpose = "Opening Stock" if existing_sr_count == 0 else "Stock Reconciliation"

        sr = frappe.new_doc("Stock Reconciliation") if existing_sr_count == 0 else frappe.get_last_doc("Stock Reconciliation", filters={"company": company})
        sr.company = company
        sr.purpose = purpose
        sr.expense_account = f"Temporary Opening - {company_abbr}"

        for item in reconciliation_items:
            item_qty = max(item["qty"], 0)

            if item_qty == 0:
                continue

            if "batch_no" not in item:
                item["batch_no"] = None

            batch_id = frappe.db.get_value("Batch", {"item": item["item_code"]}, "batch_id")

            if batch_id:
                new_qty = item_qty
                frappe.log_error(f"Updated Batch {batch_id} with new qty {new_qty}")
                item["batch_no"] = batch_id

            if "use_serial_batch_fields" not in item:
                    item["use_serial_batch_fields"] = None

            opening_stock_exists = frappe.db.exists("Stock Reconciliation", {

                "purpose": "Opening Stock"
            })

            if not opening_stock_exists:

                 item["use_serial_batch_fields"] = 1
            else:
                item["use_serial_batch_fields"] = 0




            sr.append("items", {
                "item_code": item["item_code"],
                "warehouse": item["warehouse"],
                "qty": item_qty,
                "use_serial_batch_fields": item["use_serial_batch_fields"],
                "batch_no" : item["batch_no"]

            })

        try:
            sr.insert(ignore_permissions=True)
            sr.submit()
        except frappe.exceptions.ValidationError as e:
            frappe.log_error(f"Validation Error: {str(e)}", "[CIN7] sync_stock")
            return f"Error: {str(e)}"

        return f"Stock Reconciliation {sr.name} created/updated. {len(reconciliation_items)} items processed."

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "[CIN7] sync_stock: Unhandled Exception")
        frappe.throw(_("Stock reconciliation failed. Check error log."))


# @frappe.whitelist()
# def sync_stock():
#     """Sync CIN7 stock with ERP via Stock Reconciliation. Creates/updates reconciliation, handles pagination, and batch updates."""

#     # Fetch CIN7 settings
#     cin7 = frappe.get_single("CIN7 Settings")
#     if not cin7.enable:
#         frappe.throw(_("CIN7 Integration is not enabled."))

#     base_url = "https://inventory.dearsystems.com/ExternalApi/v2/ref/productavailability"
#     warehouse = "Melbourne Warehouse - IF-M-L"
#     page = 1
#     total_items = None
#     reconciliation_map = {}

#     try:
#         # Pagination to fetch all items
#         while True:
#             url = f"{base_url}?Page={page}"
#             response = cin7._get(url)

#             if total_items is None:
#                 total_items = response.get("Total", 0)

#             stocks = response.get("ProductAvailabilityList", [])
#             if not isinstance(stocks, list):
#                 frappe.log_error(f"[CIN7] Invalid response format at Page {page}", "[CIN7] sync_stock")
#                 frappe.throw(_("Invalid CIN7 response format."))

#             # Break if no stock items are returned
#             if not stocks:
#                 break

#             # Process each stock item
#             for stock in stocks:
#                 sku = stock.get("SKU")
#                 if not sku:
#                     continue

#                 cin7_qty = float(stock.get("Available") or 0)
#                 item_code = frappe.db.get_value("Item", {"item_code": sku})

#                 if not item_code:
#                     continue

#                 # Store reconciliation data per item and warehouse
#                 key = f"{item_code}::{warehouse}"
#                 if key not in reconciliation_map:
#                     reconciliation_map[key] = {"item_code": item_code, "warehouse": warehouse, "qty": 0}

#                 reconciliation_map[key]["qty"] = cin7_qty

#             page += 1
#             if len(stocks) >= total_items:
#                 break

#         reconciliation_items = list(reconciliation_map.values())
#         if not reconciliation_items:
#             return "No matching items found. No Stock Reconciliation created."

#         # Create or fetch Stock Reconciliation
#         company = frappe.defaults.get_user_default("Company")
#         company_abbr = frappe.db.get_value("Company", company, "abbr")
#         existing_sr_count = frappe.db.count("Stock Reconciliation", {"company": company})
#         purpose = "Opening Stock" if existing_sr_count == 0 else "Stock Reconciliation"

#         sr = frappe.new_doc("Stock Reconciliation") if existing_sr_count == 0 else frappe.get_last_doc("Stock Reconciliation", filters={"company": company})
#         sr.company = company
#         sr.purpose = purpose
#         sr.expense_account = f"Temporary Opening - {company_abbr}"

#         # Add or update items in reconciliation
#         for item in reconciliation_items:
#             item_qty = max(item["qty"], 0)
#             existing_item = next((existing for existing in sr.items if existing.item_code == item["item_code"] and existing.warehouse == item["warehouse"]), None)

#             if existing_item:
#                 # Update existing batch
#                 for batch in existing_item.batch_no:
#                     if batch.batch == item.get("batch"):
#                         batch.actual_qty = item_qty
#                         break
#                 else:
#                     # Create new batch if it doesn't exist
#                     existing_item.append("batch_no", {
#                         "batch": item.get("batch"),
#                         "actual_qty": item_qty,
#                     })
#             else:
#                 # Add new item to reconciliation
#                 sr.append("items", {
#                     "item_code": item["item_code"],
#                     "warehouse": item["warehouse"],
#                     "qty": item_qty,
#                     "use_serial_batch_fields": 1,
#                     "batch_no": [{
#                         "batch": item.get("batch"),
#                         "actual_qty": item_qty,
#                     }]
#                 })

#         # Insert and submit the reconciliation
#         try:
#             sr.insert(ignore_permissions=True)
#             sr.submit()
#         except frappe.exceptions.ValidationError as e:
#             frappe.log_error(f"Validation Error: {str(e)}", "[CIN7] sync_stock")
#             return f"Error: {str(e)}"

#         return f"Stock Reconciliation {sr.name} created/updated. {len(reconciliation_items)} items processed."

#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "[CIN7] sync_stock: Unhandled Exception")
#         frappe.throw(_("Stock reconciliation failed. Check error log."))


@frappe.whitelist()
def sync_cin7_sales_orders_background():
    frappe.enqueue(
        "cin7_integration.cin7_integration.doctype.cin7_settings.cin7_settings.sync_sales_orders",
        queue="long",
        timeout=6000,
        job_name="Sync CIN7 Sales Orders",
        is_async=True,
        now=False
    )
    return "Sync started in background."


@frappe.whitelist()
def sync_sales_orders():
    page = 15
    count = 0

    while True:
        sales = get_cin7_sale_ids(saleStatus="INVOICED", start_page=page)

        if not sales:
            frappe.logger().info(f"[SYNC] No more sales found at page {page}. Ending sync.")
            break

        for i, sale in enumerate(sales, start=1):
            sale_id = sale.get("SaleID")
            customer_name = sale.get("Customer")

            frappe.logger().info(f"[SYNC] Processing SaleID: {sale_id}, Customer: {customer_name}")
            sale_data = get_cin7_sale_order_details(sale_id)

            if not sale_data:
                continue

            sale_data["Customer"] = customer_name
            sale_data["OrderDate"] = sale.get("OrderDate")
            so_name = create_erpnext_sales_order_from_cin7(sale_data)

            if so_name:
                log_cin7(
                    title=f"CIN7 Sales Order {so_name} Synced",
                    method="GET",
                    status='Success',
                )
                frappe.logger().info(f"[SYNC] Created ERPNext Sales Order: {so_name}")
                count += 1

        page += 1

    frappe.logger().info(f"[SYNC] Completed. Total orders synced: {count}")


# @frappe.whitelist()
# def sync_sales_orders():
#     statuses = ["INVOICED", "CREDITED"]
#     total_count = 0

#     for status in statuses:
#         page = 15
#         count = 0

#         while True:
#             sales = get_cin7_sale_ids(saleStatus=status, start_page=page)

#             if not sales:
#                 frappe.logger().info(f"[SYNC] No more '{status}' sales found at page {page}. Ending sync for this status.")
#                 break

#             for i, sale in enumerate(sales, start=1):
#                 sale_id = sale.get("SaleID")
#                 customer_name = sale.get("Customer")

#                 frappe.logger().info(f"[SYNC] Processing SaleID: {sale_id}, Customer: {customer_name}, Status: {status}")
#                 sale_data = get_cin7_sale_order_details(sale_id)

#                 if not sale_data:
#                     continue

#                 sale_data["Customer"] = customer_name
#                 sale_data["OrderDate"] = sale.get("OrderDate")
#                 so_name = create_erpnext_sales_order_from_cin7(sale_data)

#                 if so_name:
#                     log_cin7(
#                         title=f"CIN7 Sales Order {so_name} Synced ({status})",
#                         method="GET",
#                         status='Success',
#                     )
#                     frappe.logger().info(f"[SYNC] Created ERPNext Sales Order: {so_name}")
#                     count += 1

#             page += 1

#         frappe.logger().info(f"[SYNC] Completed for status '{status}'. Total orders synced: {count}")
#         total_count += count

#     frappe.logger().info(f"[SYNC] Completed overall. Total orders synced: {total_count}")
