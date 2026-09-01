app_name = "boq_budget_control"
app_title = "Boq Budget Control"
app_publisher = "Golden Link"
app_description = "Project budget control at the BOQ category level"
app_email = "admin@golden-link.com"
app_license = "mit"

# Apps
# ------------------

required_apps = ["erpnext"]

# Includes in <head>
# ------------------

# Bank reconciliation reminder popup shown once per session on Desk entry
app_include_js = "boq_budget_control/public/js/bank_reco_reminder.js"

# include js in doctype views
doctype_js = {
	"Purchase Order": "boq_budget_control/public/js/purchase_order.js",
	"Purchase Invoice": "boq_budget_control/public/js/purchase_invoice.js",
	"BOQ Project Budget": "boq_budget_control/public/js/boq_project_budget.js",
}

# Installation
# ------------
after_install = [
	"boq_budget_control.boq_budget.setup.make_custom_fields",
	"boq_budget_control.boq_budget.setup.make_roles",
	"boq_budget_control.boq_budget.setup.make_categories",
	"boq_budget_control.boq_budget.setup.make_workspace",
	"boq_budget_control.boq_budget.setup.make_accounts_workspace",
]
after_migrate = [
	"boq_budget_control.boq_budget.setup.make_custom_fields",
	"boq_budget_control.boq_budget.setup.make_roles",
	"boq_budget_control.boq_budget.setup.make_categories",
	"boq_budget_control.boq_budget.setup.make_workspace",
	"boq_budget_control.boq_budget.setup.make_accounts_workspace",
]

# Document Events
# ---------------
doc_events = {
	"Purchase Order": {
		"before_submit": "boq_budget_control.boq_budget.purchase_order_events.before_submit",
		"on_submit": "boq_budget_control.boq_budget.purchase_order_events.on_submit",
		"on_cancel": "boq_budget_control.boq_budget.purchase_order_events.on_cancel",
	},
	"Purchase Invoice": {
		"before_submit": "boq_budget_control.boq_budget.purchase_invoice_events.before_submit",
		"on_submit": "boq_budget_control.boq_budget.purchase_invoice_events.on_submit",
		"on_cancel": "boq_budget_control.boq_budget.purchase_invoice_events.on_cancel",
	},
}
