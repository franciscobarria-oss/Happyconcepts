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
