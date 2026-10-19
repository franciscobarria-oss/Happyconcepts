import frappe


def execute():
	"""The role must exist before the Stock Take doctype (which grants it permissions) is synced."""
	if not frappe.db.exists("Role", "Stock Take Approver"):
		frappe.get_doc({"doctype": "Role", "role_name": "Stock Take Approver", "desk_access": 1}).insert(ignore_permissions=True)
