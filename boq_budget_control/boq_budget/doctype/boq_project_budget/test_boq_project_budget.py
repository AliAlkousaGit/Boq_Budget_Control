import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, today


class TestBOQProjectBudget(FrappeTestCase):
    def test_total_is_sum_of_category_budgets(self):
        doc = _budget([
            _cat_row(_cat("PRE", "Preliminaries"), "Stop"),
            _item_row(1, 1000),
            _cat_row(_cat("SUB", "Sub Structure"), "Warn"),
            _item_row(2, 250),
        ]).insert()
        self.assertEqual(flt(doc.total_budget_amount), 1500)

    def test_submit(self):
        doc = _budget(_lines(_cat("PRE", "Preliminaries"), 1000)).insert()
        doc.submit()
        self.assertEqual(doc.docstatus, 1)

    def test_po_submit_reserves_and_cancel_reverses(self):
        from boq_budget_control.boq_budget.budget import get_available
        budget = _approved_budget_one_cat(1000, "Stop", "ELE", "Electrical Work")
        cat = "ELE"
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
        cat = "PLB"
        pi = _make_pi(budget.name, cat, 120)
        pi.submit()
        self.assertEqual(flt(get_available(budget.name, cat)), 180)
        pi.cancel()
        self.assertEqual(flt(get_available(budget.name, cat)), 300)

    def test_pi_linked_to_po_releases_and_actuals(self):
        from boq_budget_control.boq_budget.budget import get_category_summary
        budget = _approved_budget_one_cat(1000, "Stop", "BLK", "Block Work")
        cat = "BLK"
        po = _make_po(budget.name, cat, 500)
        po.submit()  # reserved 500
        self.assertEqual(flt(get_category_summary(budget.name, cat)["reserved"]), 500)
        pi = _make_pi(budget.name, cat, 500, po_name=po.name, po_detail=po.items[0].name)
        pi.submit()  # release 500 + actual 500
        s = get_category_summary(budget.name, cat)
        self.assertEqual(flt(s["reserved"]), 0)
        self.assertEqual(flt(s["actual"]), 500)


class TestBOQLines(FrappeTestCase):
    """Single two-level BOQ table: numbers are generated, never typed."""

    def test_rollup_overhead_numbering(self):
        lam, pan = _cat("LAM", "Laminates"), _cat("PAN", "Panels/mdf/lipping")
        doc = _budget([
            _cat_row(lam, "Stop", overhead=10),
            _item_row(100, 29.51, _boq_line_item("TEST-LAM-A"), category=lam),
            _item_row(100, 9.03, _boq_line_item("TEST-LAM-B"), category=lam),
            _cat_row(pan, "Warn"),
            _item_row(310, 150, category=pan),
        ]).insert()
        rows = {r.line_no: r for r in doc.items}
        self.assertEqual([r.line_no for r in doc.items], ["1", "1.1", "1.2", "2", "2.1"])
        lam_amount = flt(100 * 29.51 + 100 * 9.03)
        self.assertEqual(rows["1"].row_type, "Category")
        self.assertEqual(rows["1.1"].row_type, "Item")
        self.assertEqual(flt(rows["1"].amount), lam_amount)
        self.assertEqual(flt(rows["1"].budget_amount), flt(lam_amount * 0.9))
        self.assertEqual(flt(rows["1"].net_budget_percent), 90)
        self.assertEqual(flt(rows["2"].budget_amount), flt(310 * 150))
        self.assertEqual(rows["1"].description, "Laminates")
        self.assertEqual(rows["1.1"].uom, "Nos")
        self.assertEqual(flt(doc.total_budget_amount), flt(lam_amount * 0.9 + 310 * 150))

    def test_item_added_later_moves_under_its_category(self):
        lam, pan = _cat("LAM", "Laminates"), _cat("PAN", "Panels/mdf/lipping")
        doc = _budget([
            _cat_row(lam), _item_row(1, 5, category=lam),
            _cat_row(pan), _item_row(1, 5, category=pan),
            _item_row(2, 5, _boq_line_item("TEST-LAM-B"), category=lam),  # added last, belongs to 1
        ]).insert()
        self.assertEqual([(r.line_no, r.boq_category, r.item_code) for r in doc.items], [
            ("1", lam, None), ("1.1", lam, "TEST-BOQ-LINE-ITEM"), ("1.2", lam, "TEST-LAM-B"),
            ("2", pan, None), ("2.1", pan, "TEST-BOQ-LINE-ITEM"),
        ])

    def test_typed_line_no_is_ignored(self):
        lam = _cat("LAM", "Laminates")
        doc = _budget([dict(_cat_row(lam), line_no="7"), dict(_item_row(1, 5), line_no="9.9")]).insert()
        self.assertEqual([r.line_no for r in doc.items], ["1", "1.1"])

    def test_item_without_category_link_falls_under_category_above(self):
        lam = _cat("LAM", "Laminates")
        doc = _budget([_cat_row(lam), _item_row(1, 5)]).insert()
        self.assertEqual(doc.items[1].boq_category, lam)

    def test_item_before_any_category_rejected(self):
        doc = _budget([_item_row(1, 5), _cat_row(_cat("LAM", "Laminates"))])
        self.assertRaises(frappe.ValidationError, doc.insert)

    def test_item_of_missing_category_rejected(self):
        doc = _budget([_cat_row(_cat("LAM", "Laminates")),
                       _item_row(1, 5, category=_cat("PAN", "Panels/mdf/lipping"))])
        self.assertRaises(frappe.ValidationError, doc.insert)

    def test_item_code_required(self):
        doc = _budget([_cat_row(_cat("LAM", "Laminates")), {"row_type": "Item", "qty": 1, "rate": 5}])
        self.assertRaises(frappe.ValidationError, doc.insert)

    def test_qty_must_be_positive(self):
        doc = _budget([_cat_row(_cat("LAM", "Laminates")), _item_row(0, 5)])
        self.assertRaises(frappe.ValidationError, doc.insert)

    def test_category_required_on_category_row(self):
        doc = _budget([{"row_type": "Category"}, _item_row(1, 5)])
        self.assertRaises(frappe.ValidationError, doc.insert)

    def test_duplicate_category_rejected(self):
        lam = _cat("LAM", "Laminates")
        doc = _budget([_cat_row(lam), _item_row(1, 5), _cat_row(lam), _item_row(1, 5)])
        self.assertRaises(frappe.ValidationError, doc.insert)

    def test_same_item_twice_in_category_rejected(self):
        doc = _budget([_cat_row(_cat("LAM", "Laminates")), _item_row(1, 5), _item_row(2, 5)])
        self.assertRaises(frappe.ValidationError, doc.insert)

    def test_same_item_in_two_categories_allowed(self):
        doc = _budget([_cat_row(_cat("LAM", "Laminates")), _item_row(1, 5),
                       _cat_row(_cat("PAN", "Panels/mdf/lipping")), _item_row(1, 5)]).insert()
        self.assertEqual(len(doc.items), 4)

    def test_category_without_items_has_zero_budget(self):
        doc = _budget([_cat_row(_cat("LAM", "Laminates"))]).insert()
        self.assertEqual(flt(doc.items[0].budget_amount), 0)


