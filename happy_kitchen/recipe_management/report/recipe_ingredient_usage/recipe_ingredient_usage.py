# Copyright (c) 2026, Happy Kitchen and contributors
# For license information, please see license.txt

"""Ingredient usage (net, gross, waste) for a period or a planned run, next
to stock on hand. Same data as usage.get_ingredient_usage, the API the
inventory component reads."""

import frappe
from frappe import _
from frappe.utils import flt

from happy_kitchen.recipe_management.usage import get_ingredient_usage


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if filters.recipe and flt(filters.planned_batches):
		rows = get_ingredient_usage(
			warehouse=filters.warehouse, recipe_batches={filters.recipe: flt(filters.planned_batches)}
		)
	else:
		rows = get_ingredient_usage(
			from_date=filters.from_date,
			to_date=filters.to_date,
			source=filters.source or "Production Log",
			warehouse=filters.warehouse,
			recipe=filters.recipe,
		)
	for r in rows:
		r["recipes"] = ", ".join(r["recipes"])

	summary = [
		{"label": _("Ingredients"), "value": len(rows), "datatype": "Int"},
		{"label": _("Estimated Cost"), "value": sum(flt(r["estimated_cost"]) for r in rows), "datatype": "Currency"},
		{"label": _("Waste (yield loss) Cost"),
		 "value": sum(flt(r["waste_qty"]) * flt(r["price_per_base_unit"]) for r in rows), "datatype": "Currency"},
		{"label": _("Short on Stock"), "value": sum(1 for r in rows if r["shortage_qty"] > 0), "datatype": "Int",
		 "indicator": "Red" if any(r["shortage_qty"] > 0 for r in rows) else "Green"},
	]
	return get_columns(), rows, None, None, summary


def get_columns():
	return [
		{"fieldname": "item", "label": _("Ingredient ID"), "fieldtype": "Link", "options": "Item", "width": 95},
		{"fieldname": "item_name", "label": _("Ingredient"), "fieldtype": "Data", "width": 220},
		{"fieldname": "stock_uom", "label": _("Unit"), "fieldtype": "Link", "options": "UOM", "width": 65},
		{"fieldname": "net_qty", "label": _("Net Qty"), "fieldtype": "Float", "width": 95},
		{"fieldname": "gross_qty", "label": _("Gross Qty (issue)"), "fieldtype": "Float", "width": 115},
		{"fieldname": "waste_qty", "label": _("Yield Loss"), "fieldtype": "Float", "width": 90},
		{"fieldname": "price_per_base_unit", "label": _("Price / Unit"), "fieldtype": "Currency", "precision": 4, "width": 95},
		{"fieldname": "estimated_cost", "label": _("Est. Cost"), "fieldtype": "Currency", "width": 95},
		{"fieldname": "supplier", "label": _("Supplier"), "fieldtype": "Link", "options": "Supplier", "width": 150},
		{"fieldname": "actual_qty", "label": _("In Stock"), "fieldtype": "Float", "width": 90},
		{"fieldname": "projected_qty", "label": _("After Usage"), "fieldtype": "Float", "width": 95},
		{"fieldname": "shortage_qty", "label": _("Shortage"), "fieldtype": "Float", "width": 85},
		{"fieldname": "recipes", "label": _("Recipes"), "fieldtype": "Data", "width": 200},
	]
