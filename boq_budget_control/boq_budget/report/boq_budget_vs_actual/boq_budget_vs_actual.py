# Copyright (c) 2026, BOQ Budget Control and contributors
# License: MIT
"""BOQ Budget vs Actual — Script Report.

One row per (budget, category) allocation, showing budget vs reserved vs actual
vs available and utilization %, all computed live from the ledger.
"""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
    filters = frappe._dict(filters or {})
    return get_columns(), get_data(filters)


def get_columns():
    return [
        {"label": _("Company"), "fieldname": "company", "fieldtype": "Link",
         "options": "Company", "width": 120},
        {"label": _("Project"), "fieldname": "project", "fieldtype": "Link",
         "options": "Project", "width": 120},
        {"label": _("BOQ Budget"), "fieldname": "boq_project_budget", "fieldtype": "Link",
         "options": "BOQ Project Budget", "width": 150},
        {"label": _("Category"), "fieldname": "boq_category", "fieldtype": "Link",
         "options": "BOQ Budget Category", "width": 100},
        {"label": _("Category Name"), "fieldname": "category_name", "width": 150},
        {"label": _("Budget Amount"), "fieldname": "budget_amount", "fieldtype": "Currency",
         "options": "company:currency", "width": 120},
        {"label": _("Reserved"), "fieldname": "reserved", "fieldtype": "Currency",
         "options": "company:currency", "width": 110},
        {"label": _("Actual"), "fieldname": "actual", "fieldtype": "Currency",
         "options": "company:currency", "width": 110},
        {"label": _("Available"), "fieldname": "available", "fieldtype": "Currency",
         "options": "company:currency", "width": 110},
        {"label": _("Utilization %"), "fieldname": "utilization", "fieldtype": "Percent", "width": 100},
        {"label": _("Control"), "fieldname": "control_action", "width": 80},
    ]


def get_data(filters):
    from boq_budget_control.boq_budget.budget import get_category_summary

    bf = {"docstatus": 1}
    if filters.company:
        bf["company"] = filters.company
    if filters.project:
        bf["project"] = filters.project
    if filters.budget:
        bf["name"] = filters.budget
    budgets = frappe.db.get_all("BOQ Project Budget", filters=bf,
                                fields=["name", "company", "project"])

    out = []
    for b in budgets:
        allocs = frappe.db.get_all(
            "BOQ Project Budget Category",
            filters={"parent": b.name, "parenttype": "BOQ Project Budget"},
            fields=["boq_category", "category_name", "budget_amount", "control_action"],
        )
        for a in allocs:
            s = get_category_summary(b.name, a.boq_category)
            consumed = flt(s["reserved"]) + flt(s["actual"])
            util = (consumed / flt(s["budget_amount"]) * 100) if flt(s["budget_amount"]) else 0
            out.append({
                "company": b.company,
                "project": b.project,
                "boq_project_budget": b.name,
                "boq_category": a.boq_category,
                "category_name": a.category_name,
                "budget_amount": s["budget_amount"],
                "reserved": s["reserved"],
                "actual": s["actual"],
                "available": s["available"],
                "utilization": util,
                "control_action": a.control_action,
            })
    return out
