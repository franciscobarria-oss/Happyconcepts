import frappe


def execute():
	"""Francisco, 2026-11-17: for the time being, legible email orders are assumed delivered on their
	date. Turned on once; a manager can untick it in Recipe Settings."""
	frappe.reload_doc("recipe_management", "doctype", "recipe_settings")
	frappe.db.set_single_value("Recipe Settings", "auto_complete_email_orders", 1)
