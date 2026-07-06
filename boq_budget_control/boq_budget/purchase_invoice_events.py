# Copyright (c) 2026, BOQ Budget Control and contributors
# For license information, please see license.txt
"""Purchase Invoice doc_events adapter.

A submitted PI records *actual* expense. If a row is linked to a Purchase Order
(``po_detail`` set), it also *releases* the matching PO reservation:

* the ``Release`` row is keyed on the **PO item** (``item.po_detail``) so that
  :func:`get_reserved_for_po_item` nets Reserve(+)/Release(-) for that PO line;
* the ``Actual`` row is keyed on the **PI item** (``item.name``).

A cancelled PI reverses both, restoring the reservation for linked rows.
"""

import frappe
from frappe import _
from frappe.utils import flt

from boq_budget_control.boq_budget.budget import (
	get_reserved_for_po_item,
	post_ledger,
	post_reversal,
	project_has_budget,
	refresh_summary,
	validate_row,
)


def _row_amount(item):
	"""Budget consumed by a row = base_net_amount (company currency, excl. tax),
	falling back to qty * rate when base_net_amount is not populated."""
	return flt(item.get("base_net_amount")) or flt(item.qty) * flt(item.rate)


def _require(item, header_project):
	budget = item.get("boq_project_budget")
	category = item.get("boq_category")
	if not (budget and category):
		frappe.throw(
			_("Row {0}: BOQ Project Budget and BOQ Category are required "
			  "(Project {1} has a BOQ budget).").format(item.idx, header_project)
		)
	if frappe.db.get_value("BOQ Project Budget", budget, "docstatus") != 1:
		frappe.throw(_("Row {0}: BOQ Project Budget must be Approved.").format(item.idx))
	if frappe.db.get_value("BOQ Project Budget", budget, "is_closed"):
		frappe.throw(_("Row {0}: BOQ Project Budget is closed.").format(item.idx))
	return budget, category


def before_submit(doc, method):
	# BOQ budget control applies only when the HEADER project has an approved budget.
	# If it doesn't, the document behaves like vanilla ERPNext (fields optional).
	if not project_has_budget(doc.get("project"), doc.get("company")):
		return
	for item in doc.items:
		budget, category = _require(item, doc.project)
		if item.get("po_detail"):
			# Linked to PO: cannot invoice more than remains reserved for that PO item.
			reserved = get_reserved_for_po_item(item.po_detail)
			if _row_amount(item) > reserved + 0.01:
				frappe.throw(
					_("Row {0}: amount {1} exceeds reserved {2} for the linked Purchase Order item.")
					.format(item.idx, _row_amount(item), reserved)
				)
		else:
			# Direct PI: validate against the category's available budget.
			validate_row(budget, category, _row_amount(item))


def on_submit(doc, method):
	budgets = set()
	for item in doc.items:
		if not (item.get("boq_project_budget") and item.get("boq_category")):
			continue
		amt = _row_amount(item)
		if item.get("po_detail"):
			# Release frees the PO reservation -> key on the PO item (po_detail).
			post_ledger(
				"Release", item.boq_project_budget, item.boq_category,
				voucher_type="Purchase Invoice", voucher_no=doc.name,
				voucher_detail_no=item.po_detail, amount=amt, posting_date=doc.posting_date,
			)
		# Actual consumes budget -> key on the PI item's own identity.
		post_ledger(
			"Actual", item.boq_project_budget, item.boq_category,
			voucher_type="Purchase Invoice", voucher_no=doc.name,
			voucher_detail_no=item.name, amount=amt, posting_date=doc.posting_date,
		)
		budgets.add(item.boq_project_budget)
	for b in budgets:
		refresh_summary(b)


def on_cancel(doc, method):
	budgets = {i.boq_project_budget for i in doc.items if i.get("boq_project_budget")}
	post_reversal("Purchase Invoice", doc.name)
	for b in budgets:
		refresh_summary(b)
