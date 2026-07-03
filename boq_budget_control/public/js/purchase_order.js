frappe.ui.form.on("Purchase Order", {
	setup(frm) { setup_boq_category_query(frm); },
	refresh(frm) { setup_boq_category_query(frm); },
});

frappe.ui.form.on("Purchase Order Item", {
	project(frm, cdt, cdn) { fetch_budget_for_row(frm, cdt, cdn); },
	boq_project_budget(frm, cdt, cdn) { refresh_row_available(frm, cdt, cdn); },
	boq_category(frm, cdt, cdn) { refresh_row_available(frm, cdt, cdn); },
});

async function fetch_budget_for_row(frm, cdt, cdn) {
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

function setup_boq_category_query(frm) {
	frm.set_query("boq_category", "items", (doc, cdt, cdn) => {
		const row = locals[cdt][cdn];
		return {
			query: "boq_budget_control.boq_budget.api.boq_category_query",
			filters: { budget: row.boq_project_budget },
		};
	});
}

async function refresh_row_available(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!(row.boq_project_budget && row.boq_category)) return;
	const r = await frappe.xcall(
		"boq_budget_control.boq_budget.api.get_category_available",
		{ budget: row.boq_project_budget, category: row.boq_category },
	);
	frappe.model.set_value(cdt, cdn, "budget_available", r.available);
	frappe.model.set_value(cdt, cdn, "budget_status", r.status);
}
