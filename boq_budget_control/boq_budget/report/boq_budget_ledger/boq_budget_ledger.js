// BOQ Budget Ledger — filters
frappe.query_reports["BOQ Budget Ledger"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			width: "80",
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			width: "80",
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			width: "80",
		},
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
			width: "80",
		},
		{
			fieldname: "boq_category",
			label: __("BOQ Category"),
			fieldtype: "Link",
			options: "BOQ Budget Category",
			width: "80",
		},
		{
			fieldname: "voucher_type",
			label: __("Voucher Type"),
			fieldtype: "Select",
			options: "\nPurchase Order\nPurchase Invoice",
			width: "80",
		},
		{
			fieldname: "entry_type",
			label: __("Entry Type"),
			fieldtype: "Select",
			options: "\nReserve\nRelease\nActual",
			width: "80",
		},
	],
};
