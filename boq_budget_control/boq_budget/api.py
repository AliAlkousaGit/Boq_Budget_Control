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
	"""Return the BOQ Budget Category rows for a given budget parent."""
	if not budget or not frappe.db.exists("BOQ Project Budget", budget):
		return []
	return frappe.db.get_all(
		"BOQ Budget Category",
		filters={"parent": budget, "parenttype": "BOQ Project Budget"},
		fields=["name", "category_code", "category_name"],
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
