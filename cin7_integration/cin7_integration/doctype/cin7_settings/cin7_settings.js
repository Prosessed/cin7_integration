// Copyright (c) 2025, Jaspreet Singh Sodhi and contributors
// For license information, please see license.txt

// frappe.ui.form.on("CIN7 Settings", {
// 	refresh(frm) {

// 	},
// });

frappe.ui.form.on("CIN7 Settings", {
    refresh(frm) {
        frm.get_field("sync_items").$input.addClass('btn-primary');
        frm.get_field("sync_customer").$input.addClass('btn-primary');
        frm.get_field("sync_item_groups").$input.addClass('btn-primary');
    },

    sync_items(frm) {
        frappe.call({
            method: "cin7_integration.cin7_integration.doctype.cin7_settings.cin7_settings.sync_items",
            freeze: true,
            freeze_message: "Syncing Items from CIN7...",
            callback: function(r) {
                frappe.msgprint(r.message);
                frm.reload_doc();
            },
            error: function(r) {
                frappe.msgprint("Error syncing customers: " + r.message);
            }
        });
    },

    sync_customer(frm) {
        frappe.call({
            method: "cin7_integration.cin7_integration.doctype.cin7_settings.cin7_settings.sync_customers",
            freeze: true,
            freeze_message: "Syncing Customers from CIN7...",
            callback: function(r) {
                frappe.msgprint(r.message);
                frm.reload_doc();
            },
            error: function(r) {
                frappe.msgprint("Error syncing customers: " + r.message);
            }
        });
    },

    sync_item_groups(frm) {
        frappe.call({
            method: "cin7_integration.cin7_integration.doctype.cin7_settings.cin7_settings.sync_item_groups",
            freeze: true,
            freeze_message: "Syncing ItemGroups from CIN7...",
            callback: function(r) {
                frappe.msgprint(r.message);
                frm.reload_doc();

            },

        });
    }
});
