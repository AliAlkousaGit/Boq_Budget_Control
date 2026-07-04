// BOQ Budget vs Actual — filters
frappe.query_reports["BOQ Budget vs Actual"] = {
	filters: [
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
			fieldname: "budget",
			label: __("BOQ Project Budget"),
			fieldtype: "Link",
			options: "BOQ Project Budget",
			width: "80",
			get_query: function () {
				return {
					filters: { docstatus: 1 },
				};
			},
		},
	],
};
