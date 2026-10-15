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
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Import BOQ"), () => boq_import_dialog(frm));
		}
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

// ---------------------------------------------------------------------------
// Import BOQ (Excel): upload -> server preview -> Apply fills the table (unsaved)
// Parsing / matching rules live in boq_budget/boq_import.py.
// ---------------------------------------------------------------------------
function boq_import_dialog(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Import BOQ (Excel)"),
		fields: [
			{
				fieldname: "file",
				fieldtype: "Attach",
				label: __("BOQ file (.xlsx)"),
				reqd: 1,
				options: { restrictions: { allowed_file_types: [".xlsx"] } },
			},
			{ fieldname: "sheet", fieldtype: "Select", label: __("Sheet"), hidden: 1 },
		],
		primary_action_label: __("Preview"),
		primary_action(values) {
			frappe
				.call({
					method: "boq_budget_control.boq_budget.api.preview_boq_import",
					args: { file_url: values.file, budget: frm.is_new() ? null : frm.doc.name, sheet: values.sheet || null },
					freeze: true,
					freeze_message: __("Reading BOQ…"),
				})
				.then((r) => {
					const p = r.message || {};
					if (p.needs_sheet) {
						d.set_df_property("sheet", "options", p.sheets);
						d.set_df_property("sheet", "hidden", 0);
						d.set_df_property("sheet", "reqd", 1);
						frappe.show_alert({ message: __("This file has several BOQ sheets — choose one."), indicator: "orange" });
						return;
					}
					d.hide();
					boq_import_preview(frm, p);
				});
		},
	});
	d.show();
}

