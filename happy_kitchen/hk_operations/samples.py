"""Samples sent out: product that leaves the kitchen on no order (to a prospect or as a gift).
Pure rules, unit-tested in tests/test_samples.py.

- A sample counts in what must be made that day, like an ordered line (stock units).
- The Daily Sales Overview lists them in their own box, one row per item with the quantity and who got it.
"""

from __future__ import annotations

EPS = 1e-9


def _f(v) -> float:
	try:
		return float(v or 0)
	except (TypeError, ValueError):
		return 0.0


def add_to_demand(demand: dict[str, float], samples: list[dict]) -> dict[str, float]:
	"""demand: {item: stock qty}. samples: rows with item, stock_qty. A new dict; the input is not changed."""
	out = dict(demand)
	for s in samples:
		q = _f(s.get("stock_qty"))
		if q > EPS and s.get("item"):
			out[s["item"]] = out.get(s["item"], 0.0) + q
	return out


def box_rows(samples: list[dict]) -> list[dict]:
	"""One row per item for the sheet box: {item, item_name, item_name_zh, qty, uom, to}.
	'to' lists who received it ("K11, Hotel ABC"), each name once, in the order given."""
	rows: dict[tuple, dict] = {}
	for s in samples:
		q = _f(s.get("qty"))
		if q <= EPS or not s.get("item"):
			continue
		key = (s["item"], s.get("uom") or "")
		r = rows.setdefault(key, {"item": s["item"], "item_name": s.get("item_name") or s["item"],
		                          "item_name_zh": s.get("item_name_zh") or "", "qty": 0.0,
		                          "uom": s.get("uom") or "", "to": []})
		r["qty"] += q
		who = (s.get("recipient") or s.get("customer_name") or "").strip()
		if who and who not in r["to"]:
			r["to"].append(who)
	return [{**r, "to": ", ".join(r["to"])} for r in sorted(rows.values(), key=lambda r: r["item"])]
