"""Back up the old BOQ Project Budget Category rows before the DocType is removed.

The single two-level BOQ table replaces it. Migrate may drop the orphaned
DocType (and its table), so a raw copy is kept for rebuilding old budgets:

    SELECT parent, boq_category, total, overhead_percentage, budget_amount,
           control_action, reserved_amount, actual_amount, available_amount
    FROM `_bak_boq_project_budget_category` ORDER BY parent, idx;
"""

import frappe

SOURCE = "tabBOQ Project Budget Category"
BACKUP = "_bak_boq_project_budget_category"


def execute():
	if not frappe.db.table_exists("BOQ Project Budget Category"):
		return
	if frappe.db.sql("SHOW TABLES LIKE %s", BACKUP):
		return
	frappe.db.sql_ddl(f"CREATE TABLE `{BACKUP}` AS SELECT * FROM `{SOURCE}`")
