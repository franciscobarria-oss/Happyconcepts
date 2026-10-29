"""Sales dashboard maths (no Frappe import, so it is unit-tested).

Input is one row per Sales Order line: {date, item_code, item_name, uom, qty, amount, order}.
`date` is the delivery date (the Xero import dates orders by delivery). Output feeds the
"HK Sales" block on the Selling workspace: totals, SKUs sold, units per week, and units by
weekday over the last 4 weeks of the range (to spot the busiest days)."""

from __future__ import annotations

from datetime import date, timedelta

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
RECENT_WEEKS = 4


def as_date(value) -> date:
	if isinstance(value, date):
		return value
	return date.fromisoformat(str(value)[:10])


def week_start(d: date) -> date:
	"""Monday of the week that holds d."""
	return d - timedelta(days=d.weekday())


def skus_sold(lines: list[dict]) -> list[dict]:
	"""One row per item and unit, most units first: qty, amount, number of orders, share of units."""
	by_item: dict[tuple, dict] = {}
	for ln in lines:
		key = (ln["item_code"], ln.get("uom") or "")
		row = by_item.setdefault(key, {
			"item_code": ln["item_code"], "item_name": ln.get("item_name") or ln["item_code"],
			"uom": ln.get("uom") or "", "qty": 0.0, "amount": 0.0, "orders": set(),
		})
		row["qty"] += float(ln.get("qty") or 0)
		row["amount"] += float(ln.get("amount") or 0)
		row["orders"].add(ln.get("order"))
	total = sum(r["qty"] for r in by_item.values()) or 1
	rows = []
	for r in by_item.values():
		r["orders"] = len(r["orders"])
		r["share"] = r["qty"] / total
		rows.append(r)
	rows.sort(key=lambda r: (-r["qty"], r["item_code"]))
	return rows


def weekly(lines: list[dict], from_date, to_date) -> list[dict]:
	"""Units, orders and amount per Monday-start week, every week of the range (empty weeks are 0)."""
	start, end = week_start(as_date(from_date)), week_start(as_date(to_date))
	weeks: dict[date, dict] = {}
	d = start
	while d <= end:
		weeks[d] = {"week": d.isoformat(), "qty": 0.0, "amount": 0.0, "orders": set()}
		d += timedelta(days=7)
	for ln in lines:
		w = weeks.get(week_start(as_date(ln["date"])))
		if w is None:
			continue
		w["qty"] += float(ln.get("qty") or 0)
		w["amount"] += float(ln.get("amount") or 0)
		w["orders"].add(ln.get("order"))
	out = []
	for w in weeks.values():
		w["orders"] = len(w["orders"])
		out.append(w)
	return out


def recent_weekdays(lines: list[dict], to_date, weeks: int = RECENT_WEEKS) -> dict | None:
	"""Units by weekday for the last `weeks` Monday-start weeks of the range.

	The window ends with the week of the latest delivery on or before to_date, so an old import
	or a range that ends in a quiet week still shows its last busy weeks. Returns the grid
	(one row per week, Mon..Sun), the total and average per weekday, and the busiest weekday
	and single busiest date."""
	end = as_date(to_date)
	dated = [as_date(ln["date"]) for ln in lines]
	dated = [d for d in dated if d <= end]
	if not dated:
		return None
	last_week = week_start(max(dated))
	first_week = last_week - timedelta(days=7 * (weeks - 1))
	grid = {first_week + timedelta(days=7 * i): [0.0] * 7 for i in range(weeks)}
	per_day: dict[date, float] = {}
	for ln in lines:
		d = as_date(ln["date"])
		row = grid.get(week_start(d))
		if row is None or d > end:
			continue
		q = float(ln.get("qty") or 0)
		row[d.weekday()] += q
		per_day[d] = per_day.get(d, 0.0) + q
	totals = [sum(row[i] for row in grid.values()) for i in range(7)]
	busiest = max(range(7), key=lambda i: (totals[i], -i))
	top_day = max(per_day.items(), key=lambda kv: (kv[1], kv[0])) if per_day else None
	return {
		"from": first_week.isoformat(),
		"to": (last_week + timedelta(days=6)).isoformat(),
		"weekdays": list(WEEKDAYS),
		"weeks": [{"week": w.isoformat(), "days": row, "qty": sum(row)} for w, row in grid.items()],
		"totals": totals,
		"average": [t / weeks for t in totals],
		"busiest_weekday": WEEKDAYS[busiest] if totals[busiest] else None,
		"busiest_date": {"date": top_day[0].isoformat(), "qty": top_day[1]} if top_day and top_day[1] else None,
	}


def summarise(lines: list[dict], from_date, to_date) -> dict:
	"""Everything the dashboard draws, from the order lines inside [from_date, to_date]."""
	lo, hi = as_date(from_date), as_date(to_date)
	inside = [ln for ln in lines if lo <= as_date(ln["date"]) <= hi]
	skus = skus_sold(inside)
	return {
		"totals": {
			"qty": sum(r["qty"] for r in skus),
			"amount": sum(r["amount"] for r in skus),
			"orders": len({ln.get("order") for ln in inside}),
			"skus": len({r["item_code"] for r in skus}),
		},
		"skus": skus,
		"weeks": weekly(inside, lo, hi),
		"recent": recent_weekdays(inside, hi),
	}
