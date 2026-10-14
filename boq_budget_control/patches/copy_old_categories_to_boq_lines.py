"""Keep existing budgets working after the move to the single BOQ table.

Copies every old ``BOQ Project Budget Category`` row (read from the backup
``_bak_boq_project_budget_category`` made by ``backup_old_category_table``)
into ``BOQ Budget Item`` as a Category row of the same budget, keeping:

    budget amount, overhead %, control action (Stop/Warn/Allow),
    reserved / actual / available / spent % and the row's docstatus.

The PO / PI engine reads its allocation from these Category rows, so old
submitted budgets keep controlling spend exactly as before. Old budgets have
no item lines (1.1, 1.2 …); new budgets use the full category -> items table.

Safe to re-run: a budget that already has any BOQ Budget Item rows is skipped.
Nothing in the old data or the budget ledger is changed.
"""

import frappe
from frappe.utils import flt

BACKUP = "_bak_boq_project_budget_category"
PARENT = "BOQ Project Budget"


def execute():
	if not frappe.db.sql("SHOW TABLES LIKE %s", BACKUP):
		return

	old_rows = frappe.db.sql(
		f"SELECT * FROM `{BACKUP}` WHERE parenttype = %s ORDER BY parent, idx",
		PARENT,
		as_dict=True,
	)

	by_budget = {}
	for row in old_rows:
		by_budget.setdefault(row.parent, []).append(row)

	for budget, rows in by_budget.items():
		docstatus = frappe.db.get_value(PARENT, budget, "docstatus")
		if docstatus is None:
			continue  # budget deleted
		if frappe.db.exists("BOQ Budget Item", {"parent": budget, "parenttype": PARENT}):
			continue  # already has new-style lines (rebuilt, or patch already ran)

		for i, old in enumerate(rows, 1):
			line = to_category_line(old, i, docstatus)
			if not line["description"]:
				line["description"] = frappe.db.get_value("BOQ Budget Category", old.boq_category, "category_name")
			frappe.get_doc(line).db_insert()


def to_category_line(old, idx, docstatus):
	"""Map one old allocation row to a BOQ Budget Item Category row (pure)."""
	total = flt(old.get("total"))
	budget_amount = flt(old.get("budget_amount"))
	# manual budgets (no Total) had no overhead applied: amount = budget
	overhead = flt(old.get("overhead_percentage")) if total else 0

	return {
		"doctype": "BOQ Budget Item",
		"name": old.get("name"),
		"owner": old.get("owner"),
		"creation": old.get("creation"),
		"modified": old.get("modified"),
		"modified_by": old.get("modified_by"),
		"parent": old.get("parent"),
		"parenttype": PARENT,
		"parentfield": "items",
		"idx": idx,
		"docstatus": docstatus,
		"line_no": str(idx),
		"row_type": "Category",
		"boq_category": old.get("boq_category"),
		"description": (old.get("category_name") or "").strip() or None,
		"amount": total or budget_amount,
		"overhead_percentage": overhead,
		"budget_amount": budget_amount,
		"net_budget_percent": 100.0 - overhead,
		"control_action": old.get("control_action") or "Stop",
		"reserved_amount": flt(old.get("reserved_amount")),
		"actual_amount": flt(old.get("actual_amount")),
		"available_amount": flt(old.get("available_amount")),
		"overall_budget_spent_percentage": flt(old.get("overall_budget_spent_percentage")),
		"remarks": old.get("remarks"),
	}
