"""Ingredient usage: how much of each ingredient the kitchen used (or will use).

This is the contract for the inventory component. `get_ingredient_usage`
returns one row per ingredient in its stock UOM (Gram / Nos):

	item, item_name, stock_uom, supplier, price_per_base_unit,
	net_qty      quantity that ends up in the products
	gross_qty    quantity to issue/buy (net / yield %)
	waste_qty    gross - net
	estimated_cost, recipes (list of recipe names),
	actual_qty   stock on hand (in `warehouse`, or all warehouses)
	projected_qty  actual_qty - gross_qty
	shortage_qty   max(0, -projected_qty)
"""

import json

import frappe
from frappe import _
from frappe.utils import flt

from happy_kitchen.recipe_management.costing import aggregate_usage

SOURCES = ("Production Log", "Production Plan")


def get_recipe_lines(recipes) -> dict[str, list[dict]]:
	recipes = list(set(recipes))
	if not recipes:
		return {}
	rows = frappe.get_all(
		"Recipe Ingredient",
		filters={"parenttype": "Recipe", "parent": ("in", recipes)},
		fields=["parent", "item", "item_name", "stock_uom", "base_qty", "gross_qty", "price_per_base_unit", "supplier"],
		order_by="parent, idx",
	)
	out: dict[str, list[dict]] = {}
	for r in rows:
		out.setdefault(r.parent, []).append(r)
	return out


def get_runs(from_date=None, to_date=None, source="Production Log", warehouse=None, recipe=None) -> list[dict]:
	"""Recipes and batch counts from submitted Production Logs or Production Plans."""
	if source not in SOURCES:
		frappe.throw(_("Source must be one of {0}").format(", ".join(SOURCES)))
	conditions, values = ["parent_doc.docstatus = 1"], {}
	if from_date:
		conditions.append("parent_doc.posting_date >= %(from_date)s")
		values["from_date"] = from_date
	if to_date:
		conditions.append("parent_doc.posting_date <= %(to_date)s")
		values["to_date"] = to_date

	if source == "Production Log":
		if warehouse:
			conditions.append("parent_doc.warehouse = %(warehouse)s")
			values["warehouse"] = warehouse
		if recipe:
			conditions.append("child.recipe = %(recipe)s")
			values["recipe"] = recipe
		return frappe.db.sql(
			f"""
			select child.recipe, sum(child.batches) as batches
			from `tabRecipe Production Log` parent_doc
			join `tabRecipe Production Log Item` child on child.parent = parent_doc.name
			where {" and ".join(conditions)}
			group by child.recipe
			""",
			values,
			as_dict=True,
		)

	# Production Plan: planned_qty is in units; recipes are named by SKU (item code).
	if recipe:
		conditions.append("child.item_code = %(recipe)s")
		values["recipe"] = recipe
	rows = frappe.db.sql(
		f"""
		select child.item_code as recipe, sum(child.planned_qty) as units, r.batch_yield
		from `tabProduction Plan` parent_doc
		join `tabProduction Plan Item` child on child.parent = parent_doc.name
		join `tabRecipe` r on r.name = child.item_code
		where {" and ".join(conditions)}
		group by child.item_code, r.batch_yield
		""",
		values,
		as_dict=True,
	)
	return [{"recipe": r.recipe, "batches": flt(r.units) / (flt(r.batch_yield) or 1)} for r in rows]


def parse_recipe_batches(recipe_batches) -> list[dict]:
	"""Accept {"FC0008": 2} or [{"recipe": "FC0008", "batches": 2}] (or JSON of either)."""
	if isinstance(recipe_batches, str):
		recipe_batches = json.loads(recipe_batches)
	if isinstance(recipe_batches, dict):
		return [{"recipe": k, "batches": flt(v)} for k, v in recipe_batches.items()]
	return [{"recipe": r["recipe"], "batches": flt(r.get("batches"))} for r in recipe_batches or []]


def add_stock_levels(rows: list[dict], warehouse=None) -> None:
	items = [r["item"] for r in rows]
	if not items:
		return
	filters = {"item_code": ("in", items)}
	if warehouse:
		filters["warehouse"] = warehouse
	stock: dict[str, float] = {}
	for b in frappe.get_all("Bin", filters=filters, fields=["item_code", "actual_qty"]):
		stock[b.item_code] = stock.get(b.item_code, 0) + flt(b.actual_qty)
	for r in rows:
		r["actual_qty"] = stock.get(r["item"], 0.0)
		r["projected_qty"] = r["actual_qty"] - r["gross_qty"]
		r["shortage_qty"] = max(0.0, -r["projected_qty"])


@frappe.whitelist()
def get_ingredient_usage(
	from_date=None, to_date=None, source="Production Log", warehouse=None, recipe=None, recipe_batches=None
) -> list[dict]:
	"""Ingredient usage for a period (from Production Logs / Plans) or for an
	ad-hoc plan passed as recipe_batches, e.g. {"FC0008": 3, "IK0008": 1}."""
	frappe.has_permission("Recipe", "read", throw=True)
	if recipe_batches:
		runs = parse_recipe_batches(recipe_batches)
	else:
		runs = get_runs(from_date, to_date, source, warehouse, recipe)
	rows = aggregate_usage(runs, get_recipe_lines([r["recipe"] for r in runs]))
	add_stock_levels(rows, warehouse)
	return rows
