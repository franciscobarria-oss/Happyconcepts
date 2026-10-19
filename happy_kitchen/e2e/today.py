"""P14: Today home data, the A4 production sheet and the HK Delivery Note print. Rolled back."""

import frappe
from frappe.utils import add_days, flt, nowdate

from happy_kitchen.recipe_management import production_sheet, today, today_board

P = "E2E-P14-"


def _wh(name, abbr):
	return f"{name} - {abbr}"


def _leaf(doctype):
	return frappe.db.get_value(doctype, {"is_group": 0}, "name")


def _item(code, uom, group, warehouse, company, supplier=None, sales=0):
	frappe.get_doc({
		"doctype": "Item", "item_code": P + code, "item_name": P + code, "stock_uom": uom,
		"item_group": group, "is_stock_item": 1, "is_sales_item": sales, "valuation_rate": 0,
		"item_defaults": [{"company": company, "default_warehouse": warehouse, "default_supplier": supplier}],
	}).insert()
	return P + code


def _recipe(item, rtype, batch_yield, yield_uom, lines):
	return frappe.get_doc({
		"doctype": "Recipe", "item": item, "recipe_name": item, "recipe_type": rtype, "status": "Active",
		"batch_yield": batch_yield, "yield_uom": yield_uom,
		"ingredients": [{"item": i, "qty": q, "uom": u} for i, q, u in lines],
	}).insert().name


def _check(cond, msg):
	if not cond:
		raise AssertionError(msg)


def _ordering_lines(data, item):
	return [l for g in (data["tasks"]["ordering"] or {}).get("groups", []) for l in g["lines"] if l["item"] == item]


def run():
	frappe.set_user("Administrator")
	company = frappe.defaults.get_global_default("company")
	abbr = frappe.db.get_value("Company", company, "abbr")
	day = nowdate()
	try:
		supplier = frappe.get_doc({"doctype": "Supplier", "supplier_name": P + "Mill",
		                           "supplier_group": _leaf("Supplier Group")}).insert().name
		customer = frappe.get_doc({"doctype": "Customer", "customer_name": P + "Cafe", "customer_type": "Company",
		                           "customer_group": _leaf("Customer Group"), "territory": _leaf("Territory")}).insert().name

		flour = _item("FLOUR", "Gram", "Ingredients", _wh("Dry Stock", abbr), company, supplier)
		egg = _item("EGG", "Nos", "Ingredients", _wh("Fridge", abbr), company)
		dough = _item("DOUGH", "Gram", "Doughs", _wh("Freezer", abbr), company)
		cookie = _item("COOKIE", "Nos", "Products", _wh("Finished Goods", abbr), company, sales=1)
		_recipe(dough, "Batch Preparation", 1000, "Gram", [(flour, 600, "g"), (egg, 1, "piece")])
		cookie_r = _recipe(cookie, "Finished Product", 10, "Nos", [(dough, 500, "g"), (egg, 1, "piece")])

		so = frappe.get_doc({
			"doctype": "Sales Order", "customer": customer, "company": company,
			"transaction_date": day, "delivery_date": day,
			"items": [{"item_code": cookie, "qty": 25, "rate": 10, "delivery_date": day,
			           "warehouse": _wh("Finished Goods", abbr)}],
		}).insert()
		so.submit()

		# --- Today home: one call, dashboard and board merged ---
		data = today.today()
		tiles = {t["key"]: t for t in data["tiles"]}
		_check({"orders", "production", "deliveries", "open_po", "waste"} <= set(tiles), f"tiles {list(tiles)}")
		_check(any(d["label"] == P + "Cafe" for d in tiles["orders"]["details"]), "orders tile breakdown by customer")
		_check(any(o["name"] == so.name for o in data["now"]["orders"]), "the order is going out today")
		prod = {p["recipe"]: p for p in data["now"]["production"]}
		_check(prod.get(cookie_r, {}).get("batches") == 3, f"25 cookies = 3 batches of 10: {prod.get(cookie_r)}")
		todays = next(g for g in data["orders"] if g["key"] == "today")
		_check(any(o["name"] == so.name for o in todays["orders"]), "orders by day lists it under Today")
		# 3 cookie batches need 1500 g dough -> 2 dough batches -> 1200 g flour, none in stock
		lines = _ordering_lines(data, flour)
		_check(len(lines) == 1 and abs(lines[0]["qty"] - 1200) < 1e-6, f"order 1200 g flour: {lines}")
		_check(not any(t["route"] == "List/Purchase Order?docstatus=0" for t in data["waiting"]), "no draft POs yet")

		# "Create draft order" covers the shortage, so the next refresh drops it
		group = next(g for g in data["tasks"]["ordering"]["groups"] if g["supplier"] == supplier)
		po = today_board.create_purchase_order(supplier, [{"item": l["item"], "qty": l["qty"]} for l in group["lines"]],
		                                       group["need_by"])
		_check(frappe.db.get_value("Purchase Order", po, "docstatus") == 0, "draft purchase order")
		data = today.today()
		_check(not _ordering_lines(data, flour), "flour already on order")
		_check(any(t["route"] == "List/Purchase Order?docstatus=0" for t in data["waiting"]), "draft PO waits on you")
		_check(data["tasks"]["ordering"]["drafts"] == 0, "draft POs shown once, under Waiting on you")

		# --- A4 production sheet ---
		html = production_sheet.sheet(date=day).get_data(as_text=True)
		_check(cookie in html and (P + "Cafe") in html, "sheet lists the order")
		_check(flour in html, "sheet lists the short flour")
		empty = production_sheet.build(str(add_days(day, 30)))
		_check(not [m for m in empty["make"] if m["item"].startswith(P)], "nothing to make on a day without orders")

		# --- HK Delivery Note print (bilingual) ---
		from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note

		dn = make_delivery_note(so.name)
		dn.insert()
		_check(flt(dn.items[0].qty) == 25, "delivery note for the 25 cookies")
		page = frappe.get_print("Delivery Note", dn.name, print_format="HK Delivery Note", doc=dn, no_letterhead=1)
		_check("送貨單" in page and "Delivery Note" in page and cookie in page, "HK Delivery Note renders")
		print("ok: today e2e passed")
	finally:
		frappe.db.rollback()
		frappe.clear_cache()
