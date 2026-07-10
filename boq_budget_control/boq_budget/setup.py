import json

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


# ---------------------------------------------------------------------------
# Workspace — "BOQ Budgeting" dashboard
# ---------------------------------------------------------------------------
BOQ_WORKSPACE_LABEL = "BOQ Budgeting"
BOQ_MODULE = "BOQ Budget"


def make_workspace():
    """Create the BOQ Budgeting workspace + its number cards and charts.

    Idempotent: skips anything that already exists, so it is safe to run from
    ``after_install`` / ``after_migrate`` on every migrate.
    """
    _boq_number_cards()
    _boq_charts()
    _boq_workspace_doc()


def _boq_number_cards():
    # (label, document_type, function, aggregate_field, filters, parent_document_type)
    # parent_document_type is required when document_type is a child table.
    cards = [
        ("Total Budgeted", "BOQ Project Budget", "Sum", "total_budget_amount",
         [["BOQ Project Budget", "docstatus", "=", 1]], None),
        ("Total Reserved", "BOQ Project Budget Category", "Sum", "reserved_amount",
         [], "BOQ Project Budget"),
        ("Total Actual", "BOQ Project Budget Category", "Sum", "actual_amount",
         [], "BOQ Project Budget"),
        ("Available", "BOQ Project Budget Category", "Sum", "available_amount",
         [], "BOQ Project Budget"),
        ("Active Budgets", "BOQ Project Budget", "Count", None,
         [["BOQ Project Budget", "docstatus", "=", 1],
          ["BOQ Project Budget", "is_closed", "=", 0]], None),
    ]
    for label, dt, func, agg, filters, parent_dt in cards:
        if frappe.db.exists("Number Card", label):
            continue
        doc = frappe.get_doc({
            "doctype": "Number Card",
            "label": label,
            "type": "Document Type",
            "document_type": dt,
            "function": func,
            "is_public": 1,
            "module": BOQ_MODULE,
        })
        if parent_dt:
            doc.parent_document_type = parent_dt
        if agg:
            doc.aggregate_function_based_on = agg
        if filters:
            doc.filters_json = json.dumps(filters)
        doc.insert(ignore_permissions=True)


def _boq_charts():
    if not frappe.db.exists("Dashboard Chart", "Budget by Category"):
        frappe.get_doc({
            "doctype": "Dashboard Chart",
            "chart_name": "Budget by Category",
            "chart_type": "Group By",
            "document_type": "BOQ Project Budget Category",
            "parent_document_type": "BOQ Project Budget",
            "group_by_based_on": "boq_category",
            "group_by_type": "Sum",
            "aggregate_function_based_on": "budget_amount",
            "type": "Donut",
            "filters_json": "[]",
            "is_public": 1,
            "module": BOQ_MODULE,
        }).insert(ignore_permissions=True)

    if not frappe.db.exists("Dashboard Chart", "Monthly Ledger Activity"):
        frappe.get_doc({
            "doctype": "Dashboard Chart",
            "chart_name": "Monthly Ledger Activity",
            "chart_type": "Sum",
            "document_type": "BOQ Budget Ledger Entry",
            "based_on": "posting_date",
            "timeseries": 1,
            "timespan": "Last Year",
            "time_interval": "Monthly",
            "value_based_on": "amount",
            "type": "Line",
            "filters_json": "[]",
            "is_public": 1,
            "module": BOQ_MODULE,
        }).insert(ignore_permissions=True)


def _boq_workspace_doc():
    if frappe.db.exists("Workspace", BOQ_WORKSPACE_LABEL):
        return

    ws = frappe.get_doc({
        "doctype": "Workspace",
        "label": BOQ_WORKSPACE_LABEL,
        "title": BOQ_WORKSPACE_LABEL,
        "module": BOQ_MODULE,
        "icon": "money-coins",
        "public": 1,
        "is_hidden": 0,
        "sequence_id": 1,
        "content": json.dumps(_boq_content()),
    })

    # Child-table rows MUST mirror the content blocks built in _boq_content().
    for label in ("Total Budgeted", "Total Reserved", "Total Actual", "Available", "Active Budgets"):
        ws.append("number_cards", {"number_card_name": label, "label": label})
    for name in ("Budget by Category", "Monthly Ledger Activity"):
        ws.append("charts", {"chart_name": name, "label": name})
    ws.append("quick_lists", {"document_type": "BOQ Project Budget", "label": "Recent Budgets"})
    ws.append("quick_lists", {"document_type": "BOQ Budget Ledger Entry", "label": "Recent Ledger Entries"})

    ws.append("shortcuts", {"type": "DocType", "link_to": "BOQ Project Budget",
                            "label": "New BOQ Project Budget", "doc_view": "New", "color": "Blue"})
    ws.append("shortcuts", {"type": "DocType", "link_to": "BOQ Budget Category",
                            "label": "BOQ Budget Category", "doc_view": "List", "color": "Blue"})
    ws.append("shortcuts", {"type": "Report", "link_to": "BOQ Budget vs Actual",
                            "label": "Budget vs Actual", "color": "Grey"})
    ws.append("shortcuts", {"type": "Report", "link_to": "BOQ Budget Ledger",
                            "label": "Budget Ledger", "color": "Grey"})

    ws.insert(ignore_permissions=True)


def _boq_content():
    """12-column block layout for the workspace. Block ids are random; the
    *name* fields (number_card_name / chart_name / quick_list_name /
    shortcut_name) must match the child-table rows added in _boq_workspace_doc().
    """

    def bid():
        return frappe.generate_hash(length=10)

    def header(text):
        return {"id": bid(), "type": "header",
                "data": {"text": f'<span class="h4"><b>{text}</b></span>', "col": 12}}

    def spacer():
        return {"id": bid(), "type": "spacer", "data": {"col": 12}}

    def ncard(name, col):
        return {"id": bid(), "type": "number_card", "data": {"number_card_name": name, "col": col}}

    def chart(name, col):
        return {"id": bid(), "type": "chart", "data": {"chart_name": name, "col": col}}

    def qlist(name, col):
        return {"id": bid(), "type": "quick_list", "data": {"quick_list_name": name, "col": col}}

    def shortcut(name, col):
        return {"id": bid(), "type": "shortcut", "data": {"shortcut_name": name, "col": col}}

    def paragraph(text, col):
        return {"id": bid(), "type": "paragraph", "data": {"text": text, "col": col}}

    return [
        header("Overview"),
        ncard("Total Budgeted", 3),
        ncard("Total Reserved", 3),
        ncard("Total Actual", 3),
        ncard("Available", 3),
        ncard("Active Budgets", 3),
        paragraph(
            "<b>How BOQ budgeting works:</b> create a BOQ Project Budget, allocate an amount "
            "per category, then <b>Submit</b> it. Purchase Order items <i>reserve</i> budget; "
            "Purchase Invoice items post <i>actual</i> spend and release the matching reservation. "
            "Budgets must be Submitted before they control PO/PI spend.", 9),
        spacer(),
        header("Trends"),
        chart("Budget by Category", 6),
        chart("Monthly Ledger Activity", 6),
        spacer(),
        header("Recent Activity"),
        qlist("Recent Budgets", 6),
        qlist("Recent Ledger Entries", 6),
        spacer(),
        header("Shortcuts"),
        shortcut("New BOQ Project Budget", 3),
        shortcut("BOQ Budget Category", 3),
        shortcut("Budget vs Actual", 3),
        shortcut("Budget Ledger", 3),
    ]
