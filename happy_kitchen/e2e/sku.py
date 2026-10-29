"""Supplier SKU and our own SKU: search by either, unique per supplier, shown on the Supplier Products tab
and Receive Delivery lines. Rolled back."""

import frappe

from happy_kitchen.hk_operations import purchasing, sku_api

P = "E2E-SKU-"


def _check(cond, msg):
	if not cond:
		raise AssertionError(msg)


def _item(code, rows):
	return frappe.get_doc({
		"doctype": "Item", "item_code": P + code, "item_name": P + code, "stock_uom": "Gram",
		"item_group": "Ingredients", "is_stock_item": 1, "is_purchase_item": 1, "supplier_items": rows,
	}).insert()


def _found(txt):
	from frappe.desk.search import search_link

	return {r["value"] for r in search_link("Item", txt)}


def run():
	frappe.set_user("Administrator")
	try:
		group = frappe.db.get_value("Supplier Group", {"is_group": 0}, "name")
		a = frappe.get_doc({"doctype": "Supplier", "supplier_name": P + "A", "supplier_group": group}).insert().name
		b = frappe.get_doc({"doctype": "Supplier", "supplier_name": P + "B", "supplier_group": group}).insert().name

		flour = _item("FLOUR", [{"supplier": a, "supplier_part_no": "ZQ-9001"}, {"supplier": b, "supplier_part_no": "KB77"}])
		_check(flour.hk_supplier_skus == "ZQ-9001, KB77", f"search text: {flour.hk_supplier_skus}")

		# found by our SKU (item code) and by either supplier's SKU
		_check(flour.name in _found(P + "FLOUR"), "found by our SKU")
		_check(flour.name in _found("ZQ-9001"), "found by supplier A's SKU")
		_check(flour.name in _found("KB77"), "found by supplier B's SKU")

		# a supplier's SKU belongs to one item; another supplier may reuse the code
		try:
			_item("SUGAR", [{"supplier": a, "supplier_part_no": "ZQ-9001"}])
			raise AssertionError("duplicate SKU for one supplier was allowed")
		except frappe.ValidationError:
			pass
		sugar = _item("SUGAR2", [{"supplier": b, "supplier_part_no": "ZQ-9001"}])
		_check(sugar.hk_supplier_skus == "ZQ-9001", "another supplier may use the same code")

		# the Supplier Products tab and Receive Delivery see the supplier's own SKU
		mine = {i["name"]: i for i in purchasing.get_supplier_products(a)}
		_check(mine[flour.name]["supplier_sku"] == "ZQ-9001", "Supplier Products shows the SKU")
		_check(sku_api.supplier_skus(b, [flour.name, sugar.name]) == {flour.name: "KB77", sugar.name: "ZQ-9001"}, "SKU per supplier")

		# + Add Product takes a supplier SKU
		made = purchasing.add_supplier_product(a, P + "Butter", 0.05, "Gram", "Ingredients", supplier_sku="BU-1")
		_check(made["created"], "new product created")
		_check(sku_api.supplier_skus(a, [made["item_code"]]) == {made["item_code"]: "BU-1"}, "SKU saved by + Add Product")
		_check(made["item_code"] in _found("BU-1"), "new product found by its supplier SKU")
		print("ok: sku e2e passed")
	finally:
		frappe.db.rollback()
		frappe.clear_cache()
