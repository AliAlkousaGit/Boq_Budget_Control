import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from boq_budget_control.boq_budget import purchase_invoice_events as pie
from boq_budget_control.boq_budget import purchase_order_events as poe
from boq_budget_control.boq_budget.budget import post_ledger, project_has_budget


class TestProjectBudgetTrigger(FrappeTestCase):
    """The BOQ fields are mandatory on PO/PI only when the HEADER project has an
    approved BOQ Project Budget. Otherwise budget control is skipped entirely.

    Fixtures are picked/created at runtime so the suite runs on any site that has
    at least one Company, Project and Fiscal Year (no hardcoded company/project).
    """

    def setUp(self):
        frappe.db.delete("BOQ Budget Ledger Entry")
        frappe.db.delete("BOQ Project Budget")
        frappe.db.delete("Project", {"project_name": ("like", "BOQ Test Project%")})

        self.company = frappe.db.get_value("Company", {}, "name")  # any existing company
        self.fy = frappe.db.get_value("Fiscal Year", {}, "name")   # any existing fiscal year
        self.cat = _cat("PRE", "Preliminaries")

        self.project = _project(self.company, "BOQ Test Project A")     # carries a budget
        self.no_budget_project = _project(self.company, "BOQ Test Project B")  # never has one

        self.budget = frappe.get_doc({
            "doctype": "BOQ Project Budget", "company": self.company, "project": self.project,
            "fiscal_year": self.fy, "budget_date": today(),
            "categories": [{"boq_category": self.cat,
                            "budget_amount": 1000, "control_action": "Stop"}],
        }).insert()
        self.budget.submit()  # docstatus=1 -> "Approved"

    # ------------------------------------------------------------------ helper
    def test_helper_false_when_no_budget(self):
        self.assertFalse(project_has_budget(self.no_budget_project))
        self.assertFalse(project_has_budget(None))

    def test_helper_true_when_approved_budget(self):
        self.assertTrue(project_has_budget(self.project))

    def test_helper_false_for_draft_budget(self):
        # An unsubmitted (draft) budget does not count as "has a budget".
        frappe.get_doc({
            "doctype": "BOQ Project Budget", "company": self.company,
            "project": self.no_budget_project, "fiscal_year": self.fy, "budget_date": today(),
            "categories": [{"boq_category": self.cat,
                            "budget_amount": 500, "control_action": "Stop"}],
        }).insert()
        self.assertFalse(project_has_budget(self.no_budget_project))

    # ----------------------------------------------------- PO before_submit
    def test_po_skips_when_project_has_no_budget(self):
        doc = _doc(self.no_budget_project, self.company, [_row()])  # no BOQ fields
        poe.before_submit(doc, None)  # must not throw

    def test_po_requires_fields_when_project_has_budget(self):
        doc = _doc(self.project, self.company, [_row()])  # missing boq fields
        self.assertRaises(frappe.ValidationError, poe.before_submit, doc, None)

    def test_po_passes_when_fields_set_and_within_budget(self):
        doc = _doc(self.project, self.company, [
            _row(boq_project_budget=self.budget.name, boq_category=self.cat, amount=100)])
        poe.before_submit(doc, None)  # must not throw

    # ----------------------------------------------------- PI before_submit
    def test_pi_skips_when_project_has_no_budget(self):
        doc = _doc(self.no_budget_project, self.company, [_row()])
        pie.before_submit(doc, None)

    def test_pi_requires_fields_when_project_has_budget(self):
        doc = _doc(self.project, self.company, [_row()])
        self.assertRaises(frappe.ValidationError, pie.before_submit, doc, None)

    def test_pi_passes_when_fields_set_and_within_budget(self):
        doc = _doc(self.project, self.company, [
            _row(boq_project_budget=self.budget.name, boq_category=self.cat, amount=100)])
        pie.before_submit(doc, None)

    # --------------------------------------------- PI linked-to-PO reserved
    def test_pi_linked_po_exceeds_reserved_throws(self):
        # Reserve 500 against a PO item, then invoice 600 against the same PO item.
        post_ledger("Reserve", self.budget.name, self.cat,
                    voucher_type="Purchase Order", voucher_no="PO-L",
                    voucher_detail_no="POD-L", amount=500)
        doc = _doc(self.project, self.company, [
            _row(boq_project_budget=self.budget.name, boq_category=self.cat,
                 amount=600, po_detail="POD-L")])
        self.assertRaises(frappe.ValidationError, pie.before_submit, doc, None)

    def test_pi_linked_po_within_reserved_passes(self):
        post_ledger("Reserve", self.budget.name, self.cat,
                    voucher_type="Purchase Order", voucher_no="PO-L",
                    voucher_detail_no="POD-L", amount=500)
        doc = _doc(self.project, self.company, [
            _row(boq_project_budget=self.budget.name, boq_category=self.cat,
                 amount=400, po_detail="POD-L")])
        pie.before_submit(doc, None)  # must not throw


# --------------------------------------------------------------------------
# Lightweight document/row builders — before_submit only reads .get()/.attr,
# so a small stub stands in for real PO/PI docs without ERPNext fixtures.
# --------------------------------------------------------------------------
class _StubDoc:
    """Stands in for a real PO/PI document.

    A plain ``frappe._dict`` cannot be used: its inherited ``items`` attribute
    (the dict method) would shadow the child-table list that ``before_submit``
    iterates as ``doc.items``.
    """

    def __init__(self, project, company, items):
        self.project = project
        self.company = company
        self.items = items

    def get(self, key, default=None):
        return getattr(self, key, default)


def _doc(project, company, rows):
    return _StubDoc(project, company, rows)


def _row(boq_project_budget=None, boq_category=None, amount=0, po_detail=None, idx=1):
    return frappe._dict({
        "idx": idx,
        "boq_project_budget": boq_project_budget,
        "boq_category": boq_category,
        "po_detail": po_detail,
        "base_net_amount": amount,
        "qty": 1,
        "rate": amount,
    })


def _project(company, title):
    """Create a throwaway Project. project_name is unique in ERPNext, so a random
    suffix avoids collisions across test methods/runs (the module runner does not
    roll back between tests)."""
    options = (frappe.get_meta("Project").get_field("naming_series").options or "").split("\n")
    return frappe.get_doc({
        "doctype": "Project",
        "naming_series": options[0].strip(),
        "project_name": f"{title} {frappe.utils.random_string(6)}",
        "company": company,
    }).insert().name


def _cat(code, name):
    """Ensure a master BOQ Budget Category exists; return its name (= code)."""
    if not frappe.db.exists("BOQ Budget Category", code):
        frappe.get_doc({"doctype": "BOQ Budget Category",
                        "category_code": code, "category_name": name}).insert()
    return code
