import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, today


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

    def test_po_submit_reserves_and_cancel_reverses(self):
        from boq_budget_control.boq_budget.budget import get_available
        budget = _approved_budget_one_cat(1000, "Stop", "ELE", "Electrical Work")
        cat = budget.categories[0].name
        po = _make_po(budget.name, cat, 600)
        po.submit()
        self.assertEqual(flt(get_available(budget.name, cat)), 400)
        self.assertTrue(frappe.db.exists("BOQ Budget Ledger Entry",
                        {"voucher_no": po.name, "entry_type": "Reserve", "is_reversal": 0}))
        po.cancel()
        self.assertEqual(flt(get_available(budget.name, cat)), 1000)

    def test_pi_direct_consumes_actual(self):
        from boq_budget_control.boq_budget.budget import get_available
        budget = _approved_budget_one_cat(300, "Stop", "PLB", "Plumbing Work")
        cat = budget.categories[0].name
        pi = _make_pi(budget.name, cat, 120)
        pi.submit()
        self.assertEqual(flt(get_available(budget.name, cat)), 180)
        pi.cancel()
        self.assertEqual(flt(get_available(budget.name, cat)), 300)

    def test_pi_linked_to_po_releases_and_actuals(self):
        from boq_budget_control.boq_budget.budget import get_category_summary
        budget = _approved_budget_one_cat(1000, "Stop", "BLK", "Block Work")
        cat = budget.categories[0].name
        po = _make_po(budget.name, cat, 500)
        po.submit()  # reserved 500
        self.assertEqual(flt(get_category_summary(budget.name, cat)["reserved"]), 500)
        pi = _make_pi(budget.name, cat, 500, po_name=po.name, po_detail=po.items[0].name)
        pi.submit()  # release 500 + actual 500
        s = get_category_summary(budget.name, cat)
        self.assertEqual(flt(s["reserved"]), 0)
        self.assertEqual(flt(s["actual"]), 500)


def _ensure_fiscal_year():
    # Reuse the Frappe-seeded test fiscal year to avoid overlap conflicts with
    # the global "2026" FY that the framework creates at test setup time.
    fy = "_Test Fiscal Year 2027"
    if not frappe.db.exists("Fiscal Year", fy):
        frappe.get_doc({"doctype": "Fiscal Year", "year": fy,
                        "year_start_date": "2027-01-01", "year_end_date": "2027-12-31"}).insert()
    return fy


def _approved_budget_one_cat(amount, action, code="PRE", name="Preliminaries"):
    b = frappe.get_doc({
        "doctype": "BOQ Project Budget", "company": "CPC", "project": "PROJ-0001",
        "fiscal_year": _ensure_fiscal_year(), "budget_date": today(),
        "categories": [{"category_code": code, "category_name": name,
                        "budget_amount": amount, "control_action": action}],
    }).insert()
    b.submit()
    return b


def _make_po(budget, category, amount):
    return frappe.get_doc({
        "doctype": "Purchase Order", "supplier": _test_supplier(),
        "company": "CPC", "set_warehouse": _test_warehouse(),
        "schedule_date": today(),
        "items": [{"item_code": _test_item(), "qty": 1, "rate": amount, "project": "PROJ-0001",
                   "boq_project_budget": budget, "boq_category": category}],
    }).insert()


def _make_pi(budget, category, amount, po_name=None, po_detail=None):
    row = {"item_code": _test_item(), "qty": 1, "rate": amount, "project": "PROJ-0001",
           "boq_project_budget": budget, "boq_category": category,
           "expense_account": _test_expense_account()}
    if po_name and po_detail:
        row["purchase_order"] = po_name
        row["po_detail"] = po_detail
    return frappe.get_doc({
        "doctype": "Purchase Invoice", "supplier": _test_supplier(),
        "company": "CPC", "posting_date": today(),
        "items": [row],
    }).insert()


def _test_item():
    code = "TEST-BOQ-ITEM"
    if not frappe.db.exists("Item", code):
        frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": "Test BOQ Item",
                        "item_group": "All Item Groups", "stock_uom": "Nos",
                        "is_stock_item": 0, "is_purchase_item": 1}).insert()
    return code


def _test_supplier():
    name = "Test BOQ Supplier"
    if not frappe.db.exists("Supplier", name):
        frappe.get_doc({"doctype": "Supplier", "supplier_name": name,
                        "supplier_group": _test_supplier_group()}).insert()
    return name


def _test_supplier_group():
    g = "All Supplier Groups"
    if not frappe.db.exists("Supplier Group", g):
        frappe.get_doc({"doctype": "Supplier Group", "supplier_group_name": g}).insert()
    return g


def _test_warehouse():
    return frappe.db.get_value("Warehouse", {"company": "CPC", "is_group": 0})


def _test_expense_account():
    # An expense-type account for CPC so the non-stock PI item posts cleanly.
    acc = frappe.db.get_value("Account",
        {"company": "CPC", "root_type": "Expense", "is_group": 0}, "name")
    return acc
