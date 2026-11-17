"""Fills Item.hk_list_supplier / hk_list_price (columns of the Item list) from Item Price."""

import frappe

from happy_kitchen.hk_operations import list_price


def values_for(item_code, default_suppliers=None):
	if default_suppliers is None:
		default_suppliers = frappe.get_all(
			"Item Supplier", filters={"parent": item_code, "parenttype": "Item"},
			order_by="idx", pluck="supplier")
	today = frappe.utils.nowdate()
	prices = frappe.db.sql(
		"""select supplier, price_list_rate as rate, uom, currency, valid_from, modified
		from `tabItem Price` where item_code = %s and buying = 1
		and ifnull(valid_from, '2000-01-01') <= %s and ifnull(valid_upto, '2999-12-31') >= %s""",
		(item_code, today, today), as_dict=True)
	best = list_price.pick(prices, default_suppliers)
	supplier = (best or {}).get("supplier") or (default_suppliers[0] if default_suppliers else "")
	return {"hk_list_supplier": supplier, "hk_list_price": list_price.price_text(best)}


def item_validate(doc, method=None):
	if not doc.is_new():
		suppliers = [r.supplier for r in doc.get("supplier_items") or [] if r.supplier]
		doc.update(values_for(doc.name, suppliers))


def item_price_changed(doc, method=None):
	if doc.item_code and frappe.db.exists("Item", doc.item_code):
		for k, v in values_for(doc.item_code).items():
			frappe.db.set_value("Item", doc.item_code, k, v, update_modified=False)
