import frappe


def execute():
	"""The role must exist before the Kitchen Checks doctypes (which grant it permissions) are synced."""
	if not frappe.db.exists("Role", "Compliance Manager"):
		frappe.get_doc({"doctype": "Role", "role_name": "Compliance Manager", "desk_access": 1}).insert(ignore_permissions=True)
