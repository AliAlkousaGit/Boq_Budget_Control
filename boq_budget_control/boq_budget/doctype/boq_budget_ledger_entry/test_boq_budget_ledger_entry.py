import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today


class TestBOQBudgetLedgerEntry(FrappeTestCase):
    def test_create_ledger_entry(self):
        budget = _make_budget()
        cat = budget.categories[0].name
        doc = frappe.get_doc({
            "doctype": "BOQ Budget Ledger Entry",
            "posting_date": today(), "company": budget.company,
            "project": budget.project, "boq_project_budget": budget.name,
            "boq_category": cat, "voucher_type": "Project", "voucher_no": budget.project,
            "entry_type": "Reserve", "amount": 100,
        })
        doc.insert()
        self.assertEqual(doc.amount, 100)


def _make_budget():
    from frappe.utils import today
    fy = _fy()
    doc = frappe.get_doc({
        "doctype": "BOQ Project Budget", "company": "CPC", "project": "PROJ-0001",
        "fiscal_year": fy, "budget_date": today(),
        "categories": [{"category_code": "PRE", "category_name": "Preliminaries", "budget_amount": 1000, "control_action": "Stop"}],
    })
    doc.insert()
    return doc


def _fy():
    # Reuse the Frappe-seeded test fiscal year to avoid overlap errors on this site
    fy = "_Test Fiscal Year 2027"
    if not frappe.db.exists("Fiscal Year", fy):
        frappe.get_doc({"doctype": "Fiscal Year", "year": fy,
                        "year_start_date": "2027-01-01", "year_end_date": "2027-12-31"}).insert()
    return fy
