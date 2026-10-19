"""P11: Receive Delivery against a PO, then wastage out of stock. Rolled back."""

import frappe
from frappe.utils import add_days, flt, nowdate

from happy_kitchen.recipe_management import kitchen

P = "E2E-P11-"


def _check(cond, msg):
	if not cond:
		raise AssertionError(msg)


def run():
	frappe.set_user("Administrator")
	company = frappe.defaults.get_global_default("company")
	abbr = frappe.db.get_value("Company", company, "abbr")
	fridge = f"Fridge - {abbr}"
	try:
		_check(len(kitchen.wastage_reasons()) >= 8, "8 starting wastage reasons")
		supplier = frappe.get_doc({"doctype": "Supplier", "supplier_name": P + "SUPPLIER",
		                           "supplier_group": frappe.db.get_value("Supplier Group", {"is_group": 0}, "name")}).insert().name
		egg = frappe.get_doc({
			"doctype": "Item", "item_code": P + "EGG", "item_name": P + "EGG", "stock_uom": "Nos",
			"item_group": "Ingredients", "is_stock_item": 1, "is_purchase_item": 1,
			"item_defaults": [{"company": company, "default_warehouse": fridge}],
		}).insert().name
		butter = frappe.get_doc({
			"doctype": "Item", "item_code": P + "BUTTER", "item_name": P + "BUTTER", "stock_uom": "Gram",
			"item_group": "Ingredients", "is_stock_item": 1, "is_purchase_item": 1,
			"item_defaults": [{"company": company, "default_warehouse": fridge}],
		}).insert().name

		po = frappe.get_doc({
			"doctype": "Purchase Order", "supplier": supplier, "company": company,
			"schedule_date": add_days(nowdate(), 1), "set_warehouse": fridge,
			"items": [{"item_code": egg, "qty": 60, "rate": 1.5}, {"item_code": butter, "qty": 2000, "rate": 0.1}],
		}).insert()
		po.submit()
		_check(po.name in {p.name for p in kitchen.open_purchase_orders(supplier)}, "PO listed as open")

		lines = kitchen.purchase_order_lines(po.name)["lines"]
		by_item = {l["item"]: l for l in lines}
		res = kitchen.receive_po(po.name, [
			{"po_detail": by_item[egg]["po_detail"], "received_qty": 50, "invoice_rate": 1.5},  # 10 short
			{"po_detail": by_item[butter]["po_detail"], "received_qty": 2000, "invoice_rate": 0.12},  # +20 %
		], supplier_delivery_note="DN-1")
		pr = frappe.get_doc("Purchase Receipt", res["name"])
		_check(pr.docstatus == 1 and pr.hk_has_discrepancy == 1, "receipt submitted and flagged")
		_check("short 10" in pr.hk_delivery_flags and "price +20.0%" in pr.hk_delivery_flags, pr.hk_delivery_flags)
		rates = {i.item_code: (flt(i.rate), flt(i.hk_invoice_rate)) for i in pr.items}
		_check(rates[butter] == (0.1, 0.12), f"stock at PO price, invoice price kept: {rates}")
		_check(flt(frappe.db.get_value("Bin", {"item_code": egg, "warehouse": fridge}, "actual_qty")) == 50, "50 eggs in")

		# wastage: a whole-number item rounds up and leaves stock; too much still records, with a note
		w = kitchen.log_wastage([{"item": egg, "qty": 2, "uom": "piece", "reason": "Dropped / Damaged"}])
		_check(w["stock_entry"] and not w["stock_note"], f"wastage issued: {w}")
		_check(flt(frappe.db.get_value("Bin", {"item_code": egg, "warehouse": fridge}, "actual_qty")) == 48, "48 eggs left")
		_check(abs(flt(w["total_cost"]) - 3.0) < 1e-6, f"2 eggs at 1.5 = 3.0, got {w['total_cost']}")
		w2 = kitchen.log_wastage([{"item": butter, "qty": 5, "uom": "kg", "reason": "Spoiled / Expired"}])
		_check(not w2["stock_entry"] and w2["stock_note"], f"short stock is noted, not blocking: {w2}")
		_check(frappe.db.get_value("Wastage Log", w2["name"], "docstatus") == 1, "still submitted")
		print("ok: wastage and receiving e2e passed")
	finally:
		frappe.db.rollback()
		frappe.clear_cache()
