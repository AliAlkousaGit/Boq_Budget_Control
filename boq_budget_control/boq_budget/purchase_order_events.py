# Copyright (c) 2026, BOQ Budget Control and contributors
# For license information, please see license.txt
"""Purchase Order doc_events adapter.

Thin layer: pulls the BOQ fields + amount off each PO item row and calls the
budget engine. A submitted PO *reserves* budget; a cancelled PO reverses it.
"""

import frappe
from frappe import _
from frappe.utils import flt

from boq_budget_control.boq_budget.budget import (
	post_ledger,
	post_reversal,
	refresh_summary,
	validate_row,
)


def _row_amount(item):
	"""Budget consumed by a row = base_net_amount (company currency, excl. tax),
	falling back to qty * rate when base_net_amount is not populated."""
	return flt(item.get("base_net_amount")) or flt(item.qty) * flt(item.rate)


def before_submit(doc, method):
	for item in doc.items:
		if not item.get("project"):
			continue
		budget = item.get("boq_project_budget")
		category = item.get("boq_category")
		if not (budget and category):
			frappe.throw(
				_("Row {0}: BOQ Project Budget and BOQ Category are required when Project is set.")
				.format(item.idx)
			)
		if frappe.db.get_value("BOQ Project Budget", budget, "docstatus") != 1:
			frappe.throw(_("Row {0}: BOQ Project Budget must be Approved.").format(item.idx))
		if frappe.db.get_value("BOQ Project Budget", budget, "is_closed"):
			frappe.throw(_("Row {0}: BOQ Project Budget is closed.").format(item.idx))
		validate_row(budget, category, _row_amount(item))


def on_submit(doc, method):
	budgets = set()
	for item in doc.items:
		if item.get("project") and item.get("boq_project_budget") and item.get("boq_category"):
			post_ledger(
				"Reserve", item.boq_project_budget, item.boq_category,
				voucher_type="Purchase Order", voucher_no=doc.name,
				voucher_detail_no=item.name, amount=_row_amount(item),
				posting_date=doc.transaction_date,
			)
			budgets.add(item.boq_project_budget)
	for b in budgets:
		refresh_summary(b)


def on_cancel(doc, method):
	budgets = {i.boq_project_budget for i in doc.items if i.get("boq_project_budget")}
	post_reversal("Purchase Order", doc.name)
	for b in budgets:
		refresh_summary(b)
