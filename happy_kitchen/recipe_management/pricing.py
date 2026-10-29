"""Supplier price lookups for recipe ingredients (ERPNext Item Price)."""

import frappe
from frappe.utils import nowdate

from happy_kitchen.recipe_management.costing import price_per_base_unit


def get_settings():
	return frappe.get_cached_doc("Recipe Settings")


def get_conversion_factor(item_code: str, uom: str | None, stock_uom: str | None) -> float:
	if not uom or uom == stock_uom:
		return 1.0
	cf = frappe.db.get_value("UOM Conversion Detail", {"parent": item_code, "uom": uom}, "conversion_factor")
	if not cf:
		from erpnext.stock.get_item_details import get_conversion_factor as erpnext_cf

		cf = (erpnext_cf(item_code, uom) or {}).get("conversion_factor")
	return float(cf or 1.0)


def get_ingredient_prices(item_code: str, price_list: str | None = None) -> list[dict]:
	"""Every valid buying price for an ingredient, one per supplier price line,
	with the price converted to $ per base unit (gram or piece)."""
	price_list = price_list or get_settings().buying_price_list
	today = nowdate()
	stock_uom = frappe.get_cached_value("Item", item_code, "stock_uom")
	rows = frappe.db.sql(
		"""
		select name, supplier, price_list_rate as rate, uom, currency, valid_from
		from `tabItem Price`
		where item_code = %(item)s and price_list = %(pl)s and buying = 1
			and ifnull(valid_from, '2000-01-01') <= %(today)s
			and ifnull(valid_upto, '2999-12-31') >= %(today)s
		order by price_list_rate asc
		""",
		{"item": item_code, "pl": price_list, "today": today},
		as_dict=True,
	)
	for r in rows:
		r.item_price = r.name
		r.stock_uom = stock_uom
		r.conversion_factor = get_conversion_factor(item_code, r.uom, stock_uom)
		r.price_per_base_unit = price_per_base_unit(r.rate, r.conversion_factor)
	return rows


def get_selling_price(item_code: str, price_list: str | None = None) -> float:
	price_list = price_list or get_settings().selling_price_list
	if not price_list:
		return 0.0
	filters = {"item_code": item_code, "price_list": price_list, "selling": 1}
	stock_uom = frappe.get_cached_value("Item", item_code, "stock_uom")
	rate = frappe.db.get_value("Item Price", dict(filters, uom=stock_uom), "price_list_rate")
	if rate is None:  # no price in the stock unit: fall back to any price
		rate = frappe.db.get_value("Item Price", filters, "price_list_rate")
	return float(rate or 0)


def get_packaging_groups(settings=None) -> set[str]:
	"""Item groups (with all their sub-groups) that count as packaging."""
	settings = settings or get_settings()
	groups: set[str] = set()
	for row in settings.packaging_item_groups:
		lft, rgt = frappe.get_cached_value("Item Group", row.item_group, ["lft", "rgt"])
		groups.update(frappe.get_all("Item Group", filters={"lft": (">=", lft), "rgt": ("<=", rgt)}, pluck="name"))
	return groups


# Recipe types made in-house whose cost per unit feeds the recipes that use them.
SUB_RECIPE_TYPES = ("Batch Preparation", "Recipe Component")


def get_working_recipe(item_code: str):
	"""The active working recipe or recipe component that makes this item, if any."""
	return frappe.db.get_value(
		"Recipe",
		{"item": item_code, "recipe_type": ("in", SUB_RECIPE_TYPES), "status": ("!=", "Archived")},
		["name", "cost_per_unit", "yield_uom", "recipe_type"],
		as_dict=True,
	)
