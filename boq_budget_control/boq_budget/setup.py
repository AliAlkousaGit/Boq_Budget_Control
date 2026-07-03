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

# Standard main BOQ categories seeded so users have something to allocate against.
DEFAULT_CATEGORIES = [
    ("PRE", "Preliminaries"),
    ("SUB", "Sub Structure"),
    ("SUP", "Super Structure"),
    ("BLK", "Block Work"),
    ("FIN", "Finishes"),
    ("MEP", "MEP Services"),
    ("EXT", "External Works"),
]


def make_custom_fields():
    for dt, fields in CUSTOM_FIELDS.items():
        for f in fields:
            name = f"{dt}-{f['fieldname']}"
            if frappe.db.exists("Custom Field", name):
                continue
            frappe.get_doc({"doctype": "Custom Field", "dt": dt, **f}).insert(ignore_permissions=True)


def make_roles():
    if not frappe.db.exists("Role", "BOQ Manager"):
        frappe.get_doc({"doctype": "Role", "role_name": "BOQ Manager",
                        "desk_access": 1, "is_custom": 1}).insert(ignore_permissions=True)


def make_categories():
    for code, name in DEFAULT_CATEGORIES:
        if not frappe.db.exists("BOQ Budget Category", code):
            frappe.get_doc({"doctype": "BOQ Budget Category",
                            "category_code": code, "category_name": name}).insert(ignore_permissions=True)
