"""Pure helpers for the Today board (today_board.py); unit-tested in tests/test_board.py."""

from __future__ import annotations

import math

EPS = 1e-9


def order_qty(short: float, min_qty: float = 0, multiple: float = 0) -> float:
	"""What to order to cover `short`: at least the supplier's minimum, rounded up
	to the order multiple (eggs by 12). Stock UOM throughout."""
	if short <= EPS:
		return 0.0
	qty = max(short, min_qty or 0)
	if multiple and multiple > 0:
		qty = math.ceil(qty / multiple - EPS) * multiple
	return float(qty)


def to_order(shortages: list[dict], on_order: dict[str, float], items: dict[str, dict]) -> list[dict]:
	"""Ingredients short for the coming orders, after what is already ordered,
	grouped by default supplier, most urgent first.

	shortages: [{"item", "short", "need_by"}]  (stock UOM; need_by = first day it's needed)
	on_order:  {item: qty on open or draft purchase orders, not yet received}
	items:     {item: {"item_name", "stock_uom", "supplier", "supplier_name", "min_order_qty", "order_multiple"}}
	"""
	groups: dict[str, dict] = {}
	for s in shortages:
		left = s["short"] - (on_order.get(s["item"]) or 0)
		if left <= EPS:
			continue
		info = items.get(s["item"]) or {}
		supplier = info.get("supplier") or ""
		g = groups.setdefault(supplier, {
			"supplier": supplier, "supplier_name": info.get("supplier_name") or supplier, "need_by": s["need_by"], "lines": [],
		})
		g["need_by"] = min(g["need_by"], s["need_by"])
		g["lines"].append({
			"item": s["item"], "item_name": info.get("item_name") or s["item"], "uom": info.get("stock_uom") or "",
			"short": left, "on_order": on_order.get(s["item"]) or 0, "need_by": s["need_by"],
			"qty": order_qty(left, info.get("min_order_qty") or 0, info.get("order_multiple") or 0),
		})
	for g in groups.values():
		g["lines"].sort(key=lambda l: (l["need_by"], l["item_name"].lower()))
	# suppliers with the earliest need first; ingredients without a supplier last
	return sorted(groups.values(), key=lambda g: (not g["supplier"], g["need_by"], g["supplier_name"].lower()))


def first_need(day_plans: list[tuple[str, dict]]) -> list[dict]:
	"""Merge per-day ingredient shortages into one list with the first day each is
	short. day_plans: [(day, plan)] where plan has cumulative "ingredients" rows
	(the plan for all orders up to and including that day), oldest day first."""
	out: dict[str, dict] = {}
	for day, plan in day_plans:
		for r in plan.get("ingredients", []):
			if r["short"] <= EPS:
				continue
			row = out.setdefault(r["item"], {"item": r["item"], "need_by": day, "short": 0.0})
			row["short"] = max(row["short"], r["short"])  # cumulative plans: the last day holds the total
	return sorted(out.values(), key=lambda r: (r["need_by"], r["item"]))


def production_progress(make: list[dict], made_today: dict[str, float]) -> list[dict]:
	"""Today's production plan with what has been logged so far, per recipe."""
	rows = []
	for m in make:
		if not m.get("batches") and not made_today.get(m["recipe"]):
			continue
		made = made_today.get(m["recipe"], 0.0)
		target = m.get("units") or 0.0
		rows.append({**m, "made": made, "left": max(0.0, target - made), "done": target > 0 and made >= target - EPS})
	rows.sort(key=lambda r: (r["done"], -(r.get("batches") or 0)))
	return rows


# the dashboard's KPI that fills in the breakdown of a board tile
KPI_TO_TILE = {"orders": "orders", "produced": "production", "deliveries": "deliveries"}
DRAFT_PO_ROUTE = "List/Purchase Order?docstatus=0"


def merge_today(dash: dict, brd: dict) -> dict:
	"""One Today home from the dashboard (KPIs with breakdowns, orders by day,
	waiting on you) and the board (tiles, happening today, tasks).

	- Board tiles come first; a dashboard KPI for the same thing adds its
	  breakdown to that tile, the others (open POs, waste) follow as tiles.
	- "Waiting on you" keeps approvals, flagged deliveries and draft POs, so
	  the task columns drop the same rows instead of showing them twice.
	"""
	tiles = [dict(t, details=[]) for t in brd.get("tiles") or []]
	by_key = {t["key"]: t for t in tiles}
	for k in dash.get("kpis") or []:
		target = by_key.get(KPI_TO_TILE.get(k["key"], ""))
		if target is not None:
			target["details"] = k.get("details") or []
			continue
		if k["key"] in KPI_TO_TILE:
			continue  # its tile isn't shown (no permission): skip the duplicate
		value = f"{k['value']} {k['unit']}".strip() if k.get("unit") else k["value"]
		tiles.append({"key": k["key"], "label": k["label"], "value": value, "detail": k.get("delta") or "",
		              "tone": k.get("tone") or "", "route": k.get("route") or "", "details": k.get("details") or []})

	waiting = list(dash.get("waiting") or [])
	waiting_routes = {w.get("route") for w in waiting}
	tasks = dict(brd.get("tasks") or {})
	for key in ("receiving", "production"):
		if tasks.get(key) is not None:
			tasks[key] = [t for t in tasks[key] if t.get("route") not in waiting_routes]
	if tasks.get("ordering") and DRAFT_PO_ROUTE in waiting_routes:
		tasks["ordering"] = dict(tasks["ordering"], drafts=0)

	return {
		"today": brd.get("today") or dash.get("today"),
		"tiles": tiles,
		"now": brd.get("now") or {},
		"orders": dash.get("orders"),
		"orders_total": dash.get("orders_total") or 0,
		"waiting": waiting,
		"tasks": tasks,
	}


def week_load(days: list[str], orders: dict[str, dict], deliveries: dict[str, dict]) -> list[dict]:
	"""How busy each day is. `orders` / `deliveries` map a date to
	{"count": n, "amount": value}. A day's load is orders going out plus
	deliveries coming in; the level is relative to the week's busiest day
	(busy from 75 % of the peak, quiet up to 25 %; a flat week is never busy)."""
	rows = []
	for d in days:
		o, p = orders.get(d) or {}, deliveries.get(d) or {}
		oc, pc = int(o.get("count") or 0), int(p.get("count") or 0)
		rows.append({"date": d, "orders": oc, "order_amount": float(o.get("amount") or 0),
		             "deliveries": pc, "load": oc + pc})
	peak = max((r["load"] for r in rows), default=0)
	for r in rows:
		share = r["load"] / peak if peak else 0
		r["share"] = round(share, 3)
		r["level"] = "busy" if peak >= 3 and share >= 0.75 else "quiet" if share <= 0.25 else "normal"
	return rows
