# Copyright (c) 2026, BOQ Budget Control and contributors
# For license information, please see license.txt
"""
BOQ Budget Engine — the single source of truth for category-level budget control.

Design model (Approach A): the ledger is the only truth. Every monetary movement is
one ``BOQ Budget Ledger Entry`` row whose ``entry_type`` is one of:

* ``Reserve``  -> reserved bucket +  (e.g. a Purchase Order reserves budget)
* ``Release``  -> reserved bucket -  (e.g. a Purchase Invoice consumes a PO reservation)
* ``Actual``   -> actual bucket +    (a real posted cost)

Cancellations never delete a row. They post a *mirror* row of the **same entry_type**
with the **same magnitude ``amount``** and ``is_reversal = 1``. The sign flip happens
purely in the balance math (see :func:`_signed`), never in the stored amount. This
makes the ledger append-only and robust against cancel / amend.

Only :func:`post_ledger` and :func:`post_reversal` are writers; every other public
function in this module is a pure reader.

Category model: a "category" is identified by the master ``BOQ Budget Category`` name.
Its per-budget allocation (``budget_amount`` / ``control_action``) lives on the
``BOQ Project Budget Category`` child row of the owning ``BOQ Project Budget``.
"""

import frappe
from frappe import _
from frappe.utils import flt, fmt_money, today


# ---------------------------------------------------------------------------
# Sign convention — the single source of sign truth
# ---------------------------------------------------------------------------
def _signed(entry_type, amount, is_reversal=0):
	"""Return the mathematically-signed contribution of a ledger row.

	* ``Release`` rows count negative against the reserved bucket.
	* Any ``is_reversal`` row flips whatever sign it would otherwise have had.
	"""
	sign = -1 if entry_type == "Release" else 1
	if is_reversal:
		sign = -sign
	return sign * flt(amount)


def _allocation(budget, category):
	"""Return ``{budget_amount, control_action}`` for a category's allocation row
	within a budget, or ``None`` when the budget does not allocate that category."""
	return frappe.db.get_value(
		"BOQ Project Budget Category",
		{"parent": budget, "parenttype": "BOQ Project Budget", "boq_category": category},
		["budget_amount", "control_action"],
		as_dict=True,
	)


# ---------------------------------------------------------------------------
# Task 5 — readers: category summary + available
# ---------------------------------------------------------------------------
def get_category_summary(budget, category):
	"""Return ``{budget_amount, reserved, actual, available}`` for one category.

	``reserved`` = Σ signed over {Reserve, Release} rows.
	``actual``   = Σ signed over {Actual} rows (a reversal of an Actual is itself
	               an Actual row, so it is already included via the sign flip).
	``available`` = ``budget_amount`` − ``reserved`` − ``actual``.
	"""
	rows = frappe.db.get_all(
		"BOQ Budget Ledger Entry",
		filters={"boq_project_budget": budget, "boq_category": category},
		fields=["entry_type", "amount", "is_reversal"],
	)

	reserved = 0.0
	actual = 0.0
	for r in rows:
		signed = _signed(r["entry_type"], r["amount"], r["is_reversal"])
		if r["entry_type"] in ("Reserve", "Release"):
			reserved += signed
		elif r["entry_type"] == "Actual":
			actual += signed

	alloc = _allocation(budget, category)
	budget_amount = flt(alloc.budget_amount) if alloc else 0.0
	available = budget_amount - reserved - actual

	return {
		"budget_amount": budget_amount,
		"reserved": reserved,
		"actual": actual,
		"available": available,
	}


def get_available(budget, category):
	"""Return just the available amount for a category (float)."""
	return flt(get_category_summary(budget, category)["available"])


