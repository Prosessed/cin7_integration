# Copyright (c) 2025, Jaspreet Singh Sodhi and contributors
# For license information, please see license.txt

import frappe
import requests
import json
from frappe.model.document import Document


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
        except Exception as e:
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
        except Exception as e:
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
