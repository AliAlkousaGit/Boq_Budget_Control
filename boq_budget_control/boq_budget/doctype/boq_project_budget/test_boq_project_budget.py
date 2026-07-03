import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today


class TestBOQProjectBudget(FrappeTestCase):
    def test_total_is_sum_of_categories(self):
        doc = frappe.get_doc({
            "doctype": "BOQ Project Budget",
            "company": "CPC",
            "project": "PROJ-0001",
            "fiscal_year": _ensure_fiscal_year(),
            "budget_date": today(),
            "categories": [
                {"category_code": "PRE", "category_name": "Preliminaries", "budget_amount": 1000, "control_action": "Stop"},
                {"category_code": "SUB", "category_name": "Sub Structure", "budget_amount": 500, "control_action": "Warn"},
            ],
        })
        doc.insert()
        self.assertEqual(doc.total_budget_amount, 1500)

    def test_submit_locks_amount(self):
        doc = frappe.get_doc({
            "doctype": "BOQ Project Budget",
            "company": "CPC", "project": "PROJ-0001",
            "fiscal_year": _ensure_fiscal_year(), "budget_date": today(),
            "categories": [{"category_code": "PRE", "category_name": "Preliminaries", "budget_amount": 1000, "control_action": "Stop"}],
        })
        doc.insert(); doc.submit()
        self.assertEqual(doc.docstatus, 1)


def _ensure_fiscal_year():
    # Reuse the Frappe-seeded test fiscal year to avoid overlap conflicts with
    # the global "2026" FY that the framework creates at test setup time.
    fy = "_Test Fiscal Year 2027"
    if not frappe.db.exists("Fiscal Year", fy):
        frappe.get_doc({"doctype": "Fiscal Year", "year": fy,
                        "year_start_date": "2027-01-01", "year_end_date": "2027-12-31"}).insert()
    return fy
