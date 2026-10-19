import frappe


def execute():
	"""Turn the Happy Concepts desk theme on (P13). Runs once per site, so a later
	"untick" in Recipe Settings stays. site_config `hk_theme` still overrides it."""
	if frappe.db.exists("DocType", "Recipe Settings"):
		frappe.db.set_single_value("Recipe Settings", "desk_theme", 1)
