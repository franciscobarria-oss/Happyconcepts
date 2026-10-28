import frappe
frappe.init(site="hcl-erp.fbs-host.com", sites_path="/home/frappe/frappe-bench/sites"); frappe.connect(); frappe.set_user("Administrator")
CURRENT = ["ING-438","ING-003","ING-005","ING-013","ING-085","ING-320","ING-046","ING-492","ING-147","ING-064","ING-400","ING-072","ING-416"]
if not frappe.db.exists("Custom Field", "Item-is_current"):
	frappe.get_doc({"doctype": "Custom Field", "dt": "Item", "fieldname": "is_current", "label": "Current",
	                "fieldtype": "Check", "insert_after": "item_group", "in_list_view": 1, "in_standard_filter": 1,
	                "description": "Latest purchased version among items with the same name"}).insert(ignore_permissions=True)
frappe.db.commit()
for code in CURRENT:
	name = frappe.db.get_value("Item", code, "item_name")
	new = name if name.endswith("(Current)") else (name + " (Current)")[:140]
	frappe.db.set_value("Item", code, {"is_current": 1, "item_name": new})
frappe.db.commit()
frappe.clear_cache(doctype="Item")
for r in frappe.get_all("Item", {"is_current": 1}, ["name", "item_name"], order_by="item_name"):
	print(r.name, "|", r.item_name)
print("checked:", frappe.db.count("Item", {"is_current": 1}), "of", frappe.db.count("Item"))
frappe.destroy()
