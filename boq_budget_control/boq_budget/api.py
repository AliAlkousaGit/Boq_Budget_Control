import frappe
from frappe import _
from frappe.utils import cint, formatdate, getdate

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
	rows = frappe.db.get_all(
		"BOQ Budget Item",
		filters={"parent": budget, "parenttype": "BOQ Project Budget", "row_type": "Category"},
		fields=["boq_category", "description", "budget_amount", "control_action"],
		order_by="idx asc",
	)
	for r in rows:
		r["category_name"] = r.pop("description")
	return rows


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
		"BOQ Budget Item",
		filters={"parent": budget, "parenttype": "BOQ Project Budget", "row_type": "Category"},
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


# ---------------------------------------------------------------------------
# Accounts Reminder prototype — team reminder board API
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_accounts_reminders():
	"""Open reminders (overdue → today → upcoming → undated) + 5 recent completed."""
	frappe.has_permission("Accounts Reminder", "read", throw=True)

	open_rows = frappe.get_all(
		"Accounts Reminder",
		filters={"is_done": 0},
		fields=["name", "reminder_text", "due_date", "owner", "modified"],
	)

	today = getdate()
	for row in open_rows:
		row["owner_name"] = frappe.utils.get_fullname(row.owner)
		row["due_date_display"] = formatdate(row.due_date) if row.due_date else None
		if not row.due_date:
			row["status"] = "nodate"
		elif row.due_date < today:
			row["status"] = "overdue"
		elif row.due_date == today:
			row["status"] = "today"
		else:
			row["status"] = "upcoming"

	rank = {"overdue": 0, "today": 1, "upcoming": 2, "nodate": 3}
	open_rows.sort(key=lambda r: (rank[r["status"]], r.due_date or getdate("9999-12-31"), r.modified), reverse=False)

	completed = frappe.get_all(
		"Accounts Reminder",
		filters={"is_done": 1},
		fields=["name", "reminder_text", "due_date", "modified"],
		order_by="modified desc",
		limit_page_length=5,
	)

	return {"open": open_rows, "completed": completed}


@frappe.whitelist()
def toggle_reminder_done(name, done):
	"""Mark a reminder done (or reopen it). Users may write; managers may reopen."""
	frappe.has_permission("Accounts Reminder", "read", throw=True)
	doc = frappe.get_doc("Accounts Reminder", name)
	doc.check_permission("write")
	doc.is_done = cint(done)
	doc.save(ignore_permissions=True)
	return {"name": doc.name, "is_done": doc.is_done}
