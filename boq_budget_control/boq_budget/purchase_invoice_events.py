# Copyright (c) 2026, BOQ Budget Control and contributors
# For license information, please see license.txt

"""Purchase Invoice BOQ budget events."""

import frappe
from frappe import _
from frappe.utils import flt

from boq_budget_control.boq_budget.budget import (
    get_reserved_for_po_item,
    post_ledger,
    post_reversal,
    project_has_budget,
    refresh_summary,
    validate_row,
)


def _row_amount(item):
    """Return controlled amount in company currency, excluding tax."""
    return flt(item.get("base_net_amount")) or flt(item.qty) * flt(item.rate)


def _require(item, header_project):
    budget = item.get("boq_project_budget")
    category = item.get("boq_category")

    if not (budget and category):
        frappe.throw(
            _(
                "Row {0}: BOQ Project Budget and BOQ Category are required "
                "(Project {1} has a BOQ budget)."
            ).format(item.idx, header_project)
        )

    if frappe.db.get_value("BOQ Project Budget", budget, "docstatus") != 1:
        frappe.throw(
            _("Row {0}: BOQ Project Budget must be Approved.").format(item.idx)
        )

    if frappe.db.get_value("BOQ Project Budget", budget, "is_closed"):
        frappe.throw(
            _("Row {0}: BOQ Project Budget is closed.").format(item.idx)
        )

    return budget, category


def _is_legacy_po_item(item):
    """
    Return True when the linked PO item predates BOQ control.

    A legacy PO item has:
    - no BOQ Project Budget;
    - no BOQ Category;
    - no forward Reserve ledger entry.
    """
    if not item.get("po_detail"):
        return False

    po_item = frappe.db.get_value(
        "Purchase Order Item",
        item.po_detail,
        [
            "parent",
            "boq_project_budget",
            "boq_category",
        ],
        as_dict=True,
    )

    if not po_item:
        frappe.throw(
            _("Row {0}: linked Purchase Order item was not found.").format(
                item.idx
            )
        )

    has_reserve_entry = frappe.db.exists(
        "BOQ Budget Ledger Entry",
        {
            "voucher_type": "Purchase Order",
            "voucher_no": po_item.parent,
            "voucher_detail_no": item.po_detail,
            "entry_type": "Reserve",
            "is_reversal": 0,
        },
    )

    return (
        not po_item.boq_project_budget
        and not po_item.boq_category
        and not has_reserve_entry
    )


def before_submit(doc, method=None):
    # Apply BOQ control only when the header project has an approved budget.
    if not project_has_budget(doc.get("project"), doc.get("company")):
        return

    for item in doc.items:
        budget, category = _require(item, doc.project)
        amount = _row_amount(item)

        if not item.get("po_detail"):
            # Direct PI without a Purchase Order.
            validate_row(budget, category, amount)
            continue

        reserved = get_reserved_for_po_item(item.po_detail)

        if reserved > 0:
            # Standard controlled PO flow.
            if amount > reserved + 0.01:
                frappe.throw(
                    _(
                        "Row {0}: amount {1} exceeds reserved {2} "
                        "for the linked Purchase Order item."
                    ).format(item.idx, amount, reserved)
                )

        elif _is_legacy_po_item(item):
            # Legacy PO had no reservation, so consume available budget directly.
            validate_row(budget, category, amount)

        else:
            # A controlled PO with no reservation indicates missing or consumed data.
            frappe.throw(
                _(
                    "Row {0}: the linked Purchase Order has no remaining BOQ "
                    "reservation. Verify the PO budget allocation, cancellation "
                    "status, or previous Purchase Invoices."
                ).format(item.idx)
            )


def on_submit(doc, method=None):
    budgets = set()

    for item in doc.items:
        if not (
            item.get("boq_project_budget")
            and item.get("boq_category")
        ):
            continue

        amount = _row_amount(item)

        if item.get("po_detail"):
            reserved = get_reserved_for_po_item(item.po_detail)

            # Do not post a Release for a legacy PO with no reservation.
            if reserved > 0:
                post_ledger(
                    "Release",
                    item.boq_project_budget,
                    item.boq_category,
                    voucher_type="Purchase Invoice",
                    voucher_no=doc.name,
                    voucher_detail_no=item.po_detail,
                    amount=amount,
                    posting_date=doc.posting_date,
                )

        post_ledger(
            "Actual",
            item.boq_project_budget,
            item.boq_category,
            voucher_type="Purchase Invoice",
            voucher_no=doc.name,
            voucher_detail_no=item.name,
            amount=amount,
            posting_date=doc.posting_date,
        )

        budgets.add(item.boq_project_budget)

    for budget in budgets:
        refresh_summary(budget)


def on_cancel(doc, method=None):
    budgets = {
        item.boq_project_budget
        for item in doc.items
        if item.get("boq_project_budget")
    }

    post_reversal("Purchase Invoice", doc.name)

    for budget in budgets:
        refresh_summary(budget)