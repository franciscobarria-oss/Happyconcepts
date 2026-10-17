# Copyright (c) 2026, Happy Kitchen and contributors
# For license information, please see license.txt

"""Every ingredient and packaging item with every supplier price, the
cheapest supplier, and the recipes that use it."""

import frappe
from frappe import _
from frappe.utils import flt

from happy_kitchen.recipe_management.pricing import get_ingredient_prices, get_packaging_groups, get_settings


def execute(filters=None):
	filters = frappe._dict(filters or {})
	settings = get_settings()
	price_list = filters.price_list or settings.buying_price_list
	packaging_groups = get_packaging_groups(settings)

	price_filters = {"price_list": price_list, "buying": 1}
	if filters.item:
		price_filters["item_code"] = filters.item
	if filters.supplier:
		price_filters["supplier"] = filters.supplier
	items = set(frappe.get_all("Item Price", filters=price_filters, pluck="item_code"))

	usage = recipes_by_item()
	if filters.recipe:
		recipe_items = set(
			frappe.get_all("Recipe Ingredient", filters={"parenttype": "Recipe", "parent": filters.recipe}, pluck="item")
		)
		items &= recipe_items
		if filters.show_unpriced and not filters.supplier:
			items |= recipe_items
	elif filters.show_unpriced and not filters.supplier and not filters.item:
		items |= set(usage)

	data = []
	for item in sorted(items):
		item_name, stock_uom, item_group = frappe.get_cached_value("Item", item, ["item_name", "stock_uom", "item_group"])
		component_type = "Packaging" if item_group in packaging_groups else "Ingredient"
		if filters.component_type and filters.component_type != component_type:
			continue
		prices = get_ingredient_prices(item, price_list)
		priced = [p for p in prices if flt(p.price_per_base_unit) > 0]
		cheapest = min(priced, key=lambda p: p.price_per_base_unit) if priced else None
		recipes = usage.get(item, [])
		common = {
			"item": item,
			"item_name": item_name,
			"component_type": component_type,
			"item_group": item_group,
			"stock_uom": stock_uom,
			"recipe_count": len(recipes),
			"recipes": ", ".join(recipes),
		}
		if not prices:
			data.append({**common, "no_price": 1})
			continue
		for p in prices:
			if filters.supplier and p.supplier != filters.supplier:
				continue
			diff = (
				(flt(p.price_per_base_unit) - cheapest.price_per_base_unit) / cheapest.price_per_base_unit * 100
				if cheapest
				else 0
			)
			data.append(
				{
					**common,
					"supplier": p.supplier,
					"rate": p.rate,
					"price_uom": p.uom,
					"price_per_base_unit": p.price_per_base_unit,
					"price_per_kg": p.price_per_base_unit * 1000 if stock_uom == "Gram" else None,
					"is_cheapest": 1 if cheapest and p.name == cheapest.name else 0,
					"cheapest_supplier": cheapest.supplier if cheapest else None,
					"diff_pct": diff,
					"no_price": 0 if flt(p.price_per_base_unit) else 1,
					"item_price": p.name,
					"valid_from": p.valid_from,
				}
			)
	data.sort(key=lambda r: (r.get("supplier") or "~", r["component_type"], r["item_name"] or ""))
	return get_columns(), data


def recipes_by_item():
	out = {}
	for r in frappe.get_all(
		"Recipe Ingredient", filters={"parenttype": "Recipe"}, fields=["item", "parent"], order_by="parent", distinct=True
	):
		out.setdefault(r.item, []).append(r.parent)
	return out


def get_columns():
	return [
		{"fieldname": "supplier", "label": _("Supplier"), "fieldtype": "Link", "options": "Supplier", "width": 170},
		{"fieldname": "component_type", "label": _("Type"), "fieldtype": "Data", "width": 90},
		{"fieldname": "item", "label": _("Item ID"), "fieldtype": "Link", "options": "Item", "width": 95},
		{"fieldname": "item_name", "label": _("Ingredient / Packaging"), "fieldtype": "Data", "width": 220},
		{"fieldname": "rate", "label": _("Price"), "fieldtype": "Currency", "width": 85},
		{"fieldname": "price_uom", "label": _("Per"), "fieldtype": "Link", "options": "UOM", "width": 65},
		{"fieldname": "price_per_base_unit", "label": _("Price / Base Unit"), "fieldtype": "Currency", "precision": 4, "width": 115},
		{"fieldname": "stock_uom", "label": _("Base Unit"), "fieldtype": "Link", "options": "UOM", "width": 75},
		{"fieldname": "price_per_kg", "label": _("Price / kg"), "fieldtype": "Currency", "width": 90},
		{"fieldname": "is_cheapest", "label": _("Cheapest"), "fieldtype": "Check", "width": 75},
		{"fieldname": "cheapest_supplier", "label": _("Cheapest Supplier"), "fieldtype": "Link", "options": "Supplier", "width": 160},
		{"fieldname": "diff_pct", "label": _("vs Cheapest %"), "fieldtype": "Percent", "width": 95},
		{"fieldname": "no_price", "label": _("No Price"), "fieldtype": "Check", "width": 70},
		{"fieldname": "recipe_count", "label": _("# Recipes"), "fieldtype": "Int", "width": 80},
		{"fieldname": "recipes", "label": _("Used In"), "fieldtype": "Data", "width": 220},
		{"fieldname": "item_group", "label": _("Item Group"), "fieldtype": "Link", "options": "Item Group", "width": 120},
		{"fieldname": "item_price", "label": _("Item Price"), "fieldtype": "Link", "options": "Item Price", "width": 100},
		{"fieldname": "valid_from", "label": _("Valid From"), "fieldtype": "Date", "width": 95},
	]
