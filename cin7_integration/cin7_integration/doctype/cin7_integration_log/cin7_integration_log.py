# cin7_integration_log.py

import frappe
from frappe.model.document import Document

class CIN7IntegrationLog(Document):
    pass


def log_cin7(title, method=None, url=None, voucher_type=None, voucher_name=None, status=None, request=None, response=None):
    """Creates a new CIN7 Integration Log entry"""
    doc = frappe.new_doc('CIN7 Integration Log')
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

    doc.save()
    return doc.name
