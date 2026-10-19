"""A4 production sheet for one day: what to make for the sales orders due that
day, which batch preparations (dough, bases) to top up, and which ingredients
are short. Opened from the Today home ("Print A4" per day, and the header button):

	/api/method/happy_kitchen.recipe_management.production_sheet.sheet?date=2026-10-14

The quantities come from daily_plan.plan_day (unit-tested)."""

from __future__ import annotations

import math

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, format_datetime, getdate, now_datetime, nowdate
from werkzeug.wrappers import Response

from happy_kitchen.recipe_management.daily_plan import plan_day
from happy_kitchen.recipe_management.report.inventory_variance.inventory_variance import recipe_data, sku_aliases
from happy_kitchen.recipe_management.variance import fold_aliases

OPEN_SO_STATUSES = ("To Deliver and Bill", "To Deliver")


def order_lines(day: str) -> list[dict]:
	"""Undelivered sales order lines due on `day` (each line's own delivery date)."""
	return frappe.db.sql(
		"""
		select so.name as sales_order, so.customer, so.customer_name, soi.item_code, soi.item_name,
			soi.uom, soi.stock_uom, soi.conversion_factor,
			(soi.qty - soi.delivered_qty) as qty,
			(soi.qty - soi.delivered_qty) * soi.conversion_factor as stock_qty
		from `tabSales Order Item` soi
		join `tabSales Order` so on so.name = soi.parent
		where so.docstatus = 1 and so.status in %(statuses)s
			and coalesce(soi.delivery_date, so.delivery_date) = %(day)s
			and soi.qty > soi.delivered_qty
		order by so.customer_name, so.name, soi.idx""",
		{"statuses": OPEN_SO_STATUSES, "day": day},
		as_dict=True,
	)


def stock_on_hand() -> dict[str, float]:
	stock: dict[str, float] = {}
	for b in frappe.db.sql("select item_code, sum(actual_qty) as qty from `tabBin` group by item_code", as_dict=True):
		stock[b.item_code] = flt(b.qty)
	return stock


def fmt_qty(qty, uom: str | None, round_up: bool = False) -> str:
	"""12500 Gram -> 12.5 kg; 3.2 Nos -> 4 Nos when rounding up a need."""
	qty = flt(qty)
	uom = uom or ""
	if uom.lower() in ("gram", "g") and abs(qty) >= 1000:
		return f"{qty / 1000:,.2f}".rstrip("0").rstrip(".") + " kg"
	if uom.lower() in ("gram", "g"):
		return f"{qty:,.0f} g"
	if uom.lower() in ("nos", "piece", "unit", "box") or float(qty).is_integer():
		n = math.ceil(qty - 1e-9) if round_up else round(qty)
		return f"{n:,} {uom}".strip()
	return f"{qty:,.2f}".rstrip("0").rstrip(".") + f" {uom}"


def build(day: str, use_finished_stock: bool = True) -> dict:
	lines = order_lines(day)
	recipe_lines, sub_recipes, recipe_for_item = recipe_data()
	demand: dict[str, float] = {}
	for l in lines:
		demand[l.item_code] = demand.get(l.item_code, 0.0) + flt(l.stock_qty)
	demand = fold_aliases(demand, sku_aliases())
	stock = stock_on_hand()
	plan = plan_day(demand, recipe_for_item, sub_recipes, recipe_lines, stock, use_finished_stock)

	# names and units for everything on the sheet
	items = set(demand) | {r["item"] for key in ("make", "preps", "pick", "ingredients") for r in plan[key]}
	info = {
		i.name: i
		for i in frappe.get_all("Item", filters={"name": ("in", list(items) or [""])}, fields=["name", "item_name", "stock_uom"])
	}
	recipes = {r["recipe"] for r in plan["make"] + plan["preps"] if r.get("recipe")} | {c["recipe"] for c in plan["components"]}
	rinfo = {
		r.name: r
		for r in frappe.get_all("Recipe", filters={"name": ("in", list(recipes) or [""])}, fields=["name", "recipe_name", "yield_uom", "item"])
	}

	def name(item):
		return (info.get(item) or {}).get("item_name") or item

	def uom(item):
		return (info.get(item) or {}).get("stock_uom") or ""

	for r in plan["make"]:
		u = (rinfo.get(r["recipe"]) or {}).get("yield_uom") or uom(r["item"])
		r.update(name=name(r["item"]), uom=u,
		         ordered_fmt=fmt_qty(r["ordered"], u), on_hand_fmt=fmt_qty(r["on_hand"], u),
		         to_make_fmt=fmt_qty(r["to_make"], u, True), units_fmt=fmt_qty(r["units"], u),
		         yield_fmt=fmt_qty(r["batch_yield"], u))
	for c in plan["components"]:
		ri = rinfo.get(c["recipe"]) or {}
		c.update(name=ri.get("recipe_name") or c["recipe"], qty_fmt=fmt_qty(c["units"], ri.get("yield_uom") or uom(ri.get("item")), True))
	for r in plan["preps"]:
		u = uom(r["item"])
		r.update(name=name(r["item"]), uom=u, need_fmt=fmt_qty(r["need"], u, True), in_stock_fmt=fmt_qty(r["in_stock"], u),
		         short_fmt=fmt_qty(r["short"], u, True), units_fmt=fmt_qty(r["units"], u), yield_fmt=fmt_qty(r["batch_yield"], u))
	for key in ("pick", "ingredients"):
		for r in plan[key]:
			u = uom(r["item"])
			r.update(name=name(r["item"]), uom=u, need_fmt=fmt_qty(r["need"], u, True),
			         in_stock_fmt=fmt_qty(r["in_stock"], u), short_fmt=fmt_qty(r["short"], u, True))
	plan["make"].sort(key=lambda r: r["name"].lower())
	plan["preps"].sort(key=lambda r: (not r["batches"], r["name"].lower()))
	plan["ingredients"].sort(key=lambda r: (r["short"] <= 1e-9, r["name"].lower()))

	orders: dict[str, dict] = {}
	for l in lines:
		o = orders.setdefault(l.sales_order, {"name": l.sales_order, "customer": l.customer_name or l.customer, "lines": []})
		o["lines"].append(f"{fmt_qty(l.qty, l.uom)} {l.item_name}")
	return {
		"day": day,
		"use_finished_stock": use_finished_stock,
		"orders": list(orders.values()),
		"short_ingredients": sum(1 for r in plan["ingredients"] if r["short"] > 1e-9),
		"prep_suggestions": sum(1 for r in plan["preps"] if r["batches"]),
		**plan,
	}


@frappe.whitelist()
def sheet(date: str | None = None, use_stock: int | str = 1):
	"""The printable A4 page (HTML)."""
	for dt in ("Sales Order", "Recipe"):
		frappe.has_permission(dt, "read", throw=True)
	day = str(getdate(date or nowdate()))
	data = build(day, bool(cint(use_stock)))
	d = getdate(day)
	context = {
		"d": data,
		"b": frappe.get_attr("happy_kitchen.recipe_management.utils.get_recipe_branding")(),
		"weekday": d.strftime("%A"),
		"day_fmt": frappe.utils.formatdate(day),
		"printed": format_datetime(now_datetime(), "dd-MM-yyyy HH:mm"),
		"printed_by": frappe.utils.get_fullname(frappe.session.user),
		"prev_day": str(add_days(day, -1)),
		"next_day": str(add_days(day, 1)),
		"today": nowdate(),
		"use_stock": cint(use_stock),
	}
	html = frappe.render_template("happy_kitchen/templates/production_sheet.html", context)
	return Response(html, content_type="text/html; charset=utf-8")
