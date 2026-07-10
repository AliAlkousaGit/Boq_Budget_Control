import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class BOQProjectBudget(Document):
    def validate(self):
        self._calculate_budget_amounts()
        self.total_budget_amount = sum(flt(c.budget_amount) for c in self.categories)
        self._validate_categories()

    def _calculate_budget_amounts(self):
        """Derive Budget Amount = Total - (Total x Overhead %) per category row.

        When Total is set, Budget Amount and Net Budget % are auto-calculated
        (Budget Amount is read-only in the UI). Rows without a Total keep their
        existing Budget Amount (backward compatibility for budgets created
        before these fields existed).
        """
        for c in self.categories:
            if flt(c.total) > 0:
                overhead = flt(c.overhead_percentage)
                if overhead < 0 or overhead > 100:
                    frappe.throw(_("Row {0}: Overhead % must be between 0 and 100.").format(c.idx))
                c.budget_amount = flt(c.total) * (1 - overhead / 100.0)
                c.net_budget_percent = flt(100.0 - overhead)
            else:
                c.net_budget_percent = None

    def _validate_categories(self):
        cats = [c.boq_category for c in self.categories]
        if len(cats) != len(set(cats)):
            frappe.throw(_("A BOQ Category may only appear once per budget."))

    def on_update_after_submit(self):
        from boq_budget_control.boq_budget.budget import refresh_summary
        refresh_summary(self.name)
