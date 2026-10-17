import frappe


def execute():
	"""Settings defaults for the new Recipe Settings fields, and a starter count
	sheet with every stocked ingredient grouped by storage area."""
	for field, value in (("variance_tolerance_pct", 2), ("stock_take_sync_stock", 1)):
		if not frappe.db.exists("Singles", {"doctype": "Recipe Settings", "field": field}):
			frappe.db.set_single_value("Recipe Settings", field, value)

	from happy_kitchen.recipe_management.doctype.stock_take_sheet.stock_take_sheet import stocked_ingredients

	company = frappe.defaults.get_global_default("company") or frappe.db.get_value("Company", {}, "name")
	if company and not frappe.db.exists("Stock Take Sheet", "Main Kitchen"):
		rows = [r for r in stocked_ingredients(company) if r["storage_area"]]
		if rows:
			frappe.get_doc({"doctype": "Stock Take Sheet", "sheet_name": "Main Kitchen", "company": company, "items": rows}).insert(
				ignore_permissions=True
			)
