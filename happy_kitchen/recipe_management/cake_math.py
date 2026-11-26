"""Pure maths for the Cake Costing screen: size to volume and slices, line and total costs,
and reading the ingredient guesses a model returns. No frappe import."""
from __future__ import annotations

import math

SHAPES = ("Round", "Square", "Loaf")


def flt(v, default=0.0) -> float:
	try:
		return float(v)
	except (TypeError, ValueError):
		return default


def volume_cm3(shape: str, height, width, length=None) -> float:
	"""Round: width is the diameter. Square: width x width. Loaf: width x length."""
	h, w = flt(height), flt(width)
	if h <= 0 or w <= 0:
		return 0.0
	if shape == "Round":
		return math.pi * (w / 2) ** 2 * h
	if shape == "Loaf":
		return w * (flt(length) or w) * h
	return w * w * h


def suggest_slices(weight_g, per_slice_g=100) -> int:
	"""A slice of about 100 g by default, at least 1."""
	w = flt(weight_g)
	return max(1, round(w / per_slice_g)) if w > 0 else 0


def line_cost(qty_g, unit_cost) -> float:
	return round(flt(qty_g) * flt(unit_cost), 4)


def totals(lines: list[dict], labour=0, packaging=0, slices=0, weight_g=0) -> dict:
	"""lines: dicts with qty_g and unit_cost (None = price unknown). Unpriced lines are listed, not counted."""
	ingredients = sum(line_cost(r.get("qty_g"), r["unit_cost"]) for r in lines if r.get("unit_cost") is not None)
	unpriced = [r.get("item_name") or r.get("item") or "?" for r in lines if r.get("unit_cost") is None]
	total = ingredients + flt(labour) + flt(packaging)
	s, w = flt(slices), flt(weight_g)
	return {
		"ingredient_cost": round(ingredients, 4),
		"total_cost": round(total, 4),
		"cost_per_slice": round(total / s, 4) if s > 0 else 0.0,
		"cost_per_100g": round(total / w * 100, 4) if w > 0 else 0.0,
		"unpriced": unpriced,
	}


def ingredient_weight_gap(lines: list[dict], weight_g) -> float | None:
	"""Percent the listed grams differ from the cake's weight (baking loses water, so some gap is normal)."""
	w = flt(weight_g)
	if w <= 0:
		return None
	return round((sum(flt(r.get("qty_g")) for r in lines) - w) / w * 100, 1)


def parse_guess(data) -> list[dict]:
	"""Clean the model's JSON: [{name, grams}] with a positive weight, at most 25 lines."""
	out = []
	for r in ((data or {}).get("ingredients") or [])[:25]:
		name = " ".join(str(r.get("name") or "").split())
		g = flt(r.get("grams"))
		if name and g > 0:
			out.append({"name": name, "grams": round(g, 1)})
	return out


# Pack units -> grams (ml counts as 1 g, as in the costing sheet). "pcs" is counted, not weighed.
UNITS = {"g": 1.0, "kg": 1000.0, "lb": 453.592, "oz": 28.3495, "ml": 1.0, "L": 1000.0, "pcs": 0.0}


def pack_cost(price, pack_size, pack_unit, qty, qty_unit="g", piece_g=0) -> dict:
	"""Bulk price + pack size -> unit cost (per g, or per piece for pcs), line cost and weight in g.
	Returns {"error": ...} when the units do not fit or the pack size is missing."""
	qty_pcs, pack_pcs = qty_unit == "pcs", pack_unit == "pcs"
	if qty_pcs != pack_pcs:
		return {"error": "Units differ (pcs vs weight)"}
	base = flt(pack_size) if pack_pcs else flt(pack_size) * UNITS.get(pack_unit, 0.0)
	if base <= 0:
		return {"error": "No pack size"}
	unit = flt(price) / base
	q = flt(qty)
	return {"unit_cost": unit, "line_cost": line_cost(q, unit), "weight_g": q * flt(piece_g) if qty_pcs else q}


def per_piece(total, recipe_weight_g, piece_weight_g, slices=0) -> tuple[float, float]:
	"""(pieces per batch, cost per piece). Piece weight wins; else the slice count."""
	pw, w = flt(piece_weight_g), flt(recipe_weight_g)
	n = w / pw if pw > 0 and w > 0 else flt(slices)
	return (round(n, 2), round(flt(total) / n, 4) if n > 0 else 0.0)
