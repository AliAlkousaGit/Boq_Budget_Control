import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today


class TestBOQBudgetLedgerEntry(FrappeTestCase):
    def test_create_ledger_entry(self):
        budget = _make_budget()
        cat = budget.items[0].boq_category
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
        "items": [
            {"row_type": "Category", "boq_category": _cat("PRE", "Preliminaries"), "control_action": "Stop"},
            {"row_type": "Item", "item_code": _item(), "qty": 1, "rate": 1000},
        ],
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


def _cat(code, name):
    if not frappe.db.exists("BOQ Budget Category", code):
        frappe.get_doc({"doctype": "BOQ Budget Category",
                        "category_code": code, "category_name": name}).insert()
    return code


def _item(code="TEST-BOQ-LINE-ITEM"):
    if not frappe.db.exists("Item", code):
        frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": code,
                        "item_group": "All Item Groups", "stock_uom": "Nos",
                        "is_stock_item": 0, "is_purchase_item": 1}).insert()
    return code
