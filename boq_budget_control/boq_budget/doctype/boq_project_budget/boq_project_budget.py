import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class BOQProjectBudget(Document):
    def validate(self):
        self.total_budget_amount = sum(flt(c.budget_amount) for c in self.categories)
        self._validate_categories()

    def _validate_categories(self):
        cats = [c.boq_category for c in self.categories]
        if len(cats) != len(set(cats)):
            frappe.throw(_("A BOQ Category may only appear once per budget."))

    def on_update_after_submit(self):
        from boq_budget_control.boq_budget.budget import refresh_summary
        refresh_summary(self.name)
