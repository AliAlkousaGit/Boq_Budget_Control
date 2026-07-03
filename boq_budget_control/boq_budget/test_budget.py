import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, today


class TestBudgetEngine(FrappeTestCase):
    def setUp(self):
        frappe.db.delete("BOQ Budget Ledger Entry")
        frappe.db.delete("BOQ Project Budget")
        self.cat = _cat("PRE", "Preliminaries")
        self.budget = frappe.get_doc({
            "doctype": "BOQ Project Budget", "company": "CPC", "project": "PROJ-0001",
            "fiscal_year": _fy(), "budget_date": today(),
            "categories": [{"boq_category": self.cat,
                            "budget_amount": 1000, "control_action": "Stop"}],
        }).insert()

    # Task 5
    def test_summary_empty(self):
        from boq_budget_control.boq_budget.budget import get_category_summary, get_available
        s = get_category_summary(self.budget.name, self.cat)
        self.assertEqual(flt(s["reserved"]), 0)
        self.assertEqual(flt(s["actual"]), 0)
        self.assertEqual(flt(s["available"]), 1000)

    def test_available_matches_summary(self):
        from boq_budget_control.boq_budget.budget import get_category_summary, get_available
        _ledger(self.budget, self.cat, "Reserve", 300)
        self.assertEqual(flt(get_available(self.budget.name, self.cat)), 700)

    # Task 6
    def test_refresh_summary_writes_columns(self):
        from boq_budget_control.boq_budget.budget import refresh_summary
        _ledger(self.budget, self.cat, "Reserve", 300)
        _ledger(self.budget, self.cat, "Actual", 200)
        refresh_summary(self.budget.name)
        # summary columns now live on the allocation child row, not the master
        row = frappe.db.get_value("BOQ Project Budget Category",
            {"parent": self.budget.name, "boq_category": self.cat},
            ["reserved_amount", "actual_amount", "available_amount"], as_dict=True)
        self.assertEqual(flt(row["reserved_amount"]), 300)
        self.assertEqual(flt(row["actual_amount"]), 200)
        self.assertEqual(flt(row["available_amount"]), 500)

    # Task 7
    def test_post_ledger_is_idempotent(self):
        from boq_budget_control.boq_budget.budget import post_ledger, refresh_summary, get_available
        args = {"voucher_type": "Purchase Order", "voucher_no": "PO-TEST-1", "voucher_detail_no": "POD-1", "amount": 250}
        post_ledger("Reserve", self.budget.name, self.cat, **args)
        post_ledger("Reserve", self.budget.name, self.cat, **args)  # duplicate -> skipped
        refresh_summary(self.budget.name)
        self.assertEqual(flt(get_available(self.budget.name, self.cat)), 750)

    # Task 8
    def test_post_reversal_nets_to_zero(self):
        from boq_budget_control.boq_budget.budget import post_ledger, post_reversal, refresh_summary, get_available
        post_ledger("Reserve", self.budget.name, self.cat, voucher_type="Purchase Order", voucher_no="PO-TEST-2", voucher_detail_no="POD-2", amount=400)
        refresh_summary(self.budget.name)
        self.assertEqual(flt(get_available(self.budget.name, self.cat)), 600)
        post_reversal("Purchase Order", "PO-TEST-2")
        refresh_summary(self.budget.name)
        self.assertEqual(flt(get_available(self.budget.name, self.cat)), 1000)

    # Task 8 — release + actual on PI linked to PO, then cancel PI
    def test_release_actual_and_cancel(self):
        from boq_budget_control.boq_budget.budget import post_ledger, post_reversal, refresh_summary, get_category_summary
        post_ledger("Reserve", self.budget.name, self.cat, voucher_type="Purchase Order", voucher_no="PO-X", voucher_detail_no="POD-X", amount=500)
        post_ledger("Release", self.budget.name, self.cat, voucher_type="Purchase Invoice", voucher_no="PI-X", voucher_detail_no="PID-X", amount=500)
        post_ledger("Actual", self.budget.name, self.cat, voucher_type="Purchase Invoice", voucher_no="PI-X", voucher_detail_no="PID-X", amount=500)
        refresh_summary(self.budget.name)
        s = get_category_summary(self.budget.name, self.cat)
        self.assertEqual(flt(s["reserved"]), 0)     # 500 - 500
        self.assertEqual(flt(s["actual"]), 500)
        # cancel the PI: mirror Release(+500) and Actual(-500)
        post_reversal("Purchase Invoice", "PI-X")
        refresh_summary(self.budget.name)
        s = get_category_summary(self.budget.name, self.cat)
        self.assertEqual(flt(s["reserved"]), 500)   # reservation restored
        self.assertEqual(flt(s["actual"]), 0)

    # Task 9
    def test_validate_row_stop_blocks(self):
        from boq_budget_control.boq_budget.budget import validate_row
        self.assertRaises(frappe.ValidationError, validate_row, self.budget.name, self.cat, 1500)

    def test_validate_row_allow_passes(self):
        from boq_budget_control.boq_budget.budget import validate_row
        self.budget.categories[0].db_set("control_action", "Allow")
        status, available = validate_row(self.budget.name, self.cat, 999999, throw=True)
        self.assertEqual(status, "ok")

    # extra helper
    def test_reserved_for_po_item(self):
        from boq_budget_control.boq_budget.budget import post_ledger, get_reserved_for_po_item
        post_ledger("Reserve", self.budget.name, self.cat, voucher_type="Purchase Order", voucher_no="PO-R", voucher_detail_no="POD-R", amount=700)
        post_ledger("Release", self.budget.name, self.cat, voucher_type="Purchase Invoice", voucher_no="PI-R", voucher_detail_no="POD-R", amount=200)
        self.assertEqual(flt(get_reserved_for_po_item("POD-R")), 500)


def _fy():
    fy = "_Test Fiscal Year 2027"
    if not frappe.db.exists("Fiscal Year", fy):
        frappe.get_doc({"doctype": "Fiscal Year", "year": fy, "year_start_date": "2027-01-01", "year_end_date": "2027-12-31"}).insert()
    return fy


def _cat(code, name):
    """Ensure a master BOQ Budget Category exists; return its name (= code)."""
    if not frappe.db.exists("BOQ Budget Category", code):
        frappe.get_doc({"doctype": "BOQ Budget Category",
                        "category_code": code, "category_name": name}).insert()
    return code


def _ledger(budget, cat, entry_type, amount, **kw):
    return frappe.get_doc({
        "doctype": "BOQ Budget Ledger Entry", "posting_date": today(),
        "company": budget.company, "project": budget.project,
        "boq_project_budget": budget.name, "boq_category": cat,
        "voucher_type": kw.get("voucher_type", "Manual"), "voucher_no": kw.get("voucher_no", "M-001"),
        "voucher_detail_no": kw.get("voucher_detail_no", ""), "entry_type": entry_type, "amount": amount,
    }).insert()
