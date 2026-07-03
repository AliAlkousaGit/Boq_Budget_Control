import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class BOQProjectBudget(Document):
    def validate(self):
        self.total_budget_amount = sum(flt(c.budget_amount) for c in self.categories)
        self._validate_categories()

    def _validate_categories(self):
        codes = [c.category_code for c in self.categories]
        if len(codes) != len(set(codes)):
            frappe.throw(_("Category Codes must be unique within a budget."))

    def on_update_after_submit(self):
        from boq_budget_control.boq_budget.budget import refresh_summary
        refresh_summary(self)
