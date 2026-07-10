// Copyright (c) 2026, BOQ Budget Control and contributors
// Live calculation of Budget Amount + Net Budget % from Total and Overhead %
// on each BOQ Project Budget Category row. The server-side validate()
// re-computes the same values (source of truth); this script mirrors it so the
// user sees the result instantly while editing.
frappe.ui.form.on("BOQ Project Budget Category", {
	total: function (frm, cdt, cdn) {
		boq_calc_row(frm, cdt, cdn);
	},
	overhead_percentage: function (frm, cdt, cdn) {
		boq_calc_row(frm, cdt, cdn);
	},
	categories_remove: function (frm) {
		boq_recalc_parent_total(frm);
	},
});

function boq_calc_row(frm, cdt, cdn) {
	var row = locals[cdt][cdn];
	var total = flt(row.total);
	var overhead = flt(row.overhead_percentage);

	if (overhead < 0 || overhead > 100) {
		frappe.msgprint(__("Overhead % must be between 0 and 100."));
	}

	if (total > 0) {
		frappe.model.set_value(cdt, cdn, "budget_amount", flt(total * (1 - overhead / 100)));
		frappe.model.set_value(cdt, cdn, "net_budget_percent", flt(100 - overhead));
	} else {
		// No Total: Budget Amount stays as entered; Net % is not meaningful.
		frappe.model.set_value(cdt, cdn, "net_budget_percent", 0);
	}
	boq_recalc_parent_total(frm);
}

function boq_recalc_parent_total(frm) {
	var total = 0;
	(frm.doc.categories || []).forEach(function (row) {
		total += flt(row.budget_amount);
	});
	frm.set_value("total_budget_amount", flt(total));
}
