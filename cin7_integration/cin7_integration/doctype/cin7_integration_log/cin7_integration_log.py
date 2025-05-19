# cin7_integration_log.py

import frappe
from frappe.model.document import Document

class CIN7IntegrationLog(Document):
    pass


def log_cin7(title, method=None, url=None, voucher_type=None, voucher_name=None, status=None, request=None, response=None):
    """Creates a new Xero Integration Log entry"""
    doc = frappe.new_doc('Xero Integration Log')
    doc.update({
        "title": title,
        "method": method,
        "url": url,
        "voucher_type": voucher_type,
        "voucher_name": voucher_name,
        "status": status,
        "request": request,
        "response": response
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.name
