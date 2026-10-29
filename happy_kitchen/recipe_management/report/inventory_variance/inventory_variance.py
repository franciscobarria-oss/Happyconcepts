# Copyright (c) 2026, Happy Kitchen and contributors
# For license information, please see license.txt

"""Actual vs theoretical ingredient usage between two approved stock takes.

Actual   = opening count + purchases received (+ batch preparations produced) - closing count
Wastage  = submitted Wastage Logs in the period: part of the variance, shown
           separately; what is left is the unexplained loss.
Expected = recipes applied to submitted Production Logs, plus sales (Delivery
           Notes, stock-updating Sales Invoices) of items that were not produced
           in the period. Counted items sold as-is (a batch preparation such as
           dough, or a bought-in item) count as used themselves. Recipe Components are broken down into their own
           ingredients; Batch Preparations count as their own stocked item.

Period: counts are compared on their date and time. Purchases are taken on
their posting date and time; production and sales are taken by date, after
the opening count's date up to and including the closing count's date.
"""

import frappe
from frappe import _
from frappe.utils import flt, get_datetime

from happy_kitchen.recipe_management import variance as v
from happy_kitchen.recipe_management.pricing import SUB_RECIPE_TYPES


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not (filters.opening_stock_take and filters.closing_stock_take):
		return get_columns(), [], _("Choose an opening and a closing approved stock take."), None, []
	opening, closing = get_counts(filters)
	tolerance = get_tolerance()
	start, end = opening.posting_datetime, closing.posting_datetime

	open_qty, open_rate = count_quantities(opening.name)
	close_qty, close_rate = count_quantities(closing.name)
	received = purchases_received(start, end)
	runs, produced_items, produced_qty = production(opening.posting_date, closing.posting_date)
	sales = v.fold_aliases(items_sold(opening.posting_date, closing.posting_date), sku_aliases())
	wasted = wastage(opening.posting_date, closing.posting_date)
	recipe_lines, sub_recipes, recipe_for_item = recipe_data()
	runs += v.runs_from_sales(sales, recipe_for_item, produced_items)
	try:
		expected = v.expand_usage(runs, recipe_lines, sub_recipes)
	except v.VarianceError as e:
		frappe.throw(str(e))

	counted = set(open_qty) | set(close_qty)
	for item, qty in v.sold_as_is(sales, recipe_for_item).items():
		if item in counted:  # e.g. dough sold to a customer, a counted bought-in item
			expected[item] = expected.get(item, 0.0) + qty
	info = item_info(counted)
	rows = []
	for item in sorted(counted, key=lambda i: (info.get(i, {}).get("item_name") or i).lower()):
		row = v.variance_row(
			v.actual_usage(open_qty.get(item), received.get(item), close_qty.get(item), produced_qty.get(item)),
			expected.get(item, 0.0),
			close_rate.get(item) or open_rate.get(item),
			tolerance,
			wasted.get(item, 0.0),
		)
		row.update(
			{
				"item": item,
				"item_name": info.get(item, {}).get("item_name"),
				"stock_uom": info.get(item, {}).get("stock_uom"),
				"opening_qty": open_qty.get(item, 0.0),
				"received_qty": received.get(item, 0.0),
				"produced_qty": produced_qty.get(item, 0.0),
				"closing_qty": close_qty.get(item, 0.0),
				"status": _("Within tolerance") if row["within_tolerance"] else _("Out of tolerance"),
			}
		)
		rows.append(row)

	t = v.totals(rows)
	not_counted = sorted(set(expected) - counted)
	if filters.only_out_of_tolerance:
		rows = [r for r in rows if not r["within_tolerance"]]
	summary = [
		{"label": _("Recorded Wastage"), "value": t["wastage_cost"], "datatype": "Currency", "indicator": "Orange" if t["wastage_cost"] else "Green"},
		{"label": _("Unexplained Loss"), "value": t["unexplained_cost"], "datatype": "Currency",
		 "indicator": "Red" if t["unexplained_cost"] > 0.005 else "Green"},
		{"label": _("Total Variance Cost"), "value": t["variance_cost"], "datatype": "Currency",
		 "indicator": "Red" if abs(flt(t["variance_pct"])) > tolerance else "Green"},
		{"label": _("Overall Variance %"), "value": flt(t["variance_pct"]), "datatype": "Percent",
		 "indicator": "Red" if abs(flt(t["variance_pct"])) > tolerance else "Green"},
		{"label": _("Out of Tolerance"), "value": t["out_of_tolerance"], "datatype": "Int",
		 "indicator": "Red" if t["out_of_tolerance"] else "Green"},
		{"label": _("Tolerance"), "value": f"±{tolerance:g}%", "datatype": "Data"},
		{"label": _("Expected but not counted"), "value": len(not_counted), "datatype": "Int",
		 "indicator": "Orange" if not_counted else "Green"},
	]
	message = None
	if not_counted:
		message = _("Used by recipes but not on the count sheets, so not in the table: {0}").format(", ".join(not_counted[:15]))
	return get_columns(), rows, message, None, summary


