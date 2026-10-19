# Copyright (c) 2026, Happy Kitchen and contributors
# For license information, please see license.txt

"""Cost per UOM and total quantity used of every ingredient and packaging
item, across recipes (1 batch each) or actual production, followed by the
wages and services for the same recipes/batches."""

import frappe
from frappe import _
from frappe.utils import flt

from happy_kitchen.recipe_management.costing import aggregate_usage
from happy_kitchen.recipe_management.usage import get_recipe_lines, get_runs


def execute(filters=None):
	filters = frappe._dict(filters or {})
	runs = get_period_runs(filters)
	recipes = {
		r.name: r
		for r in frappe.get_all(
			"Recipe",
			filters={"name": ("in", [r["recipe"] for r in runs] or [""])},
			fields=["name", "total_labour_cost", "total_labour_minutes", "total_overhead_cost"],
		)
	}
	lines = get_recipe_lines(list(recipes))
	types = line_types(list(recipes))

	rows = aggregate_usage(runs, lines)
	if filters.component_type:
		rows = [r for r in rows if types.get(r["item"]) == filters.component_type]

	total_cost = sum(r["estimated_cost"] for r in rows) or 0
	data = []
	for r in rows:
		grams = r["stock_uom"] == "Gram"
		data.append(
			{
				"item": r["item"],
				"item_name": r["item_name"],
				"component_type": types.get(r["item"]),
				"supplier": r["supplier"],
				"stock_uom": r["stock_uom"],
				"price_per_base_unit": r["price_per_base_unit"],
				"price_per_kg": r["price_per_base_unit"] * 1000 if grams else None,
				"net_qty": r["net_qty"],
				"gross_qty": r["gross_qty"],
				"qty_kg": r["gross_qty"] / 1000 if grams else None,
				"waste_qty": r["waste_qty"],
				"total_cost": r["estimated_cost"],
				"share": r["estimated_cost"] / total_cost * 100 if total_cost else 0,
				"recipe_count": len(r["recipes"]),
				"recipes": ", ".join(r["recipes"]),
			}
		)

	batches = {r["recipe"]: flt(r["batches"]) for r in runs}
	wages = sum(flt(recipes[n].total_labour_cost) * b for n, b in batches.items() if n in recipes)
	hours = sum(flt(recipes[n].total_labour_minutes) * b for n, b in batches.items() if n in recipes) / 60
	services = sum(flt(recipes[n].total_overhead_cost) * b for n, b in batches.items() if n in recipes)
	grand = total_cost + wages + services
	if data:
		data.append({})
		data.append({"item_name": _("Total Ingredients & Packaging"), "total_cost": total_cost, "bold": 1})
		data.append({"item_name": _("Wages (Labour) - {0} h").format(flt(hours, 2)), "component_type": _("Labour"),
		             "total_cost": wages, "bold": 1})
		data.append({"item_name": _("Services & Overheads"), "component_type": _("Services"), "total_cost": services, "bold": 1})
		data.append({"item_name": _("Grand Total"), "total_cost": grand, "bold": 1})
		for row in data[-3:]:
			row["share"] = row["total_cost"] / grand * 100 if grand else 0

	packaging = sum(d["total_cost"] for d in data if d.get("component_type") == "Packaging")
	summary = [
		{"label": _("Ingredients"), "value": total_cost - packaging, "datatype": "Currency"},
		{"label": _("Packaging"), "value": packaging, "datatype": "Currency"},
		{"label": _("Wages"), "value": wages, "datatype": "Currency"},
		{"label": _("Services"), "value": services, "datatype": "Currency"},
		{"label": _("Total Cost"), "value": grand, "datatype": "Currency", "indicator": "Blue"},
		{"label": _("Ingredients Used (kg)"),
		 "value": flt(sum(d.get("qty_kg") or 0 for d in data if d.get("component_type") != "Packaging"), 2),
		 "datatype": "Float"},
	]
	chart = {
		"data": {
			"labels": [_("Ingredients"), _("Packaging"), _("Wages"), _("Services")],
			"datasets": [{"values": [flt(total_cost - packaging, 2), flt(packaging, 2), flt(wages, 2), flt(services, 2)]}],
		},
		"type": "donut",
		"height": 240,
	}
	return get_columns(), data, None, chart, summary


def get_period_runs(filters) -> list[dict]:
	if filters.based_on in ("Production Log", "Production Plan"):
		runs = get_runs(filters.from_date, filters.to_date, filters.based_on, filters.warehouse, filters.recipe)
	else:
		recipe_filters = {"status": ("!=", "Archived")}
		if filters.recipe:
			recipe_filters = {"name": filters.recipe}
		runs = [{"recipe": n, "batches": 1} for n in frappe.get_all("Recipe", filters=recipe_filters, pluck="name")]
	if filters.recipe_type:
		keep = set(frappe.get_all("Recipe", filters={"recipe_type": filters.recipe_type}, pluck="name"))
		runs = [r for r in runs if r["recipe"] in keep]
	return runs


def line_types(recipes) -> dict[str, str]:
	if not recipes:
		return {}
	return {
		r.item: r.component_type
		for r in frappe.get_all(
			"Recipe Ingredient",
			filters={"parenttype": "Recipe", "parent": ("in", recipes)},
			fields=["item", "component_type"],
		)
	}


def get_columns():
	return [
		{"fieldname": "item", "label": _("Item ID"), "fieldtype": "Link", "options": "Item", "width": 95},
		{"fieldname": "item_name", "label": _("Ingredient / Packaging"), "fieldtype": "Data", "width": 230},
		{"fieldname": "component_type", "label": _("Type"), "fieldtype": "Data", "width": 105},
		{"fieldname": "supplier", "label": _("Supplier"), "fieldtype": "Link", "options": "Supplier", "width": 150},
		{"fieldname": "stock_uom", "label": _("UOM"), "fieldtype": "Link", "options": "UOM", "width": 65},
		{"fieldname": "price_per_base_unit", "label": _("Cost / UOM"), "fieldtype": "Currency", "precision": 4, "width": 95},
		{"fieldname": "price_per_kg", "label": _("Cost / kg"), "fieldtype": "Currency", "width": 85},
		{"fieldname": "net_qty", "label": _("Net Qty Used"), "fieldtype": "Float", "width": 100},
		{"fieldname": "gross_qty", "label": _("Total Qty Used (gross)"), "fieldtype": "Float", "width": 130},
		{"fieldname": "qty_kg", "label": _("Total Used (kg)"), "fieldtype": "Float", "width": 100},
		{"fieldname": "waste_qty", "label": _("Yield Loss"), "fieldtype": "Float", "width": 85},
		{"fieldname": "total_cost", "label": _("Total Cost"), "fieldtype": "Currency", "width": 105},
		{"fieldname": "share", "label": _("% of Cost"), "fieldtype": "Percent", "width": 80},
		{"fieldname": "recipe_count", "label": _("# Recipes"), "fieldtype": "Int", "width": 75},
		{"fieldname": "recipes", "label": _("Used In"), "fieldtype": "Data", "width": 220},
	]
