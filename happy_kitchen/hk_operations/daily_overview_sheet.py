"""Daily Sales Overview page: one delivery day, grid on the front, what's needed on the back.

	/api/method/happy_kitchen.hk_operations.daily_overview_sheet.sheet?date=2026-10-24

Draft and submitted orders both count (drafts are marked); cancelled ones don't.
Grid maths: daily_overview.py (unit-tested). The needs list uses daily_plan.plan_day
for the full ordered quantity, so it shows batches and ingredients once a sold item
is linked to its recipe, and the plain quantity per product until then."""

from __future__ import annotations

import frappe
from frappe.utils import add_days, cint, format_datetime, formatdate, getdate, now_datetime, nowdate
from werkzeug.wrappers import Response

from happy_kitchen.hk_operations import daily_overview as grid
from happy_kitchen.recipe_management.daily_plan import plan_day
from happy_kitchen.recipe_management.production_sheet import fmt_qty, stock_on_hand
from happy_kitchen.recipe_management.report.inventory_variance.inventory_variance import recipe_data, sku_aliases
from happy_kitchen.recipe_management.variance import fold_aliases

CUSTOMER_FIELDS = ["name", "customer_name", "hk_sheet_group", "hk_sheet_label", "hk_sheet_label_zh", "hk_sheet_sort"]



def order_lines(day: str) -> list[dict]:
	return frappe.db.sql(
		"""
		select so.name as sales_order, so.docstatus, so.customer, so.customer_name, so.po_no,
			so.grand_total as so_grand_total,
			soi.item_code, soi.item_name, soi.customer_item_code, soi.uom, soi.stock_uom,
			soi.conversion_factor, soi.qty, soi.qty * soi.conversion_factor as stock_qty
		from `tabSales Order Item` soi
		join `tabSales Order` so on so.name = soi.parent
		where so.docstatus < 2 and so.status not in ('Closed', 'Cancelled')
			and coalesce(soi.delivery_date, so.delivery_date) = %(day)s
		order by so.customer_name, so.name, soi.idx""",
		{"day": day}, as_dict=True)


def invoices_for(sales_orders: list[str]) -> list[dict]:
	if not sales_orders:
		return []
	return frappe.db.sql(
		"""
		select distinct si.name, sii.sales_order, si.grand_total
		from `tabSales Invoice Item` sii join `tabSales Invoice` si on si.name = sii.parent
		where sii.sales_order in %(so)s and si.docstatus < 2""",
		{"so": tuple(sales_orders)}, as_dict=True)


def item_info(codes: set[str]) -> dict[str, dict]:
	meta = frappe.get_meta("Item")
	fields = ["name", "item_name", "stock_uom", "shelf_life_in_days"]
	if meta.has_field("hk_item_name_zh"):
		fields.append("hk_item_name_zh")
	out = {}
	for i in frappe.get_all("Item", filters={"name": ("in", list(codes) or [""])}, fields=fields):
		out[i.name] = {"item_name": i.item_name, "item_name_zh": i.get("hk_item_name_zh") or "",
		               "shelf_life_days": i.shelf_life_in_days, "stock_uom": i.stock_uom}
	return out


def build(day: str) -> dict:
	lines = order_lines(day)
	meta = frappe.get_meta("Customer")
	customers = {c.name: c for c in frappe.get_all(
		"Customer", filters={"name": ("in", list({l.customer for l in lines}) or [""])},
		fields=[f for f in CUSTOMER_FIELDS if f in ("name", "customer_name") or meta.has_field(f)])}
	codes = {grid.sheet_code(l) for l in lines} | {l.item_code for l in lines}
	items = item_info(codes)
	for l in lines:  # a placeholder item (SKU-nnnn) shows under the customer's code but uses its own details
		items.setdefault(grid.sheet_code(l), items.get(l.item_code) or {})
	d = getdate(day)
	data = grid.build_grid(d, [dict(l) for l in lines], {k: dict(v) for k, v in customers.items()}, items,
	                       invoices_for(sorted({l.sales_order for l in lines})))

	# what is needed: full ordered quantity, drafts included, no finished stock deducted
	demand: dict[str, float] = {}
	for l in lines:
		demand[l.item_code] = demand.get(l.item_code, 0.0) + (l.stock_qty or 0)
	demand = fold_aliases(demand, sku_aliases())
	recipe_lines, sub_recipes, recipe_for_item = recipe_data()
	plan = plan_day(demand, recipe_for_item, sub_recipes, recipe_lines, stock_on_hand(), False)
	label = {l.item_code: grid.sheet_code(l) for l in lines}
	need_codes = {r["item"] for k in ("make", "preps", "pick", "ingredients") for r in plan[k]}
	items.update({k: v for k, v in item_info(need_codes - set(items)).items()})

	needs = []
	for key, title in (("make", "Make 生產"), ("preps", "Dough & preps 半成品"), ("pick", "Products 產品"),
	                   ("ingredients", "Ingredients 材料")):
		for r in plan[key]:
			info = items.get(r["item"]) or {}
			uom = info.get("stock_uom") or ""
			code = label.get(r["item"], r["item"])
			need = r.get("need", r.get("units"))
			stock = r.get("in_stock", r.get("on_hand"))
			needs.append({
				"kind": title, "code": code, "name": info.get("item_name") or r["item"], "zh": info.get("item_name_zh") or "",
				"need": fmt_qty(need, uom, True), "stock": fmt_qty(stock or 0, uom),
				"short": fmt_qty(r["short"], uom, True) if r.get("short") else "", "is_short": bool(r.get("short")),
			})
	# placeholder SKU lines merge under the customer's code
	merged: dict[tuple, dict] = {}
	for n in needs:
		k = (n["kind"], n["code"])
		merged.setdefault(k, n)
	data["needs"] = list(merged.values())
	data["orders"] = len({l.sales_order for l in lines})
	data["draft_lines"] = sum(1 for l in lines if l.docstatus == 0)
	data["lines"] = len(lines)
	return data


@frappe.whitelist()
def sheet(date: str | None = None):
	"""The printable A4 pages (HTML): grid, then what's needed on the back."""
	for dt in ("Sales Order", "Customer"):
		frappe.has_permission(dt, "read", throw=True)
	day = str(getdate(date or nowdate()))
	d = getdate(day)
	data = build(day)
	context = {
		"d": data, "day": day, "weekday": d.strftime("%a"), "day_fmt": formatdate(day),
		"b": frappe.get_attr("happy_kitchen.recipe_management.utils.get_recipe_branding")(),
		"printed": format_datetime(now_datetime(), "dd-MM-yyyy HH:mm"),
		"prev_day": str(add_days(day, -1)), "next_day": str(add_days(day, 1)), "today": nowdate(),
		"fmt_date": lambda x: x.strftime("%a %d %b") if x else "",
		"fmt_qty": lambda v: f"{v:,.0f}" if float(v).is_integer() else f"{v:,.2f}",
		"fmt_money": lambda v: f"HK${v:,.2f}" if v else "",
	}
	html = frappe.render_template("happy_kitchen/templates/daily_overview.html", context)
	return Response(html, content_type="text/html; charset=utf-8")
