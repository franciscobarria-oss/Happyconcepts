"""Dashboard part of the Today home (today.py merges it with today_board.py):
KPIs with their breakdowns, orders by day (late / today / tomorrow / day after)
and "waiting on you". Each part is only included when the user can read that
doctype."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, nowdate

OPEN_PO_STATUSES = ("To Receive and Bill", "To Receive")
OPEN_SO_STATUSES = ("To Deliver and Bill", "To Deliver")
ORDER_ROWS = 10  # per day on the Orders card (late / today / tomorrow / day after)
ORDER_ITEMS = 4  # product lines shown under each order in the detailed view
DETAIL_ROWS = 4  # breakdown lines under each KPI tile in the detailed view
RECENT_DAYS = 7
DISCREPANCY_DAYS = 14


def week_start(day) -> str:
	"""Monday of the week containing `day` (ISO weeks, as the kitchen roster)."""
	d = getdate(day)
	return str(add_days(d, -d.weekday()))


def top(totals: dict, n: int = DETAIL_ROWS) -> list[tuple]:
	"""Largest values first: {"Flour": 3, "Sugar": 5} -> [("Sugar", 5), ("Flour", 3)]."""
	return sorted(totals.items(), key=lambda kv: (-kv[1], str(kv[0])))[:n]


def _money(v) -> str:
	return f"HK$ {flt(v):,.0f}"


def _can(doctype: str) -> bool:
	return bool(frappe.db.exists("DocType", doctype)) and frappe.has_permission(doctype, "read")


@frappe.whitelist()
def kitchen_today() -> dict:
	today = nowdate()
	out: dict = {
		"today": today, "kpis": [], "production": None, "production_totals": [], "production_logs": 0,
		"orders": None, "orders_total": 0, "waiting": [],
	}

	if _can("Recipe Production Log"):
		logs = frappe.get_all(
			"Recipe Production Log",
			filters={"docstatus": 1, "posting_date": (">=", add_days(today, -(RECENT_DAYS - 1)))},
			fields=["name", "posting_date", "total_cost", "owner"],
			order_by="posting_date desc, creation desc",
			limit=50,
		)
		items = (
			frappe.get_all(
				"Recipe Production Log Item",
				filters={"parent": ("in", [l.name for l in logs]), "parenttype": "Recipe Production Log"},
				fields=["parent", "recipe", "recipe_name", "batches", "units"],
				order_by="idx asc",
			)
			if logs
			else []
		)
		todays = [l for l in logs if str(l.posting_date) == today]
		todays_names = {l.name for l in todays}
		today_batches = sum(flt(i.batches) for i in items if i.parent in todays_names)
		made_today: dict = {}
		for i in items:
			if i.parent in todays_names:
				made_today[i.recipe_name or i.recipe] = made_today.get(i.recipe_name or i.recipe, 0) + flt(i.batches)
		out["kpis"].append(
			{
				"key": "produced",
				"label": _("Produced today"),
				"value": f"{today_batches:g}",
				"unit": _("batches"),
				"delta": _("{0} logs · HK$ {1} ingredients").format(
					len(todays), f"{sum(flt(l.total_cost) for l in todays):,.0f}"
				),
				"route": "kitchen-production",
				"details": [{"label": r, "value": _("{0} batches").format(f"{b:g}")} for r, b in top(made_today)],
			}
		)
		by_log = {}
		for i in items:
			by_log.setdefault(i.parent, []).append(i)
		rows = []
		for l in logs[:8]:
			for i in by_log.get(l.name, [])[:4]:
				rows.append(
					{
						"log": l.name,
						"date": str(l.posting_date),
						"recipe": i.recipe,
						"recipe_name": i.recipe_name,
						"batches": flt(i.batches),
						"units": flt(i.units),
						"by": frappe.utils.get_fullname(l.owner),
					}
				)
		out["production"] = rows[:12]
		# the simple view: what was made this week, per recipe
		totals: dict = {}
		for i in items:
			t = totals.setdefault(i.recipe, {"recipe": i.recipe, "recipe_name": i.recipe_name, "batches": 0.0, "units": 0.0})
			t["batches"] += flt(i.batches)
			t["units"] += flt(i.units)
		out["production_totals"] = sorted(totals.values(), key=lambda t: (-t["batches"], t["recipe_name"] or ""))[:6]
		out["production_logs"] = len(logs)

	if _can("Sales Order"):
		orders = frappe.get_all(
			"Sales Order",
			filters={"docstatus": 1, "status": ("in", OPEN_SO_STATUSES)},
			fields=["name", "customer", "customer_name", "delivery_date", "grand_total", "per_delivered", "status"],
			order_by="delivery_date asc, creation asc",
			limit=200,
		)
		late = [o for o in orders if o.delivery_date and str(o.delivery_date) < today]
		due_today = [o for o in orders if o.delivery_date and str(o.delivery_date) == today]
		by_customer: dict = {}
		for o in orders:
			by_customer[o.customer_name or o.customer] = by_customer.get(o.customer_name or o.customer, 0) + flt(o.grand_total)
		out["kpis"].insert(
			0,
			{
				"key": "orders",
				"label": _("Orders to deliver"),
				"value": str(len(orders)),
				"unit": "",
				"delta": _("{0} due today · {1} late").format(len(due_today), len(late)) if orders else _("No open orders"),
				"route": "List/Sales Order?status=To Deliver and Bill",
				"tone": "warning" if late else "",
				"details": [{"label": c, "value": _money(v)} for c, v in top(by_customer)],
			},
		)
		def row(o):
			return {
				"name": o.name,
				"customer": o.customer_name or o.customer,
				"delivery_date": str(o.delivery_date),
				"grand_total": flt(o.grand_total),
				"per_delivered": flt(o.per_delivered),
				"items": lines.get(o.name, [])[:ORDER_ITEMS],
				"more_items": max(0, len(lines.get(o.name, [])) - ORDER_ITEMS),
			}

		# late (only when there are any), then today, tomorrow, the day after
		days = [("late", _("Late"), None, late)] if late else []
		for i, (key, label) in enumerate(
			[("today", _("Today")), ("tomorrow", _("Tomorrow")), ("day_after", _("Day after tomorrow"))]
		):
			day = str(add_days(today, i))
			days.append((key, label, day, [o for o in orders if o.delivery_date and str(o.delivery_date) == day]))
		# what is still to deliver on the orders shown (detailed view)
		shown = [o.name for _k, _l, _d, rows in days for o in rows[:ORDER_ROWS]]
		lines: dict = {}
		if shown:
			for l in frappe.get_all(
				"Sales Order Item",
				filters={"parent": ("in", shown), "parenttype": "Sales Order"},
				fields=["parent", "item_name", "qty", "delivered_qty", "uom"],
				order_by="idx asc",
			):
				left = flt(l.qty) - flt(l.delivered_qty)
				if left > 0:
					lines.setdefault(l.parent, []).append({"item_name": l.item_name, "qty": left, "uom": l.uom})
		out["orders"] = [
			{
				"key": key, "label": label, "date": day, "count": len(rows),
				"amount": sum(flt(o.grand_total) for o in rows),
				"orders": [row(o) for o in rows[:ORDER_ROWS]],
			}
			for key, label, day, rows in days
		]
		out["orders_total"] = len(orders)

	if _can("Purchase Order"):
		open_pos = frappe.get_all(
			"Purchase Order",
			filters={"docstatus": 1, "status": ("in", OPEN_PO_STATUSES)},
			fields=["name", "supplier_name", "schedule_date", "grand_total", "per_received"],
			order_by="schedule_date asc",
			limit=200,
		)
		due = [p for p in open_pos if p.schedule_date and str(p.schedule_date) <= today]

		def per_supplier(pos):
			totals: dict = {}
			for p in pos:
				totals[p.supplier_name] = totals.get(p.supplier_name, 0) + flt(p.grand_total)
			return [{"label": s, "value": _money(v)} for s, v in top(totals)]
		out["kpis"].append(
			{
				"key": "deliveries",
				"label": _("Deliveries due"),
				"value": str(len(due)),
				"unit": "",
				"delta": ", ".join(sorted({p.supplier_name for p in due})[:3]) or _("Nothing due today"),
				"route": "receive-delivery",
				"tone": "warning" if any(str(p.schedule_date) < today for p in due) else "",
				"details": per_supplier(due),
			}
		)
		out["kpis"].append(
			{
				"key": "open_po",
				"label": _("Open purchase orders"),
				"value": f"HK$ {sum(flt(p.grand_total) for p in open_pos):,.0f}",
				"unit": "",
				"delta": _("{0} orders to receive").format(len(open_pos)),
				"route": "List/Purchase Order?status=To Receive and Bill",
				"details": per_supplier(open_pos),
			}
		)
		drafts = frappe.db.count("Purchase Order", {"docstatus": 0})
		if drafts:
			out["waiting"].append(
				{"label": _("Purchase orders to send"), "detail": _("{0} drafts").format(drafts),
				 "route": "List/Purchase Order?docstatus=0", "tone": "info"}
			)

	if _can("Wastage Log"):
		monday = week_start(today)
		waste = frappe.get_all(
			"Wastage Log",
			filters={"docstatus": 1, "posting_date": (">=", monday)},
			fields=["name", "total_cost"],
			limit=500,
		)
		by_reason: dict = {}
		if waste:
			for w in frappe.get_all(
				"Wastage Log Item",
				filters={"parent": ("in", [w.name for w in waste]), "parenttype": "Wastage Log"},
				fields=["reason", "amount"],
			):
				by_reason[w.reason or _("No reason")] = by_reason.get(w.reason or _("No reason"), 0) + flt(w.amount)
		out["kpis"].append(
			{
				"key": "waste",
				"label": _("Waste this week"),
				"value": f"HK$ {sum(flt(w.total_cost) for w in waste):,.0f}",
				"unit": "",
				"delta": _("{0} logs since Monday").format(len(waste)),
				"route": "List/Wastage Log",
				"details": [{"label": r, "value": _money(v)} for r, v in top(by_reason)],
			}
		)

	if _can("Stock Take"):
		pending = frappe.get_all(
			"Stock Take",
			filters={"status": "Submitted"},
			fields=["name", "stock_take_sheet", "submitted_by", "posting_date"],
			order_by="posting_date asc",
			limit=10,
		)
		approver = "Stock Take Approver" in frappe.get_roles()
		for s in pending:
			mine = s.submitted_by == frappe.session.user
			out["waiting"].append(
				{
					"label": _("Approve stock count {0}").format(s.name),
					"detail": _("{0}, counted {1}").format(
						s.stock_take_sheet, frappe.utils.formatdate(s.posting_date)
					)
					+ ("" if approver and not mine else " · " + _("needs another Stock Take Approver")),
					"route": f"Form/Stock Take/{s.name}",
					"tone": "warning",
				}
			)

	if _can("Purchase Receipt"):
		flagged = frappe.get_all(
			"Purchase Receipt",
			filters={
				"docstatus": 1,
				"hk_has_discrepancy": 1,
				"posting_date": (">=", add_days(today, -DISCREPANCY_DAYS)),
			},
			fields=["name", "supplier_name", "posting_date"],
			order_by="posting_date desc",
			limit=5,
		)
		for r in flagged:
			out["waiting"].append(
				{
					"label": _("Check delivery from {0}").format(r.supplier_name),
					"detail": _("{0} differs from the order").format(r.name),
					"route": f"Form/Purchase Receipt/{r.name}",
					"tone": "danger",
				}
			)

	if _can("Leave Application"):
		leave = frappe.db.count("Leave Application", {"docstatus": 0, "status": "Open"})
		if leave:
			out["waiting"].append(
				{"label": _("Time off to approve"), "detail": _("{0} requests").format(leave),
				 "route": "List/Leave Application?status=Open", "tone": "info"}
			)

	if _can("Overtime Entry"):
		ot = frappe.db.count("Overtime Entry", {"docstatus": 0})
		if ot:
			out["waiting"].append(
				{"label": _("Overtime to approve"), "detail": _("{0} entries").format(ot),
				 "route": "List/Overtime Entry?docstatus=0", "tone": "info"}
			)

	return out
