# Copyright (c) 2026, Happy Kitchen and contributors
# For license information, please see license.txt

"""Per-ingredient cost breakdown of each recipe, with labour (wages) and
overheads/services, and a fully loaded cost per ingredient line."""

import frappe
from frappe import _
from frappe.utils import flt

from happy_kitchen.recipe_management.costing import allocate_loaded_costs


def execute(filters=None):
	filters = frappe._dict(filters or {})
	recipe_filters = {"status": filters.status} if filters.status else {"status": ("!=", "Archived")}
	if filters.recipe_type:
		recipe_filters["recipe_type"] = filters.recipe_type
	if filters.recipe:
		recipe_filters = {"name": filters.recipe}
	names = frappe.get_all("Recipe", filters=recipe_filters, pluck="name", order_by="name")

	data = []
	for name in names:
		data.extend(recipe_rows(frappe.get_doc("Recipe", name)))

	chart = summary = None
	if len(names) == 1:
		doc = frappe.get_doc("Recipe", names[0])
		chart = cost_chart(doc)
		summary = report_summary(doc)
	return get_columns(), data, None, chart, summary


def recipe_rows(doc):
	units = flt(doc.batch_yield) or 1
	total = flt(doc.total_batch_cost)

	def share(amount):
		return flt(amount) / total * 100 if total else 0

	rows = [
		{
			"component": f"{doc.name} - {doc.recipe_name} ({doc.recipe_type})",
			"recipe": doc.name,
			"type": _("Recipe"),
			"batch_cost": doc.total_batch_cost,
			"unit_cost": doc.cost_per_unit,
			"share": 100 if total else 0,
			"loaded_cost": doc.total_batch_cost,
			"loaded_unit_cost": doc.cost_per_unit,
			"indent": 0,
		}
	]
	loaded = allocate_loaded_costs(
		[flt(r.line_cost) for r in doc.ingredients], doc.total_labour_cost, doc.total_overhead_cost
	)
	for row, loaded_cost in zip(doc.ingredients, loaded):
		rows.append(
			{
				"component": row.item_name,
				"recipe": doc.name,
				"type": _(row.component_type or "Ingredient"),
				"item": row.item,
				"supplier": row.supplier,
				"qty": row.qty,
				"uom": row.uom,
				"yield_pct": row.yield_pct,
				"gross_qty": row.gross_qty,
				"stock_uom": row.stock_uom,
				"price_per_base_unit": row.price_per_base_unit,
				"batch_cost": row.line_cost,
				"unit_cost": flt(row.line_cost) / units,
				"share": share(row.line_cost),
				"loaded_cost": loaded_cost,
				"loaded_unit_cost": loaded_cost / units,
				"indent": 1,
			}
		)
	for row in doc.labour:
		rows.append(
			{
				"component": " / ".join(filter(None, [row.activity, row.staff_role])),
				"recipe": doc.name,
				"type": _("Labour"),
				"qty": row.minutes,
				"uom": _("min"),
				"price_per_base_unit": flt(row.hourly_rate) / 60,
				"batch_cost": row.cost,
				"unit_cost": flt(row.cost) / units,
				"share": share(row.cost),
				"indent": 1,
			}
		)
	for row in doc.overheads:
		rows.append(
			{
				"component": row.service,
				"recipe": doc.name,
				"type": _("Overhead / Service"),
				"uom": row.basis,
				"batch_cost": row.amount,
				"unit_cost": flt(row.amount) / units,
				"share": share(row.amount),
				"indent": 1,
			}
		)
	return rows


def cost_chart(doc):
	return {
		"data": {
			"labels": [_("Ingredients"), _("Labour"), _("Overheads & Services")],
			"datasets": [
				{"values": [flt(doc.total_ingredient_cost, 2), flt(doc.total_labour_cost, 2), flt(doc.total_overhead_cost, 2)]}
			],
		},
		"type": "donut",
		"height": 260,
	}


def report_summary(doc):
	return [
		{"label": _("Cost / Batch"), "value": doc.total_batch_cost, "datatype": "Currency"},
		{"label": _("Cost / Unit"), "value": doc.cost_per_unit, "datatype": "Currency"},
		{"label": _("Selling Price"), "value": doc.selling_price, "datatype": "Currency"},
		{"label": _("Food Cost %"), "value": doc.food_cost_pct, "datatype": "Percent",
		 "indicator": "Green" if flt(doc.food_cost_pct) <= 35 else "Red"},
		{"label": _("Margin / Unit"), "value": doc.gross_margin, "datatype": "Currency",
		 "indicator": "Green" if flt(doc.gross_margin) >= 0 else "Red"},
	]


def get_columns():
	return [
		{"fieldname": "component", "label": _("Component"), "fieldtype": "Data", "width": 280},
		{"fieldname": "type", "label": _("Type"), "fieldtype": "Data", "width": 110},
		{"fieldname": "recipe", "label": _("Recipe"), "fieldtype": "Link", "options": "Recipe", "width": 90, "hidden": 1},
		{"fieldname": "item", "label": _("Ingredient ID"), "fieldtype": "Link", "options": "Item", "width": 95},
		{"fieldname": "supplier", "label": _("Supplier"), "fieldtype": "Link", "options": "Supplier", "width": 150},
		{"fieldname": "qty", "label": _("Net Qty"), "fieldtype": "Float", "width": 80},
		{"fieldname": "uom", "label": _("Unit / Basis"), "fieldtype": "Data", "width": 90},
		{"fieldname": "yield_pct", "label": _("Yield %"), "fieldtype": "Percent", "width": 70},
		{"fieldname": "gross_qty", "label": _("Gross Base Qty"), "fieldtype": "Float", "width": 100},
		{"fieldname": "stock_uom", "label": _("Base Unit"), "fieldtype": "Data", "width": 70},
		{"fieldname": "price_per_base_unit", "label": _("Price / Base Unit"), "fieldtype": "Currency", "width": 110, "precision": 4},
		{"fieldname": "batch_cost", "label": _("Cost / Batch"), "fieldtype": "Currency", "width": 105},
		{"fieldname": "unit_cost", "label": _("Cost / Unit"), "fieldtype": "Currency", "width": 95},
		{"fieldname": "share", "label": _("% of Total"), "fieldtype": "Percent", "width": 85},
		{"fieldname": "loaded_cost", "label": _("Loaded Cost / Batch"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "loaded_unit_cost", "label": _("Loaded Cost / Unit"), "fieldtype": "Currency", "width": 125},
	]
