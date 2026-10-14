// Copyright (c) 2026, BOQ Budget Control and contributors
// BOQ Project Budget — single two-level BOQ table (BOQ Budget Item).
//
//   1     Category   [+ Add Item]     BOQ Category, Overhead %, Control  (Button field add_item)
//   1.1   Item                       Item, Qty, Rate  -> amount = qty × rate
//   1.2   Item
//   2     Category   [+ Add Item]
//
// Rows are only added through the buttons: "Add Category" under the table and
// "+ Add Item" on each category row. No. is generated automatically, and the
// rows are kept in hierarchy order. The server validate() repeats the same
// numbering / totals and is the source of truth.

const BOQ_ROW = "BOQ Budget Item";

frappe.ui.form.on("BOQ Project Budget", {
	setup(frm) {
		frm.set_query("item_code", "items", () => ({ filters: { disabled: 0 } }));
	},
	refresh(frm) {
		frm.set_df_property("items", "cannot_add_rows", 1);
		boq_add_category_button(frm);
		boq_renumber(frm, false);
	},
	items_on_form_rendered(frm) {
		boq_decorate_rows(frm);
	},
});

frappe.ui.form.on(BOQ_ROW, {
	// rows added any other way (e.g. "Insert Below" in the row editor)
	// become items of the category above them
	items_add(frm, cdt, cdn) {
		if (frm.__boq_adding) return;
		const items = frm.doc.items || [];
		const pos = items.findIndex((r) => r.name === cdn);
		let cat = null;
		for (let i = pos - 1; i >= 0; i--) {
			if (items[i].row_type === "Category") {
				cat = items[i];
				break;
			}
			if (items[i].row_type === "Item" && items[i].boq_category) {
				cat = { boq_category: items[i].boq_category };
				break;
			}
		}
		const row = locals[cdt][cdn];
		if (cat && cat.boq_category) {
			row.row_type = "Item";
			row.boq_category = cat.boq_category;
		} else {
			row.row_type = "Category";
			row.control_action = "Stop";
		}
		boq_renumber(frm);
	},
	items_remove(frm) {
		boq_drop_orphan_items(frm);
		boq_renumber(frm);
	},
	boq_category(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.row_type !== "Category") return;
		const dup = (frm.doc.items || []).some(
			(r) => r.name !== cdn && r.row_type === "Category" && r.boq_category && r.boq_category === row.boq_category
		);
		if (dup) {
			frappe.msgprint(__("Category {0} is already in this BOQ.", ["<b>" + frappe.utils.escape_html(row.boq_category) + "</b>"]));
			frappe.model.set_value(cdt, cdn, "boq_category", (frm.__boq_prev_cat || {})[cdn] || "");
			return;
		}
		// move this category's items along with it
		const old = (frm.__boq_prev_cat || {})[cdn];
		(frm.doc.items || []).forEach((r) => {
			if (r.row_type === "Item" && old && r.boq_category === old) r.boq_category = row.boq_category;
		});
		boq_renumber(frm);
	},
	// native Button field on category rows
	add_item(frm, cdt, cdn) {
		boq_add_item(frm, cdn);
	},
	qty: (frm) => boq_renumber(frm),
	rate: (frm) => boq_renumber(frm),
	overhead_percentage: (frm) => boq_renumber(frm),
});

// ---------------------------------------------------------------------------
// Adding rows
// ---------------------------------------------------------------------------
function boq_add_category_button(frm) {
	const grid = frm.fields_dict.items && frm.fields_dict.items.grid;
	if (!grid) return;
	if (!grid.__boq_cat_btn) {
		grid.__boq_cat_btn = grid.add_custom_button(__("Add Category"), () => {
			const row = boq_new_row(frm);
			row.row_type = "Category";
			row.control_action = "Stop";
			boq_renumber(frm);
		});
		grid.__boq_cat_btn.removeClass("btn-secondary").addClass("btn-primary");
	}
	grid.__boq_cat_btn.toggle(frm.doc.docstatus === 0);
}

function boq_add_item(frm, cat_name) {
	const cat = locals[BOQ_ROW][cat_name];
	if (!cat) return;
	if (!cat.boq_category) {
		frappe.msgprint(__("Select the BOQ Category on row {0} first.", [cat.line_no || cat.idx]));
		return;
	}
	// appended, then boq_renumber() places it after the category's last item
	const row = boq_new_row(frm);
	row.row_type = "Item";
	row.boq_category = cat.boq_category;
	boq_renumber(frm);
}

function boq_new_row(frm) {
	frm.__boq_adding = true;
	try {
		return frappe.model.add_child(frm.doc, BOQ_ROW, "items");
	} finally {
		frm.__boq_adding = false;
	}
}

// Deleting a category also deletes its items.
function boq_drop_orphan_items(frm) {
	const cats = new Set(
		(frm.doc.items || []).filter((r) => r.row_type === "Category" && r.boq_category).map((r) => r.boq_category)
	);
	const orphans = (frm.doc.items || []).filter(
		(r) => r.row_type === "Item" && r.boq_category && !cats.has(r.boq_category)
	);
	if (!orphans.length) return;
	orphans.forEach((r) => frappe.model.clear_doc(BOQ_ROW, r.name));
	frm.doc.items = (frm.doc.items || []).filter((r) => !orphans.includes(r));
	frappe.show_alert({ message: __("{0} item row(s) of the deleted category removed", [orphans.length]), indicator: "orange" });
}

