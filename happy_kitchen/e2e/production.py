"""P9: Production log, batch preparations to stock and the Material Issue. Rolled back."""

import frappe
from frappe.utils import flt, nowdate

from happy_kitchen.recipe_management import kitchen
from happy_kitchen.recipe_management.doctype.recipe_production_log import recipe_production_log as rpl

P = "E2E-P9-"


def _wh(name, abbr):
	return f"{name} - {abbr}"


def _item(code, uom, group, warehouse, company):
	frappe.get_doc({
		"doctype": "Item", "item_code": P + code, "item_name": P + code, "stock_uom": uom,
		"item_group": group, "is_stock_item": 1, "valuation_rate": 0,
		"item_defaults": [{"company": company, "default_warehouse": warehouse}],
	}).insert()
	return P + code


def _recipe(item, rtype, batch_yield, yield_uom, lines, status="Active"):
	return frappe.get_doc({
		"doctype": "Recipe", "item": item, "recipe_name": item, "recipe_type": rtype, "status": status,
		"batch_yield": batch_yield, "yield_uom": yield_uom,
		"ingredients": [{"item": i, "qty": q, "uom": u} for i, q, u in lines],
	}).insert().name


def _check(cond, msg):
	if not cond:
		raise AssertionError(msg)


def run():
	frappe.set_user("Administrator")
	company = frappe.defaults.get_global_default("company")
	abbr = frappe.db.get_value("Company", company, "abbr")
	price_list = frappe.db.get_single_value("Recipe Settings", "buying_price_list") or "Standard Buying"
	try:
		frappe.db.set_single_value("Recipe Settings", "create_stock_entry_on_submit", 1)
		frappe.clear_document_cache("Recipe Settings", "Recipe Settings")

		flour = _item("FLOUR", "Gram", "Ingredients", _wh("Dry Stock", abbr), company)
		egg = _item("EGG", "Nos", "Ingredients", _wh("Fridge", abbr), company)
		dough = _item("DOUGH", "Gram", "Doughs", _wh("Freezer", abbr), company)
		cookie = _item("COOKIE", "Nos", "Products", _wh("Finished Goods", abbr), company)
		for item, rate in ((flour, 0.02), (egg, 1.5)):
			frappe.get_doc({"doctype": "Item Price", "item_code": item, "price_list": price_list,
			                "price_list_rate": rate}).insert()

		receipt = frappe.get_doc({
			"doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "purpose": "Material Receipt",
			"company": company,
			"items": [
				{"item_code": flour, "qty": 5000, "basic_rate": 0.02, "t_warehouse": _wh("Dry Stock", abbr)},
				{"item_code": egg, "qty": 30, "basic_rate": 1.5, "t_warehouse": _wh("Fridge", abbr)},
			],
		}).insert()
		receipt.submit()

		dough_r = _recipe(dough, "Batch Preparation", 1000, "Gram", [(flour, 600, "g"), (egg, 1.025, "piece")])
		cookie_r = _recipe(cookie, "Finished Product", 10, "Nos", [(dough, 500, "g"), (egg, 1, "piece")])
		old_r = _recipe(_item("OLD", "Nos", "Products", _wh("Finished Goods", abbr), company),
		                "Finished Product", 1, "Nos", [(egg, 1, "piece")], status="Archived")

		tiles = {r["name"] for r in kitchen.production_recipes()}
		_check({dough_r, cookie_r} <= tiles and old_r not in tiles, "tiles should list only Active recipes")

		pv = kitchen.production_preview([{"recipe": dough_r, "batches": 1}, {"recipe": cookie_r, "batches": 2}])
		need = {l["item"]: l for l in pv["lines"]}
		_check(abs(need[egg]["needed"] - 3.025) < 1e-6, f"egg need {need[egg]}")
		_check(need[dough]["short"] == 1000, f"no dough in stock yet, so all 1000 g short: {need[dough]}")

		try:
			kitchen.log_production([{"recipe": old_r, "batches": 1}])
			raise AssertionError("an Archived recipe must not be logged")
		except frappe.ValidationError:
			pass

		res = kitchen.log_production([{"recipe": dough_r, "batches": 1}, {"recipe": cookie_r, "batches": 2}])
		log = frappe.get_doc("Recipe Production Log", res["name"])
		_check(log.docstatus == 1, "log submitted")
		_check([flt(r.units) for r in log.items] == [1000, 20], f"units {[r.units for r in log.items]}")

		# one Manufacture entry for the dough: ingredients out of their own warehouses, dough into the Freezer
		names = log.batch_stock_entries.split()
		_check(len(names) == 1, f"batch entries {names}")
		mfg = frappe.get_doc("Stock Entry", names[0])
		rows = {d.item_code: d for d in mfg.items}
		_check(rows[flour].qty == 600 and rows[flour].s_warehouse == _wh("Dry Stock", abbr), "flour from Dry Stock")
		_check(rows[egg].qty == 2 and rows[egg].s_warehouse == _wh("Fridge", abbr), "1.025 eggs round up to 2, from Fridge")
		_check(rows[dough].qty == 1000 and rows[dough].t_warehouse == _wh("Freezer", abbr), "dough into Freezer")
		mfg.submit()
		rate = frappe.db.get_value("Bin", {"item_code": dough, "warehouse": _wh("Freezer", abbr)}, "valuation_rate")
		_check(abs(flt(rate) - (600 * 0.02 + 2 * 1.5) / 1000) < 1e-6, f"dough valued at ingredient cost, got {rate}")

		# the cookie run goes on one Material Issue (the dough comes out of the Freezer)
		issue = frappe.get_doc("Stock Entry", log.stock_entry)
		_check(issue.purpose == "Material Issue" and issue.docstatus == 0, "draft Material Issue")
		rows = {d.item_code: d for d in issue.items}
		_check(set(rows) == {dough, egg}, f"issue items {set(rows)}")
		_check(rows[dough].qty == 1000 and rows[dough].s_warehouse == _wh("Freezer", abbr), "dough from Freezer")
		_check(rows[egg].qty == 2, "2 eggs for 2 cookie batches")
		issue.submit()

		# buttons are idempotent
		_check(rpl.make_stock_entry(log.name) == issue.name, "Material Issue not duplicated")
		_check(rpl.make_batch_preparation_entries(log.name) == names, "Manufacture not duplicated")
		print("ok: production e2e passed", nowdate())
	finally:
		frappe.db.rollback()
		frappe.clear_document_cache("Recipe Settings", "Recipe Settings")
		frappe.clear_cache()