function boq_import_preview(frm, p) {
	const esc = (v) => frappe.utils.escape_html(v == null ? "" : String(v));
	const money = (v) => format_currency(flt(v), frappe.defaults.get_default("currency"));
	const errors = p.errors || [];
	const warnings = p.warnings || [];
	const s = p.summary || {};
	const list = (items, color) =>
		items.length
			? `<ul style="color:${color};margin:4px 0 10px 18px;padding:0">${items.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`
			: "";

	let html = `<div style="font-size:12px">`;
	html += `<p class="text-muted" style="margin-bottom:6px">${__("Sheet")}: <b>${esc(p.sheet)}</b> · ${__("Header row")}: <b>${esc(p.header_row)}</b> · ${__("Columns")}: ${Object.entries(p.columns || {}).map(([k, v]) => `${esc(k)}=${esc(v)}`).join(", ")}</p>`;
	if (s.categories !== undefined) {
		html += `<p><b>${s.categories}</b> ${__("categories")}, <b>${s.lines}</b> ${__("lines")} (${s.unpriced_lines} ${__("unpriced")}), ${__("total")} <b>${money(s.total)}</b></p>`;
	}
	if (errors.length) html += `<h6 style="color:var(--red-600,#c0392b)">${__("Blocking — fix before importing")}</h6>` + list(errors, "var(--red-600,#c0392b)");
	if (warnings.length) html += `<h6 style="color:var(--orange-600,#d35400)">${__("Warnings")}</h6>` + list(warnings, "var(--orange-600,#d35400)");

	html += `<table class="table table-bordered table-sm" style="font-size:12px"><thead><tr>
		<th>${__("Ref")}</th><th>${__("Source category")}</th><th>${__("Matched category")}</th>
		<th class="text-right">${__("Lines")}</th><th class="text-right">${__("Amount")}</th><th class="text-right">${__("Sheet subtotal")}</th></tr></thead><tbody>`;
	(p.categories || []).forEach((c) => {
		const m = c.match
			? `${esc(c.match.category_name)} <span class="text-muted">(${Math.round(c.match.score * 100)}%)</span>`
			: `<span style="color:var(--red-600,#c0392b)">${__("No match")}</span>`;
		const lines = c.lines
			.map(
				(l) => `<tr><td>${esc(l.boq_ref)}</td><td>${esc(String(l.description).slice(0, 120))}</td>
				<td>${esc(l.unit || "")}${l.uom ? " → " + esc(l.uom) : ""}</td><td class="text-right">${flt(l.qty)}</td>
				<td class="text-right">${money(l.rate)}</td><td class="text-right">${money(l.amount)}</td><td>${esc(l.remarks || "")}</td></tr>`
			)
			.join("");
		html += `<tr><td>${esc(c.boq_ref)}</td><td>${esc(c.source_name)}</td><td>${m}</td>
			<td class="text-right">${c.lines.length}</td><td class="text-right">${money(c.amount)}</td>
			<td class="text-right">${c.sheet_subtotal == null ? "" : money(c.sheet_subtotal)}</td></tr>
			<tr><td></td><td colspan="5"><details><summary class="text-muted">${__("Lines")}</summary>
			<table class="table table-sm" style="font-size:11px;margin:4px 0"><thead><tr><th>${__("Ref")}</th><th>${__("Description")}</th><th>${__("Unit")}</th>
			<th class="text-right">${__("Qty")}</th><th class="text-right">${__("Rate")}</th><th class="text-right">${__("Amount")}</th><th>${__("Remarks")}</th></tr></thead>
			<tbody>${lines}</tbody></table></details></td></tr>`;
	});
	html += `</tbody></table>`;

	if ((p.totals || []).length) {
		html += `<p class="text-muted">${__("Sheet totals (reported, not applied)")}: ${p.totals.map((t) => `${esc(t.label)} = ${t.value == null ? "—" : money(t.value)}`).join(" · ")}</p>`;
	}
	if ((p.skipped || []).length) {
		html += `<details><summary class="text-muted">${__("Skipped rows")} (${p.skipped.length})</summary><ul style="margin-left:18px">${p.skipped
			.map((x) => `<li>${__("Row")} ${x.row}: ${esc(x.reason)} — ${esc(x.text)}</li>`)
			.join("")}</ul></details>`;
	}
	html += `</div>`;

	const blocked = errors.length > 0;
	const d = new frappe.ui.Dialog({
		title: __("Import BOQ — Preview"),
		size: "extra-large",
		fields: [
			{ fieldname: "preview", fieldtype: "HTML" },
			{
				fieldname: "default_overhead",
				fieldtype: "Percent",
				label: __("Default Overhead % (applied to every imported category)"),
				default: 0,
				hidden: blocked ? 1 : 0,
			},
		],
		primary_action_label: blocked ? __("Close") : __("Apply"),
		primary_action(values) {
			if (blocked) {
				d.hide();
				return;
			}
			const oh = flt(values.default_overhead);
			if (oh < 0 || oh > 100) {
				frappe.msgprint(__("Overhead % must be between 0 and 100."));
				return;
			}
			const rows = frm.doc.items || [];
			const n_cat = rows.filter((r) => r.row_type === "Category").length;
			const n_lines = rows.length - n_cat;
			const apply = () => {
				boq_import_apply(frm, p, oh);
				d.hide();
			};
			if (rows.some((r) => r.boq_category || r.description || r.item_code)) {
				frappe.confirm(
					__("This will remove the existing {0} categories and {1} lines and replace them with the imported BOQ. Continue?", [n_cat, n_lines]),
					apply
				);
			} else {
				apply();
			}
		},
	});
	d.fields_dict.preview.$wrapper.html(html);
	d.show();
}

function boq_import_apply(frm, p, overhead) {
	frm.clear_table("items");
	(p.categories || []).forEach((c) => {
		frm.add_child("items", {
			row_type: "Category",
			boq_category: c.match.name,
			description: c.match.category_name,
			control_action: "Stop",
			overhead_percentage: overhead,
			boq_ref: c.boq_ref,
		});
		c.lines.forEach((l) => {
			frm.add_child("items", {
				row_type: "Item",
				boq_category: c.match.name,
				description: l.description,
				uom: l.uom || null,
				qty: l.qty,
				rate: l.rate,
				amount: l.amount,
				remarks: l.remarks || null,
				boq_ref: l.boq_ref,
			});
		});
	});
	boq_renumber(frm);
	frappe.show_alert({
		message: __("Imported {0} categories / {1} lines — review and Save.", [p.summary.categories, p.summary.lines]),
		indicator: "green",
	});
}
