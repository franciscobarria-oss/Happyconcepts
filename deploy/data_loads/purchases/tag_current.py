import frappe
from frappe.desk.doctype.tag.tag import add_tag
frappe.init(site="hcl-erp.fbs-host.com", sites_path="/home/frappe/frappe-bench/sites"); frappe.connect(); frappe.set_user("Administrator")
CURRENT = ["ING-438","ING-003","ING-005","ING-013","ING-085","ING-320","ING-046","ING-492","ING-147","ING-064","ING-400","ING-072","ING-416"]
for code in CURRENT:
	tags = (frappe.db.get_value("Item", code, "_user_tags") or "").split(",")
	if "Current" not in tags:
		add_tag("Current", "Item", code)
frappe.db.commit()
for r in frappe.get_all("Item", {"_user_tags": ["like", "%Current%"]}, ["name", "item_name", "_user_tags"], order_by="item_name"):
	print(r.name, "|", r.item_name, "|", r._user_tags)
frappe.destroy()