def get_counts(filters):
	docs = []
	for name in (filters.opening_stock_take, filters.closing_stock_take):
		d = frappe.db.get_value("Stock Take", name, ["name", "docstatus", "posting_date", "posting_time"], as_dict=True)
		if not d or d.docstatus != 1:
			frappe.throw(_("{0} is not an approved stock take").format(name))
		d.posting_datetime = get_datetime(f"{d.posting_date} {d.posting_time}")
		docs.append(d)
	if docs[1].posting_datetime <= docs[0].posting_datetime:
		frappe.throw(_("The closing stock take must be after the opening one"))
	return docs


def get_tolerance() -> float:
	value = frappe.db.get_single_value("Recipe Settings", "variance_tolerance_pct")
	return v.DEFAULT_TOLERANCE_PCT if value in (None, "") else flt(value)


def count_quantities(stock_take: str):
	qty, rate = {}, {}
	for r in frappe.get_all("Stock Take Item", filters={"parent": stock_take, "parenttype": "Stock Take"},
	                        fields=["item", "stock_qty", "valuation_rate"]):
		qty[r.item] = qty.get(r.item, 0.0) + flt(r.stock_qty)
		if flt(r.valuation_rate):
			rate[r.item] = flt(r.valuation_rate)
	return qty, rate


def purchases_received(start, end) -> dict[str, float]:
	"""Stock-UOM quantities received on Purchase Receipts and stock-updating
	Purchase Invoices (returns are negative)."""
	out: dict[str, float] = {}
	for parent, child, extra in (("Purchase Receipt", "Purchase Receipt Item", ""),
	                             ("Purchase Invoice", "Purchase Invoice Item", "and p.update_stock = 1")):
		for r in frappe.db.sql(
			f"""select c.item_code, sum(c.stock_qty) as qty
			from `tab{child}` c join `tab{parent}` p on p.name = c.parent
			where p.docstatus = 1 {extra}
				and timestamp(p.posting_date, p.posting_time) > %(start)s
				and timestamp(p.posting_date, p.posting_time) <= %(end)s
			group by c.item_code""",
			{"start": start, "end": end},
			as_dict=True,
		):
			out[r.item_code] = out.get(r.item_code, 0.0) + flt(r.qty)
	return out


def production(from_date, to_date):
	"""Runs from submitted Production Logs, the items they made, and the units
	of batch preparations made (they enter stock like a purchase)."""
	rows = frappe.db.sql(
		"""select c.recipe, sum(c.batches) as batches, sum(c.units) as units, r.item, r.recipe_type
		from `tabRecipe Production Log` p
		join `tabRecipe Production Log Item` c on c.parent = p.name
		join `tabRecipe` r on r.name = c.recipe
		where p.docstatus = 1 and p.posting_date > %(f)s and p.posting_date <= %(t)s
		group by c.recipe, r.item, r.recipe_type""",
		{"f": from_date, "t": to_date},
		as_dict=True,
	)
	runs = [{"recipe": r.recipe, "batches": flt(r.batches)} for r in rows]
	produced_items = {r.item for r in rows}
	produced_qty: dict[str, float] = {}
	for r in rows:
		if r.recipe_type == v.BATCH_PREPARATION:
			produced_qty[r.item] = produced_qty.get(r.item, 0.0) + flt(r.units)
	return runs, produced_items, produced_qty


def wastage(from_date, to_date) -> dict[str, float]:
	"""Stock-UOM quantities on submitted Wastage Logs in the period."""
	out: dict[str, float] = {}
	if not frappe.db.table_exists("Wastage Log Item"):  # Wastage Log arrives in P11
		return out
	for r in frappe.db.sql(
		"""select c.item, sum(c.stock_qty) as qty
		from `tabWastage Log Item` c join `tabWastage Log` p on p.name = c.parent
		where p.docstatus = 1 and p.posting_date > %(f)s and p.posting_date <= %(t)s
		group by c.item""",
		{"f": from_date, "t": to_date},
		as_dict=True,
	):
		out[r.item] = flt(r.qty)
	return out