# ---------------------------------------------------------------------------
# Task 6 — refresh_summary: persist computed columns on every category row
# ---------------------------------------------------------------------------
def refresh_summary(budget_name):
	"""Recompute and persist reserved/actual/available for every category row,
	plus the parent's ``total_budget_amount``.

	Uses ``db_set`` (not ``save``) so the submitted parent is not re-validated.
	"""
	budget_doc = frappe.get_doc("BOQ Project Budget", budget_name)
	total_budget = 0.0

	for row in budget_doc.categories:
		summary = get_category_summary(budget_name, row.boq_category)
		row.db_set({
			"reserved_amount": summary["reserved"],
			"actual_amount": summary["actual"],
			"available_amount": summary["available"],
		})
		total_budget += flt(row.budget_amount)

	budget_doc.db_set("total_budget_amount", total_budget)


# ---------------------------------------------------------------------------
# Task 7 — post_ledger: the only way to write a forward ledger row
# ---------------------------------------------------------------------------
def post_ledger(
	entry_type,
	budget,
	category,
	*,
	voucher_type,
	voucher_no,
	voucher_detail_no="",
	amount,
	posting_date=None,
	company=None,
	project=None,
	remarks=None,
):
	"""Insert one ledger row.

	* **Idempotency:** if a non-reversal row already exists for the triple
	  ``(voucher_no, voucher_detail_no, entry_type)``, this is a no-op (returns None).
	* **Zero skip:** a row with ``amount`` of 0 is not posted (returns None).
	* Defaults ``company``/``project`` from the budget when not supplied.
	"""
	if flt(amount) == 0:
		return None

	# Idempotency guard — only forward (non-reversal) rows are matched, so a
	# duplicated doc-event / retry cannot double-count.
	already = frappe.db.exists(
		"BOQ Budget Ledger Entry",
		{
			"voucher_no": voucher_no,
			"voucher_detail_no": voucher_detail_no,
			"entry_type": entry_type,
			"is_reversal": 0,
		},
	)
	if already:
		return None

	if not company or not project:
		budget_doc = frappe.db.get_value(
			"BOQ Project Budget", budget, ["company", "project"], as_dict=True
		)
		company = company or (budget_doc.company if budget_doc else None)
		project = project or (budget_doc.project if budget_doc else None)

	doc = frappe.get_doc({
		"doctype": "BOQ Budget Ledger Entry",
		"posting_date": posting_date or today(),
		"company": company,
		"project": project,
		"boq_project_budget": budget,
		"boq_category": category,
		"voucher_type": voucher_type,
		"voucher_no": voucher_no,
		"voucher_detail_no": voucher_detail_no,
		"entry_type": entry_type,
		"amount": flt(amount),
		"is_reversal": 0,
		"remarks": remarks,
	})
	doc.insert(ignore_permissions=True)
	return doc.name


# ---------------------------------------------------------------------------
# Task 8 — post_reversal: cancel a voucher by mirroring its rows
# ---------------------------------------------------------------------------
def post_reversal(voucher_type, voucher_no):
	"""Post a mirror reversal row for every non-reversal ledger row of a voucher.

	Each mirror carries the **same entry_type and same magnitude** as the original,
	with ``is_reversal = 1`` and ``reverses_voucher_no`` / ``reverses_detail_no``
	pointing back at the original voucher. The sign flip is handled in :func:`_signed`.

	Guarded against duplicate reversals; a no-op if no rows exist. Does not recompute
	summary columns — callers do that via :func:`refresh_summary`.
	"""
	rows = frappe.db.get_all(
		"BOQ Budget Ledger Entry",
		filters={
			"voucher_type": voucher_type,
			"voucher_no": voucher_no,
			"is_reversal": 0,
		},
		fields=[
			"name", "posting_date", "company", "project",
			"boq_project_budget", "boq_category",
			"voucher_detail_no", "entry_type", "amount",
		],
	)

	for r in rows:
		# Skip if a reversal for this exact original already exists.
		if frappe.db.exists(
			"BOQ Budget Ledger Entry",
			{
				"is_reversal": 1,
				"reverses_voucher_no": voucher_no,
				"reverses_detail_no": r.voucher_detail_no,
				"entry_type": r.entry_type,
			},
		):
			continue

		frappe.get_doc({
			"doctype": "BOQ Budget Ledger Entry",
			"posting_date": r.posting_date or today(),
			"company": r.company,
			"project": r.project,
			"boq_project_budget": r.boq_project_budget,
			"boq_category": r.boq_category,
			"voucher_type": voucher_type,
			"voucher_no": voucher_no,
			"voucher_detail_no": r.voucher_detail_no,
			"entry_type": r.entry_type,        # SAME entry_type as the original
			"amount": flt(r.amount),           # SAME magnitude
			"is_reversal": 1,
			"reverses_voucher_no": voucher_no,
			"reverses_detail_no": r.voucher_detail_no,
		}).insert(ignore_permissions=True)


