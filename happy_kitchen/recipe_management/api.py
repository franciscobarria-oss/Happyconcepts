import frappe
from frappe.utils import fmt_money

from happy_kitchen.recipe_management.pricing import get_ingredient_prices


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def supplier_query(doctype, txt, searchfield, start, page_len, filters):
	"""Supplier dropdown on a recipe line: only suppliers that sell this
	ingredient, cheapest first, with their price per base unit."""
	item_code = (filters or {}).get("item_code")
	if not item_code:
		return []
	out = []
	for p in get_ingredient_prices(item_code):
		if not p.supplier or (txt and txt.lower() not in p.supplier.lower()):
			continue
		out.append((p.supplier, f"{fmt_money(p.price_per_base_unit, 4, p.currency)} / {p.stock_uom}"))
	return out[int(start) : int(start) + int(page_len)]


@frappe.whitelist()
def get_supplier_prices(item_code: str) -> list[dict]:
	frappe.has_permission("Recipe", "read", throw=True)
	return get_ingredient_prices(item_code)
