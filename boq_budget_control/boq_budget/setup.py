import frappe

CUSTOM_FIELDS = {
    "Purchase Order Item": [
        {"fieldname": "boq_project_budget", "label": "BOQ Project Budget",
         "fieldtype": "Link", "options": "BOQ Project Budget", "insert_after": "project"},
        {"fieldname": "boq_category", "label": "BOQ Category",
         "fieldtype": "Link", "options": "BOQ Budget Category", "insert_after": "boq_project_budget"},
        {"fieldname": "budget_available", "label": "Budget Available",
         "fieldtype": "Currency", "read_only": 1, "insert_after": "boq_category"},
        {"fieldname": "budget_status", "label": "Budget Status",
         "fieldtype": "Data", "read_only": 1, "insert_after": "budget_available"},
    ],
    "Purchase Invoice Item": [
        {"fieldname": "boq_project_budget", "label": "BOQ Project Budget",
         "fieldtype": "Link", "options": "BOQ Project Budget", "insert_after": "project"},
        {"fieldname": "boq_category", "label": "BOQ Category",
         "fieldtype": "Link", "options": "BOQ Budget Category", "insert_after": "boq_project_budget"},
        {"fieldname": "budget_available", "label": "Budget Available",
         "fieldtype": "Currency", "read_only": 1, "insert_after": "boq_category"},
        {"fieldname": "budget_status", "label": "Budget Status",
         "fieldtype": "Data", "read_only": 1, "insert_after": "budget_available"},
    ],
}


def make_custom_fields():
    for dt, fields in CUSTOM_FIELDS.items():
        for f in fields:
            name = f"{dt}-{f['fieldname']}"
            if frappe.db.exists("Custom Field", name):
                continue
            frappe.get_doc({"doctype": "Custom Field", "dt": dt, **f}).insert(ignore_permissions=True)