// ---------------------------------------------------------------------------
// Ordering, numbering, totals
// ---------------------------------------------------------------------------
function boq_renumber(frm, mark_dirty = true) {
	const items = frm.doc.items || [];
	const cats = items.filter((r) => r.row_type === "Category");
	const placed = new Set();
	const ordered = [];
	let total = 0;

	cats.forEach((cat, ci) => {
		const c_no = ci + 1;
		cat.line_no = String(c_no);
		ordered.push(cat);
		placed.add(cat.name);

		let amount = 0;
		let i_no = 0;
		items.forEach((r) => {
			if (r.row_type !== "Item" || placed.has(r.name)) return;
			if (!cat.boq_category || r.boq_category !== cat.boq_category) return;
			i_no += 1;
			r.line_no = c_no + "." + i_no;
			r.amount = flt(r.qty) * flt(r.rate);
			amount += flt(r.amount);
			ordered.push(r);
			placed.add(r.name);
		});

		const oh = flt(cat.overhead_percentage);
		cat.amount = amount;
		cat.budget_amount = flt(amount * (1 - oh / 100));
		cat.net_budget_percent = 100 - oh;
		total += flt(cat.budget_amount);
	});

	// anything left (e.g. an item whose category was never chosen) goes last
	items.forEach((r) => {
		if (!placed.has(r.name)) {
			r.line_no = "";
			ordered.push(r);
		}
	});

	ordered.forEach((r, i) => (r.idx = i + 1));
	frm.doc.items = ordered;

	frm.__boq_prev_cat = {};
	cats.forEach((c) => (frm.__boq_prev_cat[c.name] = c.boq_category));

	frm.doc.total_budget_amount = flt(total);
	if (mark_dirty && frm.doc.docstatus === 0) frm.dirty();
	frm.refresh_field("items");
	frm.refresh_field("total_budget_amount");
	boq_decorate_rows(frm);
	boq_render_summary(frm);
}

// ---------------------------------------------------------------------------
// Row look: category rows bold + shaded
// ---------------------------------------------------------------------------
function boq_decorate_rows(frm) {
	// grid rows render asynchronously after refresh_field
	setTimeout(() => boq_decorate_rows_now(frm), 50);
}

function boq_decorate_rows_now(frm) {
	const grid = frm.fields_dict.items && frm.fields_dict.items.grid;
	if (!grid || !grid.wrapper) return;
	if (!grid.wrapper.find("#boq-row-style").length) {
		grid.wrapper.append(
			'<style id="boq-row-style">' +
				".boq-cat-row { background-color: var(--subtle-fg, #f3f3f3); }" +
				".boq-cat-row .static-area { font-weight: 700; }" +
				".boq-item-row [data-fieldname='item_code'] .static-area { padding-left: 16px; }" +
				"</style>"
		);
	}
	(grid.grid_rows || []).forEach((grid_row) => {
		const doc = grid_row.doc;
		if (!doc) return;
		const is_cat = doc.row_type === "Category";
		grid_row.wrapper.toggleClass("boq-cat-row", is_cat);
		grid_row.wrapper.toggleClass("boq-item-row", !is_cat);

	});
}

// Read-only per-category summary under the table.
function boq_render_summary(frm) {
	const field = frm.fields_dict.category_summary_html;
	if (!field) return;
	const cats = (frm.doc.items || []).filter((r) => r.row_type === "Category");
	if (!cats.length) {
		field.$wrapper.empty();
		return;
	}
	const cur = (v) => format_currency(flt(v), frappe.defaults.get_default("currency"));
	const pct = (v) => (flt(v) ? flt(v, 2) + "%" : "");
	const esc = frappe.utils.escape_html;
	const submitted = frm.doc.docstatus === 1;
	let body = "";
	cats.forEach((c) => {
		const red = submitted && flt(c.available_amount) <= 0 ? ' style="color: var(--red-600, #c0392b)"' : "";
		body +=
			"<tr>" +
			`<td>${esc(c.line_no || "")}</td>` +
			`<td>${esc(c.description || c.boq_category || "")}</td>` +
			`<td class="text-right">${cur(c.amount)}</td>` +
			`<td class="text-right">${pct(c.overhead_percentage)}</td>` +
			`<td class="text-right"><b>${cur(c.budget_amount)}</b></td>` +
			`<td>${esc(c.control_action || "")}</td>` +
			(submitted
				? `<td class="text-right">${cur(c.reserved_amount)}</td>` +
				  `<td class="text-right">${cur(c.actual_amount)}</td>` +
				  `<td class="text-right"${red}>${cur(c.available_amount)}</td>` +
				  `<td class="text-right">${pct(c.overall_budget_spent_percentage)}</td>`
				: "") +
			"</tr>";
	});
	const th = (t, right) => `<th${right ? ' class="text-right"' : ""}>${__(t)}</th>`;
	const head =
		"<tr>" + th("No.") + th("Category") + th("Amount", 1) + th("Overhead %", 1) + th("Budget", 1) + th("Control") +
		(submitted ? th("Reserved", 1) + th("Actual", 1) + th("Available", 1) + th("Spent % of total", 1) : "") +
		"</tr>";
	field.$wrapper.html(
		'<div class="text-muted small" style="margin: 8px 0 4px">' + __("Category summary") + "</div>" +
			'<table class="table table-bordered table-sm" style="font-size: 12px">' +
			"<thead>" + head + "</thead><tbody>" + body + "</tbody></table>"
	);
}
