# Copyright (c) 2026, BOQ Budget Control and contributors
# License: MIT
"""BOQ Budget Ledger — Script Report.

Raw, append-only ledger of every budget movement (Reserve / Release / Actual,
including reversals) with date + dimension filters. The audit trail behind the
BOQ Budget vs Actual summary.
"""

import frappe
from frappe import _


def execute(filters=None):
    filters = frappe._dict(filters or {})
    return get_columns(), get_data(filters)


def get_columns():
    return [
        {"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
        {"label": _("Company"), "fieldname": "company", "fieldtype": "Link",
         "options": "Company", "width": 120},
        {"label": _("Project"), "fieldname": "project", "fieldtype": "Link",
         "options": "Project", "width": 110},
        {"label": _("BOQ Budget"), "fieldname": "boq_project_budget", "fieldtype": "Link",
         "options": "BOQ Project Budget", "width": 140},
        {"label": _("BOQ Category"), "fieldname": "boq_category", "fieldtype": "Link",
         "options": "BOQ Budget Category", "width": 100},
        {"label": _("Voucher Type"), "fieldname": "voucher_type", "width": 120},
        {"label": _("Voucher No"), "fieldname": "voucher_no", "width": 140},
        {"label": _("Entry Type"), "fieldname": "entry_type", "width": 90},
        {"label": _("Amount"), "fieldname": "amount", "fieldtype": "Currency",
         "options": "company:currency", "width": 110},
        {"label": _("Reversal"), "fieldname": "is_reversal", "fieldtype": "Check", "width": 60},
        {"label": _("Remarks"), "fieldname": "remarks", "width": 180},
    ]


def get_data(filters):
    f = {}

    # Date range — handle from-only, to-only, or both.
    if filters.from_date and filters.to_date:
        f["posting_date"] = ["between", [filters.from_date, filters.to_date]]
    elif filters.from_date:
        f["posting_date"] = [">=", filters.from_date]
    elif filters.to_date:
        f["posting_date"] = ["<=", filters.to_date]

    for key in ("company", "project", "boq_category", "voucher_type", "entry_type"):
        if filters.get(key):
            f[key] = filters[key]

    return frappe.db.get_all(
        "BOQ Budget Ledger Entry",
        filters=f,
        fields=[
            "posting_date", "company", "project", "boq_project_budget", "boq_category",
            "voucher_type", "voucher_no", "entry_type", "amount", "is_reversal", "remarks",
        ],
        order_by="posting_date desc, creation desc",
    )
