import frappe
from frappe import _

from boq_budget_control.boq_budget.budget import get_category_summary


@frappe.whitelist()
def get_budget_for_project(project, company=None):
	"""Return approved budgets for a project (one per fiscal year expected)."""
	if not project:
		return []
	filters = {"project": project, "docstatus": 1}
	if company:
		filters["company"] = company
	return frappe.db.get_all(
		"BOQ Project Budget",
		filters=filters,
		fields=["name", "fiscal_year", "is_closed"],
	)


@frappe.whitelist()
def get_category_options(budget):
	"""Return the master categories allocated in a given budget."""
	if not budget or not frappe.db.exists("BOQ Project Budget", budget):
		return []
	return frappe.db.get_all(
		"BOQ Project Budget Category",
		filters={"parent": budget, "parenttype": "BOQ Project Budget"},
		fields=["boq_category", "category_name", "budget_amount", "control_action"],
	)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def boq_category_query(doctype, txt, searchfield, start, page_len, filters):
	"""Link-field query: only master categories allocated in the selected budget.

	Wired from the PO/PI client scripts via ``set_query`` with
	``{query: "...boq_category_query", filters: {budget: <budget>}}``.
	"""
	budget = (filters or {}).get("budget")
	if not budget:
		return []
	allocated = frappe.db.get_all(
		"BOQ Project Budget Category",
		filters={"parent": budget, "parenttype": "BOQ Project Budget"},
		pluck="boq_category",
	)
	if not allocated:
		return []
	like = f"%{txt or ''}%"
	return frappe.db.get_all(
		"BOQ Budget Category",
		filters={
			"name": ["in", allocated],
			"category_name": ["like", like],
		},
		fields=["name", "category_name"],
		start=start,
		page_length=page_len,
		as_list=True,
	)


@frappe.whitelist()
def get_category_available(budget, category):
	"""Return the live available/reserved/actual + status for one category."""
	if not (budget and category):
		return {"available": 0, "status": "—"}
	s = get_category_summary(budget, category)
	status = "Over Budget" if s["available"] < 0 else "OK"
	return {
		"available": s["available"],
		"reserved": s["reserved"],
		"actual": s["actual"],
		"status": status,
	}
