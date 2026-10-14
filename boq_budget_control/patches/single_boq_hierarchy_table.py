"""Move to the single two-level BOQ table (BOQ Budget Item).

Drops the dashboard number cards / chart that pointed at the removed
``BOQ Project Budget Category`` table; ``after_migrate`` (setup.make_workspace)
recreates them under the same names against the Category rows of
``BOQ Budget Item``, so the BOQ Budgeting workspace layout stays valid.

The old rows are kept in ``_bak_boq_project_budget_category``
(see backup_old_category_table).
"""

import frappe

OLD_TABLE = "BOQ Project Budget Category"


def execute():
	for doctype in ("Number Card", "Dashboard Chart"):
		for name in frappe.get_all(doctype, filters={"document_type": OLD_TABLE}, pluck="name"):
			frappe.delete_doc(doctype, name, force=1, ignore_permissions=True)

	if frappe.db.exists("DocType", OLD_TABLE):
		frappe.delete_doc("DocType", OLD_TABLE, force=1, ignore_permissions=True)