def _budget(items):
    return frappe.get_doc({
        "doctype": "BOQ Project Budget",
        "company": "CPC", "project": "PROJ-0001",
        "fiscal_year": _ensure_fiscal_year(), "budget_date": today(),
        "items": items,
    })


def _cat_row(category, action="Stop", overhead=0):
    return {"row_type": "Category", "boq_category": category,
            "control_action": action, "overhead_percentage": overhead}


def _item_row(qty, rate, item_code=None, category=None):
    row = {"row_type": "Item", "item_code": item_code or _boq_line_item(), "qty": qty, "rate": rate}
    if category:
        row["boq_category"] = category
    return row


def _lines(category, amount, action="Stop", overhead=0):
    return [_cat_row(category, action, overhead), _item_row(1, amount)]


def _boq_line_item(code="TEST-BOQ-LINE-ITEM"):
    if not frappe.db.exists("Item", code):
        frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": code,
                        "item_group": "All Item Groups", "stock_uom": "Nos",
                        "is_stock_item": 0, "is_purchase_item": 1}).insert()
    return code


def _ensure_fiscal_year():
    # Reuse the Frappe-seeded test fiscal year to avoid overlap conflicts with
    # the global "2026" FY that the framework creates at test setup time.
    fy = "_Test Fiscal Year 2027"
    if not frappe.db.exists("Fiscal Year", fy):
        frappe.get_doc({"doctype": "Fiscal Year", "year": fy,
                        "year_start_date": "2027-01-01", "year_end_date": "2027-12-31"}).insert()
    return fy


def _cat(code, name):
    """Ensure a master BOQ Budget Category exists; return its name (= code)."""
    if not frappe.db.exists("BOQ Budget Category", code):
        frappe.get_doc({"doctype": "BOQ Budget Category",
                        "category_code": code, "category_name": name}).insert()
    return code


def _approved_budget_one_cat(amount, action, code="PRE", name="Preliminaries"):
    b = frappe.get_doc({
        "doctype": "BOQ Project Budget", "company": "CPC", "project": "PROJ-0001",
        "fiscal_year": _ensure_fiscal_year(), "budget_date": today(),
        "items": _lines(_cat(code, name), amount, action),
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
