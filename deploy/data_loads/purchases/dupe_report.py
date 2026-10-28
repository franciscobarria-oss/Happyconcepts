import frappe, json
def run():
	for code in ["ING-539", "ING-605", "ING-595", "ING-596", "ING-547", "ING-577"]:
		i = frappe.get_doc("Item", code)
		q = lambda s: frappe.db.sql(s, {"c": code})[0][0]
		print(code, "|", i.item_name, "|", i.stock_uom, "| stock", i.is_stock_item, "| serial", i.has_serial_no, "| batch", i.has_batch_no, "| group", i.item_group)
		print("  desc:", i.description)
		print("  suppliers:", [(s.supplier, s.supplier_part_no) for s in i.supplier_items], "| defaults:", [(d.company, d.default_supplier) for d in i.item_defaults])
		print("  uoms:", [(u.uom, u.conversion_factor) for u in i.uoms])
		print("  prices:", frappe.get_all("Item Price", filters={"item_code": code}, fields=["price_list", "supplier", "price_list_rate", "uom"]))
		c = {}
		for k, s in {"SLE": "select count(*) from `tabStock Ledger Entry` where item_code=%(c)s",
			"Bin": "select count(*) from `tabBin` where item_code=%(c)s",
			"BOM Item": "select count(*) from `tabBOM Item` where item_code=%(c)s",
			"BOM": "select count(*) from `tabBOM` where item=%(c)s",
			"PO Item": "select count(*) from `tabPurchase Order Item` where item_code=%(c)s",
			"PR Item": "select count(*) from `tabPurchase Receipt Item` where item_code=%(c)s",
			"PI Item": "select count(*) from `tabPurchase Invoice Item` where item_code=%(c)s",
			"MR Item": "select count(*) from `tabMaterial Request Item` where item_code=%(c)s",
			"SE Detail": "select count(*) from `tabStock Entry Detail` where item_code=%(c)s",
			"SO Item": "select count(*) from `tabSales Order Item` where item_code=%(c)s"}.items():
			c[k] = q(s)
		# any custom (happy_kitchen) doctypes with an Item link field
		for df in frappe.get_all("DocField", filters={"fieldtype": "Link", "options": "Item"}, fields=["parent", "fieldname"]):
			if frappe.db.get_value("DocType", df.parent, "module") in ("Happy Kitchen",) or df.parent.lower().startswith(("hk ", "recipe")):
				try:
					n = frappe.db.sql(f"select count(*) from `tab{df.parent}` where `{df.fieldname}`=%(c)s", {"c": code})[0][0]
					if n: c[f"{df.parent}.{df.fieldname}"] = n
				except Exception as e:
					pass
		print("  refs:", {k: v for k, v in c.items() if v} or "none")
