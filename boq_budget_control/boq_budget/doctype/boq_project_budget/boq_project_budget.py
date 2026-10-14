# Copyright (c) 2026, BOQ Budget Control and contributors
# For license information, please see license.txt
"""BOQ Project Budget — one hierarchical BOQ table, two levels.

    No.   Row type   User enters                           Calculated
    1     Category   BOQ Category, Overhead %, Control     amount = Σ its items
    1.1   Item       Item, Qty, Rate                       amount = qty × rate
    1.2   Item
    2     Category
    2.1   Item

``No.`` is never typed: it is regenerated on every save from the structure.
An Item row belongs to the Category row with the same ``boq_category``
(rows added with the "+ Add Item" button carry it); an Item row without a
category falls under the nearest Category row above it. Rows are re-ordered
so each category is followed by its own items.

Category rows carry the budget allocation read by the PO / PI engine
(``budget_amount``, ``control_action``) and the cached summary columns written
by ``budget.refresh_summary`` (reserved / actual / available / spent %).
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

CATEGORY = "Category"
ITEM = "Item"

# Fields that only make sense on one row type; cleared on the other.
_CATEGORY_ONLY = (
	"overhead_percentage", "budget_amount", "net_budget_percent",
	"reserved_amount", "actual_amount", "available_amount",
	"overall_budget_spent_percentage",
)
_ITEM_ONLY = ("item_code", "uom", "qty", "rate")


class BOQProjectBudget(Document):
	def validate(self):
		self._build_hierarchy()
		self.total_budget_amount = sum(
			flt(r.budget_amount) for r in self.items if r.row_type == CATEGORY
		)

	# ------------------------------------------------------------------
	def _build_hierarchy(self):
		rows = sorted(self.items or [], key=lambda r: r.idx or 0)
		if not rows:
			frappe.throw(_("Add at least one Category with its items."))

		for row in rows:
			if row.row_type not in (CATEGORY, ITEM):
				row.row_type = ITEM if row.item_code else CATEGORY

		# 1. categories, in the order they appear
		categories = []
		by_category = {}
		for row in rows:
			if row.row_type != CATEGORY:
				continue
			if not row.boq_category:
				frappe.throw(_("Row {0}: select the BOQ Category.").format(row.idx))
			if row.boq_category in by_category:
				frappe.throw(
					_("BOQ Category {0} is added more than once. A category may only appear once.").format(
						frappe.bold(row.boq_category)
					)
				)
			by_category[row.boq_category] = {"row": row, "items": []}
			categories.append(row.boq_category)

		# 2. attach items to their category (explicit link, else nearest category above)
		current = None
		for row in rows:
			if row.row_type == CATEGORY:
				current = row.boq_category
				continue
			category = row.boq_category if row.boq_category in by_category else None
			if not category and not row.boq_category:
				category = current
			if not category:
				frappe.throw(
					_("Row {0}: Item {1} is not under any Category. Add it with the "
					  "'+ Add Item' button of a category.").format(row.idx, frappe.bold(row.item_code or ""))
				)
			by_category[category]["items"].append(row)

		# 3. re-order + number: 1, 1.1, 1.2, 2, 2.1 …
		ordered = []
		for c_no, category in enumerate(categories, 1):
			group = by_category[category]
			cat_row = group["row"]
			cat_row.line_no = str(c_no)
			self._prepare_category(cat_row)
			ordered.append(cat_row)

			seen_items = {}
			for i_no, item in enumerate(group["items"], 1):
				item.line_no = f"{c_no}.{i_no}"
				item.boq_category = category
				self._prepare_item(item)
				if item.item_code in seen_items:
					frappe.throw(
						_("Item {0} is listed twice under {1} (No. {2} and {3}).").format(
							frappe.bold(item.item_code), frappe.bold(cat_row.description or category),
							seen_items[item.item_code], item.line_no,
						)
					)
				seen_items[item.item_code] = item.line_no
				ordered.append(item)

			self._calculate_category(cat_row, group["items"])

		for idx, row in enumerate(ordered, 1):
			row.idx = idx
		self.items = ordered

	def _prepare_category(self, row):
		for f in _ITEM_ONLY:
			row.set(f, None)
		row.description = frappe.db.get_value("BOQ Budget Category", row.boq_category, "category_name")
		row.control_action = row.control_action or "Stop"

	def _prepare_item(self, row):
		if not row.item_code:
			frappe.throw(_("No. {0}: select the Item.").format(row.line_no))
		if flt(row.qty) <= 0:
			frappe.throw(_("No. {0}: Qty must be greater than 0.").format(row.line_no))
		if flt(row.rate) < 0:
			frappe.throw(_("No. {0}: Rate cannot be negative.").format(row.line_no))

		for f in _CATEGORY_ONLY:
			row.set(f, None)
		row.control_action = None

		if not row.description or not row.uom:
			item = frappe.db.get_value("Item", row.item_code, ["item_name", "stock_uom"], as_dict=True) or {}
			row.description = row.description or item.get("item_name")
			row.uom = row.uom or item.get("stock_uom")

		row.amount = flt(row.qty) * flt(row.rate)

	def _calculate_category(self, row, items):
		row.amount = sum(flt(i.amount) for i in items)
		overhead = flt(row.overhead_percentage)
		if overhead < 0 or overhead > 100:
			frappe.throw(_("No. {0}: Overhead % must be between 0 and 100.").format(row.line_no))
		row.budget_amount = flt(row.amount) * (1 - overhead / 100.0)
		row.net_budget_percent = 100.0 - overhead

	def on_update_after_submit(self):
		from boq_budget_control.boq_budget.budget import refresh_summary

		refresh_summary(self.name)
