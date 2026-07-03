frappe.ui.form.on("Purchase Invoice", {
	refresh(frm) {
		frm.set_query("boq_category", "items", (doc, cdt, cdn) => {
			const row = locals[cdt][cdn];
			return { filters: { parent: row.boq_project_budget, parenttype: "BOQ Project Budget" } };
		});
	},
});

frappe.ui.form.on("Purchase Invoice Item", {
	project(frm, cdt, cdn) { fetch_pi_budget(frm, cdt, cdn); },
	boq_project_budget(frm, cdt, cdn) { refresh_pi_available(frm, cdt, cdn); },
	boq_category(frm, cdt, cdn) { refresh_pi_available(frm, cdt, cdn); },
	po_detail(frm, cdt, cdn) { copy_po_boq(frm, cdt, cdn); },
});

async function fetch_pi_budget(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row.project) return;
	const budgets = await frappe.xcall(
		"boq_budget_control.boq_budget.api.get_budget_for_project",
		{ project: row.project, company: frm.doc.company },
	);
	if (budgets.length === 1) {
		frappe.model.set_value(cdt, cdn, "boq_project_budget", budgets[0].name);
	}
}

async function copy_po_boq(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row.po_detail) return;
	const po_item = await frappe.db.get_value(
		"Purchase Order Item", row.po_detail, ["boq_project_budget", "boq_category"],
	);
	if (po_item && po_item.message) {
		frappe.model.set_value(cdt, cdn, "boq_project_budget", po_item.message.boq_project_budget);
		frappe.model.set_value(cdt, cdn, "boq_category", po_item.message.boq_category);
	}
}

async function refresh_pi_available(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!(row.boq_project_budget && row.boq_category)) return;
	const r = await frappe.xcall(
		"boq_budget_control.boq_budget.api.get_category_available",
		{ budget: row.boq_project_budget, category: row.boq_category },
	);
	frappe.model.set_value(cdt, cdn, "budget_available", r.available);
	frappe.model.set_value(cdt, cdn, "budget_status", r.status);
}
