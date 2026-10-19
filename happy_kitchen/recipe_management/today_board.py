"""Board part of the Today home (today.py merges it with dashboard.py).

Top: what is happening today (orders going out, production planned and made,
deliveries coming in, who is on shift). Below: the tasks, in three columns:
ordering (ingredients short for the next days' orders, after what is already on
order), receiving (deliveries due or late, deliveries that differed) and
production (what is left to make today, batch preparations to top up, and
label jobs once the labels feature (P15) is installed: guarded by DocType exists).
Each part is only included when the user can read the doctypes behind it.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, nowdate

from happy_kitchen.recipe_management import board
from happy_kitchen.recipe_management.daily_plan import plan_day
from happy_kitchen.recipe_management.production_sheet import fmt_qty, stock_on_hand
from happy_kitchen.recipe_management.report.inventory_variance.inventory_variance import recipe_data, sku_aliases
from happy_kitchen.recipe_management.variance import fold_aliases

OPEN_SO_STATUSES = ("To Deliver and Bill", "To Deliver")
OPEN_PO_STATUSES = ("To Receive and Bill", "To Receive")
LOOKAHEAD_DAYS = 3  # ordering looks at orders due today and the next 2 days
DISCREPANCY_DAYS = 14
ROWS = 8


def _can(doctype: str, ptype: str = "read") -> bool:
	return bool(frappe.db.exists("DocType", doctype)) and frappe.has_permission(doctype, ptype)


def _open_lines(until: str) -> list[dict]:
	"""Undelivered sales order lines due on or before `until` (late ones included)."""
	return frappe.db.sql(
		"""
		select so.name as sales_order, so.customer, so.customer_name, soi.item_code, soi.item_name, soi.uom,
			coalesce(soi.delivery_date, so.delivery_date) as delivery_date,
			(soi.qty - soi.delivered_qty) as qty,
			(soi.qty - soi.delivered_qty) * soi.conversion_factor as stock_qty
		from `tabSales Order Item` soi
		join `tabSales Order` so on so.name = soi.parent
		where so.docstatus = 1 and so.status in %(statuses)s
			and coalesce(soi.delivery_date, so.delivery_date) <= %(until)s
			and soi.qty > soi.delivered_qty
		order by coalesce(soi.delivery_date, so.delivery_date), so.customer_name, so.name, soi.idx""",
		{"statuses": OPEN_SO_STATUSES, "until": until},
		as_dict=True,
	)


def _plan(lines, tables, stock):
	recipe_lines, sub_recipes, recipe_for_item, aliases = tables
	demand: dict[str, float] = {}
	for l in lines:
		demand[l.item_code] = demand.get(l.item_code, 0.0) + flt(l.stock_qty)
	return plan_day(fold_aliases(demand, aliases), recipe_for_item, sub_recipes, recipe_lines, stock, True)


def _on_order() -> dict[str, float]:
	"""Stock-UOM quantity on submitted-but-not-received and draft purchase orders."""
	rows = frappe.db.sql(
		"""
		select poi.item_code, sum(greatest(poi.stock_qty - poi.received_qty * poi.conversion_factor, 0)) as qty
		from `tabPurchase Order Item` poi
		join `tabPurchase Order` po on po.name = poi.parent
		where (po.docstatus = 1 and po.status in %(statuses)s) or po.docstatus = 0
		group by poi.item_code""",
		{"statuses": OPEN_PO_STATUSES},
		as_dict=True,
	)
	return {r.item_code: flt(r.qty) for r in rows}


def _item_info(codes) -> dict[str, dict]:
	if not codes:
		return {}
	company = frappe.defaults.get_user_default("Company") or frappe.defaults.get_global_default("company")
	info = {
		i.name: {"item_name": i.item_name, "stock_uom": i.stock_uom, "min_order_qty": flt(i.min_order_qty),
		         "order_multiple": flt(i.get("hk_order_multiple"))}
		for i in frappe.get_all("Item", filters={"name": ("in", list(codes))},
		                        fields=["name", "item_name", "stock_uom", "min_order_qty", "hk_order_multiple"])
	}
	for d in frappe.get_all("Item Default", filters={"parent": ("in", list(codes)), "parenttype": "Item", "company": company},
	                        fields=["parent", "default_supplier"]):
		if d.parent in info and d.default_supplier:
			info[d.parent]["supplier"] = d.default_supplier
	names = {s.name: s.supplier_name for s in frappe.get_all(
		"Supplier", filters={"name": ("in", list({i.get("supplier") for i in info.values() if i.get("supplier")}) or [""])},
		fields=["name", "supplier_name"])}
	for i in info.values():
		if i.get("supplier"):
			i["supplier_name"] = names.get(i["supplier"], i["supplier"])
	return info


@frappe.whitelist()
def today_board() -> dict:
	today = nowdate()
	out: dict = {"today": today, "tiles": [], "now": {}, "tasks": {"ordering": None, "receiving": None, "production": None}}
	can_so, can_po = _can("Sales Order"), _can("Purchase Order")

	# ---------------------------------------------------------------- orders out --
	lines = _open_lines(str(add_days(today, LOOKAHEAD_DAYS - 1))) if can_so else []
	due_now = [l for l in lines if str(l.delivery_date) <= today]
	if can_so:
		orders: dict[str, dict] = {}
		for l in due_now:
			o = orders.setdefault(l.sales_order, {"name": l.sales_order, "customer": l.customer_name or l.customer,
			                                      "late": str(l.delivery_date) < today, "date": str(l.delivery_date), "items": []})
			o["items"].append(f"{fmt_qty(l.qty, l.uom)} {l.item_name}")
		labels = {}
		if orders and frappe.db.exists("DocType", "Label Job"):
			for j in frappe.get_all("Label Job", filters={"sales_order": ("in", list(orders))},
			                        fields=["sales_order", "status", "label_count"]):
				c = labels.setdefault(j.sales_order, {"printed": 0, "waiting": 0, "check": 0})
				key = {"Printed": "printed", "Needs check": "check", "Queued": "waiting", "Printing": "waiting"}.get(j.status)
				if key:
					c[key] += cint(j.label_count)
		for name, o in orders.items():
			o["labels"] = labels.get(name)
		rows = sorted(orders.values(), key=lambda o: (not o["late"], o["customer"] or ""))
		out["now"]["orders"] = rows
		late = sum(1 for o in rows if o["late"])
		out["tiles"].append({"key": "orders", "label": _("Orders going out"), "value": len(rows),
		                     "detail": _("{0} late").format(late) if late else _("due today"),
		                     "tone": "danger" if late else "", "route": "List/Sales Order?status=To Deliver and Bill"})

	# ---------------------------------------------------------------- production --
	plans = []
	if can_so and _can("Recipe"):
		recipe_lines, sub_recipes, recipe_for_item = recipe_data()
		tables = (recipe_lines, sub_recipes, recipe_for_item, sku_aliases())
		stock = stock_on_hand()
		for i in range(LOOKAHEAD_DAYS):
			day = str(add_days(today, i))
			plans.append((day, _plan([l for l in lines if str(l.delivery_date) <= day], tables, stock)))

	if plans and _can("Recipe Production Log"):
		made: dict[str, float] = {}
		logs = frappe.get_all("Recipe Production Log", filters={"docstatus": 1, "posting_date": today}, pluck="name")
		for i in frappe.get_all("Recipe Production Log Item", filters={"parent": ("in", logs or [""]), "parenttype": "Recipe Production Log"},
		                        fields=["recipe", "units"]):
			made[i.recipe] = made.get(i.recipe, 0.0) + flt(i.units)
		today_plan = plans[0][1]
		rnames = {r.name: r for r in frappe.get_all("Recipe", fields=["name", "recipe_name", "yield_uom"])}
		prod = board.production_progress(today_plan["make"], made)
		for p in prod:
			r = rnames.get(p["recipe"]) or {}
			u = r.get("yield_uom") or "Nos"
			p.update(name=r.get("recipe_name") or p["item"], units_fmt=fmt_qty(p["units"], u),
			         made_fmt=fmt_qty(p["made"], u), left_fmt=fmt_qty(p["left"], u, True))
		out["now"]["production"] = prod
		done = sum(1 for p in prod if p["done"])
		out["tiles"].append({"key": "production", "label": _("To make today"),
		                     "value": f"{sum(p['batches'] for p in prod if not p['done']):g}",
		                     "detail": _("batches · {0} of {1} recipes done").format(done, len(prod)) if prod else _("nothing planned"),
		                     "route": "kitchen-production"})

		# tasks: what is left today, then batch preparations for the next days
		tasks = []
		for p in prod:
			if not p["done"]:
				tasks.append({"label": _("Make {0}").format(p["name"]),
				              "detail": _("{0} batches · {1} still to make").format(f"{p['batches']:g}", p["left_fmt"]),
				              "route": "kitchen-production", "tone": "warning", "badge": _("Today")})
		for c in today_plan["components"]:
			r = rnames.get(c["recipe"]) or {}
			tasks.append({"label": _("Prep fresh: {0}").format(r.get("recipe_name") or c["recipe"]),
			              "detail": fmt_qty(c["units"], r.get("yield_uom") or "", True),
			              "route": f"Form/Recipe/{c['recipe']}", "tone": "info", "badge": _("Today")})
		seen = set()
		for day, plan in plans:
			for pr in plan["preps"]:
				if pr["batches"] and pr["item"] not in seen:
					seen.add(pr["item"])
					r = rnames.get(pr.get("recipe")) or {}
					tasks.append({"label": _("Top up {0}").format(r.get("recipe_name") or pr["item"]),
					              "detail": _("{0} batches · short {1}").format(pr["batches"], fmt_qty(pr["short"], frappe.db.get_value("Item", pr["item"], "stock_uom"), True)),
					              "route": "kitchen-production", "tone": "warning" if day == today else "info",
					              "badge": _("Today") if day == today else frappe.utils.formatdate(day, "EEE d MMM")})
		if frappe.db.exists("DocType", "Label Job") and _can("Label Job"):
			check = frappe.db.count("Label Job", {"status": "Needs check"})
			failed = frappe.db.count("Label Job", {"status": "Failed"})
			if check:
				tasks.append({"label": _("Check product labels"), "detail": _("{0} label jobs waiting for a check").format(check),
				              "route": "List/Label Job?status=Needs check", "tone": "warning", "badge": _("Labels")})
			if failed:
				tasks.append({"label": _("Labels failed to print"), "detail": _("{0} jobs").format(failed),
				              "route": "List/Label Job?status=Failed", "tone": "danger", "badge": _("Labels")})
		out["tasks"]["production"] = tasks

	# ---------------------------------------------------------------- ordering --
	if plans and can_po:
		short = board.first_need(plans)
		info = _item_info({s["item"] for s in short})
		groups = board.to_order(short, _on_order(), info)
		for g in groups:
			for l in g["lines"]:
				l.update(short_fmt=fmt_qty(l["short"], l["uom"], True), qty_fmt=fmt_qty(l["qty"], l["uom"], True))
		out["tasks"]["ordering"] = {
			"groups": groups,
			"drafts": frappe.db.count("Purchase Order", {"docstatus": 0}),
			"can_create": _can("Purchase Order", "create"),
		}

	# ---------------------------------------------------------------- receiving --
	if can_po:
		pos = frappe.get_all(
			"Purchase Order",
			filters={"docstatus": 1, "status": ("in", OPEN_PO_STATUSES), "schedule_date": ("<=", str(add_days(today, 1)))},
			fields=["name", "supplier_name", "schedule_date", "grand_total", "per_received", "total_qty"],
			order_by="schedule_date asc, creation asc", limit=50,
		)
		counts = {}
		if pos:
			for r in frappe.db.sql("select parent, count(*) n from `tabPurchase Order Item` where parent in %(p)s group by parent",
			                       {"p": [p.name for p in pos]}, as_dict=True):
				counts[r.parent] = r.n
		incoming = [p for p in pos if str(p.schedule_date) <= today]
		out["now"]["deliveries"] = [
			{"name": p.name, "supplier": p.supplier_name, "date": str(p.schedule_date), "late": str(p.schedule_date) < today,
			 "value": flt(p.grand_total), "lines": counts.get(p.name, 0), "per_received": flt(p.per_received)}
			for p in incoming
		]
		late = sum(1 for p in incoming if str(p.schedule_date) < today)
		out["tiles"].append({"key": "deliveries", "label": _("Deliveries in"), "value": len(incoming),
		                     "detail": _("{0} late").format(late) if late else _("expected today"),
		                     "tone": "warning" if late else "", "route": "receive-delivery"})
		tasks = []
		for p in pos:
			is_late, is_today = str(p.schedule_date) < today, str(p.schedule_date) == today
			tasks.append({"label": _("Receive {0}").format(p.supplier_name),
			              "detail": _("{0} · {1} lines{2}").format(p.name, counts.get(p.name, 0),
			                                                       " · " + _("{0}% received").format(round(flt(p.per_received))) if flt(p.per_received) else ""),
			              "route": f"receive-delivery/{p.name}",
			              "tone": "danger" if is_late else ("warning" if is_today else "info"),
			              "badge": _("Late") if is_late else (_("Today") if is_today else _("Tomorrow"))})
		if _can("Purchase Receipt"):
			for r in frappe.get_all("Purchase Receipt",
			                        filters={"docstatus": 1, "hk_has_discrepancy": 1, "posting_date": (">=", add_days(today, -DISCREPANCY_DAYS))},
			                        fields=["name", "supplier_name"], order_by="posting_date desc", limit=5):
				tasks.append({"label": _("Check delivery from {0}").format(r.supplier_name),
				              "detail": _("{0} differs from the order").format(r.name),
				              "route": f"Form/Purchase Receipt/{r.name}", "tone": "danger", "badge": _("Check")})
		out["tasks"]["receiving"] = tasks

	# ---------------------------------------------------------------- team --
	if _can("Shift Assignment"):
		shifts = frappe.db.sql(
			"""select employee, employee_name, shift_type from `tabShift Assignment`
			where docstatus = 1 and status = 'Active' and start_date <= %(d)s and (end_date is null or end_date >= %(d)s)
			order by shift_type, employee_name""",
			{"d": today}, as_dict=True,
		)
		last = {}
		if shifts and _can("Employee Checkin"):
			for c in frappe.get_all("Employee Checkin",
			                        filters={"employee": ("in", [s.employee for s in shifts]), "time": (">=", today)},
			                        fields=["employee", "log_type", "time"], order_by="time asc"):
				last[c.employee] = c
		team = []
		for s in shifts:
			c = last.get(s.employee)
			state = "in" if c and c.log_type == "IN" else ("out" if c else "not_yet")
			team.append({"name": s.employee_name, "shift": s.shift_type, "state": state,
			             "since": frappe.utils.format_time(c.time, "HH:mm") if c else ""})
		out["now"]["team"] = team
		here = sum(1 for t in team if t["state"] == "in")
		out["tiles"].append({"key": "team", "label": _("On shift"), "value": len(team),
		                     "detail": _("{0} clocked in").format(here), "route": "team"})
	return out


@frappe.whitelist(methods=["POST"])
def create_purchase_order(supplier: str, items: str | list, schedule_date: str | None = None) -> str:
	"""A draft purchase order for the ingredients the board says to order. It is
	only a draft: someone checks it and submits it as usual."""
	if not _can("Purchase Order", "create"):
		frappe.throw(_("You can't create purchase orders."), frappe.PermissionError)
	if isinstance(items, str):
		items = json.loads(items or "[]")
	rows = [{"item_code": i["item"], "qty": flt(i["qty"])} for i in items if flt(i.get("qty")) > 0]
	if not rows:
		frappe.throw(_("Nothing to order."))
	day = getdate(schedule_date) if schedule_date else getdate(add_days(nowdate(), 1))
	if day < getdate(nowdate()):
		day = getdate(nowdate())
	po = frappe.new_doc("Purchase Order")
	po.supplier = supplier
	po.schedule_date = day
	po.company = frappe.defaults.get_user_default("Company") or frappe.defaults.get_global_default("company")
	for r in rows:
		po.append("items", {**r, "schedule_date": day})
	po.set_missing_values()
	po.insert()
	return po.name
