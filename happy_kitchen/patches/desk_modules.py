import frappe

MODULES = ["HK Suppliers", "HK Sales", "HK Clock In", "HK Accounting", "HK Costing", "HK Reports",
           "HK Today", "HK Stock Take"]


def execute():
	"""Each desk icon needs its own Module Def: the desk finds an icon's sidebar by the module of its
	workspace, so icons that share a module all open the same screen (Sales opened Team). Idempotent."""
	for name in MODULES:
		if not frappe.db.exists("Module Def", name):
			frappe.get_doc({"doctype": "Module Def", "module_name": name, "app_name": "happy_kitchen"}).insert(
				ignore_permissions=True)
