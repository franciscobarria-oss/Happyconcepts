"""Supplier SKU hooks and lookups. Rules in sku.py."""

import frappe
from frappe import _

from happy_kitchen.hk_operations import sku


def item_validate(doc, method=None):
	"""Keep Item.hk_supplier_skus in step with the Supplier Items table (it feeds the Item
	search) and keep a supplier's SKU unique: one SKU is one item for that supplier."""
	rows = [{"supplier": r.supplier, "supplier_part_no": r.supplier_part_no} for r in doc.get("supplier_items") or []]
	again = sku.repeated_in_item(rows)
	if again:
		frappe.throw(_("{0} is listed twice with the SKU {1}.").format(again[0], again[1]))
	for r in rows:
		code = sku.clean(r["supplier_part_no"])
		if not code:
			continue
		other = frappe.db.sql(
			"select parent from `tabItem Supplier` where parenttype = 'Item' and supplier = %s "
			"and supplier_part_no = %s and parent != %s limit 1",
			(r["supplier"], code, doc.name or ""),
		)
		if other:
			frappe.throw(_("{0}'s SKU {1} is already used by item {2}.").format(r["supplier"], code, other[0][0]))
	customer_rows = [{"supplier": "", "supplier_part_no": r.ref_code} for r in doc.get("customer_items") or []]
	doc.hk_supplier_skus = sku.search_text(rows + customer_rows)


def supplier_skus(supplier: str, items) -> dict:
	"""{item_code: supplier SKU} for the items that have one with this supplier."""
	items = [i for i in items if i]
	if not items:
		return {}
	out = {}
	for r in frappe.get_all(
		"Item Supplier",
		filters={"parenttype": "Item", "supplier": supplier, "parent": ("in", items)},
		fields=["parent", "supplier_part_no"],
	):
		if sku.clean(r.supplier_part_no):
			out[r.parent] = sku.clean(r.supplier_part_no)
	return out