# ---------------------------------------------------------------------------
# Task 9 — validate_row: enforce a category's control_action against a spend
# ---------------------------------------------------------------------------
def validate_row(budget, category, amount, throw=True):
	"""Check ``amount`` against ``available`` under the row's ``control_action``.

	Returns ``(status, available)`` where status is one of ``"ok"``, ``"warn"``,
	``"stop"``. Behaviour:

	* Pass if ``amount <= available`` *or* the action is ``Allow`` -> ``("ok", ...)``.
	* ``Stop`` and over budget -> ``frappe.throw`` (when ``throw``), else ``("stop", ...)``.
	* ``Warn`` and over budget -> ``frappe.msgprint`` (orange, when ``throw``), else ``("warn", ...)``.
	"""
	available = get_available(budget, category)
	alloc = _allocation(budget, category)
	control_action = alloc.control_action if alloc else "Stop"

	if flt(amount) <= available or control_action == "Allow":
		return ("ok", available)

	msg = _("Budget exceeded for this BOQ category: need {0}, available {1}.").format(
		fmt_money(amount), fmt_money(available)
	)

	if control_action == "Stop":
		if throw:
			frappe.throw(msg, frappe.ValidationError)
		return ("stop", available)

	# Warn (and any unexpected value falls through to a warning rather than a hard error)
	if throw:
		frappe.msgprint(msg, indicator="orange")
	return ("warn", available)


# ---------------------------------------------------------------------------
# Extra helper — net reserved for a single PO item
# ---------------------------------------------------------------------------
def get_reserved_for_po_item(po_detail):
	"""Net reserved for a Purchase Order item, summed across all ledger rows
	keyed on ``voucher_detail_no == po_detail``.

	A PO's ``Reserve`` row stores ``voucher_detail_no = po_item_name``; a
	``Release`` row (posted by a linked Purchase Invoice) carries the same
	``voucher_detail_no``. Summing every such row through :func:`_signed`
	yields the still-outstanding reservation.
	"""
	rows = frappe.db.get_all(
		"BOQ Budget Ledger Entry",
		filters={"voucher_detail_no": po_detail},
		fields=["entry_type", "amount", "is_reversal"],
	)
	total = 0.0
	for r in rows:
		total += _signed(r["entry_type"], r["amount"], r["is_reversal"])
	return flt(total)


# ---------------------------------------------------------------------------
# Project-level trigger — does this Project carry an approved BOQ budget?
# ---------------------------------------------------------------------------
def project_has_budget(project, company=None):
	"""Return ``True`` if an approved (``docstatus=1``) BOQ Project Budget exists
	for the project.

	The Purchase Order / Purchase Invoice ``before_submit`` hooks use this to decide
	whether BOQ Project Budget + BOQ Category are mandatory on the document's rows.
	When this is ``False``, budget control is skipped entirely for the document and
	the rows behave like vanilla ERPNext.
	"""
	if not project:
		return False
	filters = {"project": project, "docstatus": 1}
	if company:
		filters["company"] = company
	return bool(frappe.db.exists("BOQ Project Budget", filters))
