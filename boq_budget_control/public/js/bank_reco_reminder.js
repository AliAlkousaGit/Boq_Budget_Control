// Copyright (c) 2026, BOQ Budget Control and contributors
// License: MIT
//
// Bank Statement Reconciliation reminder.
// Shows ONE popup per login session when an accounting user enters ERPNext Desk.
//
// Wired via `app_include_js` in hooks.py. Fires on Frappe's `startup` event
// (triggered after the Desk boots — frappe/public/js/frappe/desk.js), at which
// point frappe.boot and frappe.user_roles are fully available.

// Roles that should see the reminder. Edit this list to widen / narrow.
const BOQ_REMINDER_ROLES = [
	"Accounts Manager",
	"Accounts User",
	"System Manager",
];

$(document).on("startup", function () {
	if (!frappe.boot || !frappe.boot.user) return;
	if (frappe.session.user === "Guest") return;

	// Only show to users holding one of the reminder roles.
	if (!frappe.user_roles.some((r) => BOQ_REMINDER_ROLES.includes(r))) return;

	// Show exactly once per browser session (clears on logout / tab close).
	// Swap sessionStorage -> localStorage for once-per-browser instead.
	if (sessionStorage.getItem("boq_bank_reco_reminder")) return;
	sessionStorage.setItem("boq_bank_reco_reminder", "1");

	frappe.msgprint({
		title: __("Bank Reconciliation Reminder"),
		indicator: "orange",
		message: __(
			"Reminder: Bank statement reconciliation must be completed within a maximum of 10 days from the bank transaction date."
		),
	});
});
