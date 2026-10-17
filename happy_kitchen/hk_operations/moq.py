"""Pure purchasing maths (no Frappe import): order multiples, supplier minimum order amount,
ING-xxx item numbering and Kg -> Gram price conversion. purchasing.py and the forms call into here."""

from __future__ import annotations

import math
import re

EPS = 1e-6
ING_RE = re.compile(r"^ING-(\d+)$")


def total_stock_qty(lines):
	"""Sum stock quantities per item. lines: iterable of dicts with item_code and stock_qty
	(or qty and conversion_factor)."""
	totals = {}
	for d in lines:
		code = d.get("item_code")
		if not code:
			continue
		qty = d.get("stock_qty")
		if qty is None:
			qty = (d.get("qty") or 0) * (d.get("conversion_factor") or 1)
		totals[code] = totals.get(code, 0.0) + float(qty or 0)
	return totals


def multiple_suggestion(qty, multiple):
	"""None if qty is a whole multiple of `multiple` (or no multiple is set), else the nearest
	valid quantities (lower, upper); lower is None when it would be 0."""
	m = float(multiple or 0)
	if m <= 0:
		return None
	n = float(qty) / m
	if abs(n - round(n)) <= EPS:
		return None
	lo, hi = math.floor(n) * m, math.ceil(n) * m
	return (lo if lo > 0 else None, hi)


def multiple_errors(totals, items):
	"""totals: {item_code: stock qty}; items: {item_code: {"item_name", "stock_uom", "hk_order_multiple"}}.
	Returns one dict per item whose ordered quantity isn't a multiple."""
	errors = []
	for code, qty in totals.items():
		it = items.get(code) or {}
		s = multiple_suggestion(qty, it.get("hk_order_multiple"))
		if s:
			errors.append({
				"item_code": code, "item_name": it.get("item_name") or code, "stock_uom": it.get("stock_uom") or "",
				"qty": qty, "multiple": float(it["hk_order_multiple"]), "lower": s[0], "upper": s[1],
			})
	return errors


def minimum_shortfall(total, minimum):
	"""Amount still needed to reach the supplier's minimum order (0 = none or reached)."""
	m = float(minimum or 0)
	t = float(total or 0)
	return round(m - t, 2) if m > 0 and t + EPS < m else 0.0


def next_item_code(existing_codes, width=3):
	"""Next ING-xxx after the highest existing one (gaps are not reused)."""
	top = 0
	for c in existing_codes:
		m = ING_RE.match(c or "")
		if m:
			top = max(top, int(m.group(1)))
	return f"ING-{top + 1:0{width}d}"


def to_stock_units(price, uom, qtys=()):
	"""Prices and quantities typed per Kg are stored per Gram. Returns (stock_uom, price, [qtys])."""
	if uom == "Kg":
		return "Gram", float(price) / 1000, [float(q or 0) * 1000 for q in qtys]
	if uom not in ("Gram", "Nos"):
		raise ValueError(f"Unsupported UOM {uom!r}: use Gram, Kg or Nos")
	return uom, float(price), [float(q or 0) for q in qtys]