def items_sold(from_date, to_date) -> dict[str, float]:
	"""Units delivered: Delivery Notes plus Sales Invoices that update stock
	(an invoice made from a delivery note doesn't, so nothing counts twice)."""
	out: dict[str, float] = {}
	for parent, child, extra in (("Delivery Note", "Delivery Note Item", ""),
	                             ("Sales Invoice", "Sales Invoice Item", "and p.update_stock = 1")):
		for r in frappe.db.sql(
			f"""select c.item_code, sum(c.stock_qty) as qty
			from `tab{child}` c join `tab{parent}` p on p.name = c.parent
			where p.docstatus = 1 {extra} and p.posting_date > %(f)s and p.posting_date <= %(t)s
			group by c.item_code""",
			{"f": from_date, "t": to_date},
			as_dict=True,
		):
			out[r.item_code] = out.get(r.item_code, 0.0) + flt(r.qty)
	return out


def sku_aliases() -> dict[str, tuple]:
	"""Sales items linked to another item's recipe (Item → Made From Recipe)."""
	out = {}
	for i in frappe.get_all("Item", filters={"hk_recipe": ("is", "set")}, fields=["name", "hk_recipe", "hk_recipe_qty"]):
		target = frappe.db.get_value("Recipe", i.hk_recipe, "item")
		if target and target != i.name:
			out[i.name] = (target, flt(i.hk_recipe_qty) or 1.0)
	return out


def recipe_data():
	"""Lines per recipe (gross qty per batch, stock UOM), the in-house
	sub-recipes by item, and the recipe used for each sold item."""
	recipes = frappe.get_all("Recipe", fields=["name", "item", "recipe_type", "batch_yield", "status"])
	lines: dict[str, list] = {}
	for r in frappe.get_all("Recipe Ingredient", filters={"parenttype": "Recipe"},
	                        fields=["parent", "item", "base_qty", "gross_qty"], order_by="parent, idx"):
		lines.setdefault(r.parent, []).append(r)
	rank = {"Active": 0, "Draft": 1, "Archived": 2}
	sub_recipes, recipe_for_item = {}, {}
	for r in sorted(recipes, key=lambda r: rank.get(r.status, 3)):
		info = {"recipe": r.name, "recipe_type": r.recipe_type, "batch_yield": flt(r.batch_yield) or 1.0}
		recipe_for_item.setdefault(r.item, info)
		if r.recipe_type in SUB_RECIPE_TYPES and r.status != "Archived":
			sub_recipes.setdefault(r.item, info)
	return lines, sub_recipes, recipe_for_item


def item_info(items) -> dict:
	if not items:
		return {}
	return {i.name: i for i in frappe.get_all("Item", filters={"name": ("in", list(items))}, fields=["name", "item_name", "stock_uom"])}


def get_columns():
	return [
		{"fieldname": "item", "label": _("Ingredient ID"), "fieldtype": "Link", "options": "Item", "width": 100},
		{"fieldname": "item_name", "label": _("Ingredient"), "fieldtype": "Data", "width": 210},
		{"fieldname": "stock_uom", "label": _("Unit"), "fieldtype": "Link", "options": "UOM", "width": 65},
		{"fieldname": "opening_qty", "label": _("Opening"), "fieldtype": "Float", "width": 95},
		{"fieldname": "received_qty", "label": _("Received"), "fieldtype": "Float", "width": 95},
		{"fieldname": "produced_qty", "label": _("Produced"), "fieldtype": "Float", "width": 90},
		{"fieldname": "closing_qty", "label": _("Closing"), "fieldtype": "Float", "width": 95},
		{"fieldname": "actual_usage", "label": _("Actual Used"), "fieldtype": "Float", "width": 105},
		{"fieldname": "expected_usage", "label": _("Expected Used"), "fieldtype": "Float", "width": 110},
		{"fieldname": "variance_qty", "label": _("Variance Qty"), "fieldtype": "Float", "width": 105},
		{"fieldname": "unit_cost", "label": _("Unit Cost"), "fieldtype": "Currency", "precision": 4, "width": 95},
		{"fieldname": "variance_cost", "label": _("Variance Cost"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "variance_pct", "label": _("Variance %"), "fieldtype": "Percent", "width": 95},
		{"fieldname": "wastage_qty", "label": _("Recorded Waste"), "fieldtype": "Float", "width": 105},
		{"fieldname": "unexplained_cost", "label": _("Unexplained Cost"), "fieldtype": "Currency", "width": 115},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 125},
		{"fieldname": "within_tolerance", "label": _("Within Tolerance"), "fieldtype": "Check", "hidden": 1},
	]
