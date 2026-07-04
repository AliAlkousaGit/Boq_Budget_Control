// Copyright (c) 2026, BOQ Budget Control and contributors
// License: MIT
//
// Bank Statement Reconciliation reminder.
// Shows a one-time popup each login session when the user enters ERPNext Desk.
//
// Behaviour:
//   * Fires on Frappe's `startup` event (triggered after the Desk boots — see
//     frappe/public/js/frappe/desk.js). `frappe.boot` / `frappe.user_roles`
//     are fully available at that point.
//   * Shows ONCE per browser session via sessionStorage — so it appears on the
//     first Desk entry after login and not again until the user logs out /
//     closes the tab. Swap sessionStorage -> localStorage for once-per-day.
//   * By default shown to every Desk user. Uncomment the role filter below to
//     restrict it to accounting users only.
//
// Wired via `app_include_js` in hooks.py.

$(document).on("startup", function () {
	if (!frappe.boot || !frappe.boot.user) return;
	if (frappe.session.user === "Guest") return;

	// --- optional: restrict to accounting users ---
	// const acct_roles = ["Accounts Manager", "Accounts User", "System Manager"];
	// if (!frappe.user_roles.some((r) => acct_roles.includes(r))) return;

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
