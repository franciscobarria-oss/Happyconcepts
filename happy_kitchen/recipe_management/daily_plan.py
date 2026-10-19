"""What the kitchen has to make for a day's orders (pure, unit-tested in
tests/test_daily_plan.py). The A4 production sheet (production_sheet.py)
feeds it the day's sales orders, the recipes and stock on hand.

Rules (the same as Inventory Variance and the Production screen):
- A Finished Product is made in whole batches: units ordered minus finished
  stock on hand (optional), rounded up to the recipe's batch yield.
- A Recipe Component is made fresh as part of the product: it is listed under
  "prep with the run" and its own ingredients are added.
- A Batch Preparation (dough, bases) comes out of stock: what the runs need is
  compared with stock on hand and any shortfall becomes a suggested batch run,
  whose ingredients are added too (preps inside preps are followed).
- Anything ordered that has no recipe is picked from stock.
"""

from __future__ import annotations

import math

from happy_kitchen.recipe_management.variance import BATCH_PREPARATION, RECIPE_COMPONENT, VarianceError, flt

EPS = 1e-9
MAX_DEPTH = 10


def whole_batches(units: float, batch_yield: float) -> int:
	"""Batches needed to make at least `units` (0 when nothing is needed)."""
	units, batch_yield = flt(units), flt(batch_yield) or 1.0
	if units <= EPS:
		return 0
	return int(math.ceil(units / batch_yield - EPS))


def _expand(recipe, batches, recipe_lines, sub_recipes, raw, preps, components, path=()):
	"""Add one recipe run's lines: raw ingredients to `raw`, batch preps to
	`preps` (demand), components expanded in place and noted in `components`."""
	if recipe in path:
		raise VarianceError(f"Recipe loop: {' -> '.join(path + (recipe,))}")
	if len(path) >= MAX_DEPTH:
		raise VarianceError(f"Sub-recipes nested deeper than {MAX_DEPTH} levels at {recipe}")
	for line in recipe_lines.get(recipe, []):
		qty = flt(line.get("gross_qty") or line.get("base_qty")) * flt(batches)
		if qty <= EPS:
			continue
		item = line["item"]
		sub = sub_recipes.get(item)
		if sub and sub.get("recipe") != recipe and sub.get("recipe_type") == RECIPE_COMPONENT:
			components[sub["recipe"]] = components.get(sub["recipe"], 0.0) + qty
			_expand(sub["recipe"], qty / (flt(sub.get("batch_yield")) or 1.0), recipe_lines, sub_recipes,
			        raw, preps, components, path + (recipe,))
		elif sub and sub.get("recipe") != recipe and sub.get("recipe_type") == BATCH_PREPARATION:
			preps[item] = preps.get(item, 0.0) + qty
		else:
			raw[item] = raw.get(item, 0.0) + qty


def plan_day(
	demand: dict[str, float],
	recipe_for_item: dict[str, dict],
	sub_recipes: dict[str, dict],
	recipe_lines: dict[str, list[dict]],
	stock: dict[str, float],
	use_finished_stock: bool = True,
) -> dict:
	"""demand: {item_code: units ordered, in the item's stock UOM (aliases already folded)}
	recipe_for_item / sub_recipes / recipe_lines: as in the Inventory Variance report
	stock: {item_code: qty on hand, stock UOM}

	Returns {"make", "components", "preps", "pick", "ingredients"}; quantities in stock UOM.
	"""
	make, pick = [], []
	raw: dict[str, float] = {}
	prep_demand: dict[str, float] = {}
	components: dict[str, float] = {}

	for item, units in sorted(demand.items()):
		units = flt(units)
		if units <= EPS:
			continue
		rec = recipe_for_item.get(item)
		if not rec:
			on_hand = flt(stock.get(item))
			pick.append({"item": item, "need": units, "in_stock": on_hand, "short": max(0.0, units - on_hand)})
			continue
		if rec.get("recipe_type") == BATCH_PREPARATION:
			# sold as-is (e.g. a box of dough): comes out of the prep stock below
			prep_demand[item] = prep_demand.get(item, 0.0) + units
			continue
		on_hand = max(0.0, flt(stock.get(item))) if use_finished_stock else 0.0
		to_make = max(0.0, units - on_hand)
		batch_yield = flt(rec.get("batch_yield")) or 1.0
		batches = whole_batches(to_make, batch_yield)
		make.append({
			"item": item, "recipe": rec["recipe"], "ordered": units, "on_hand": on_hand,
			"to_make": to_make, "batches": batches, "units": batches * batch_yield, "batch_yield": batch_yield,
		})
		if batches:
			_expand(rec["recipe"], batches, recipe_lines, sub_recipes, raw, prep_demand, components)

	# Batch preparations: shortfall -> suggested batches, whose ingredients may need more preps.
	suggested: dict[str, int] = {}
	for _round in range(MAX_DEPTH + 1):
		extra_raw: dict[str, float] = {}
		extra_preps: dict[str, float] = {}
		extra_components: dict[str, float] = {}
		new_suggested = {}
		total = dict(prep_demand)
		# demand from the prep runs suggested in the previous round
		for item, batches in suggested.items():
			sub = sub_recipes[item]
			_expand(sub["recipe"], batches, recipe_lines, sub_recipes, extra_raw, extra_preps, extra_components)
		for item, qty in extra_preps.items():
			total[item] = total.get(item, 0.0) + qty
		for item, need in total.items():
			sub = sub_recipes.get(item) or recipe_for_item.get(item) or {}
			short = max(0.0, need - max(0.0, flt(stock.get(item))))
			n = whole_batches(short, sub.get("batch_yield")) if sub.get("recipe") else 0
			if n:
				new_suggested[item] = n
		if new_suggested == suggested:
			break
		suggested = new_suggested
	else:
		raise VarianceError("Batch preparations depend on each other in a loop")

	for item, qty in extra_raw.items():
		raw[item] = raw.get(item, 0.0) + qty
	for recipe, qty in extra_components.items():
		components[recipe] = components.get(recipe, 0.0) + qty

	preps = []
	for item, need in sorted(total.items()):
		sub = sub_recipes.get(item) or recipe_for_item.get(item) or {}
		on_hand = flt(stock.get(item))
		batches = suggested.get(item, 0)
		batch_yield = flt(sub.get("batch_yield")) or 1.0
		preps.append({
			"item": item, "recipe": sub.get("recipe"), "need": need, "in_stock": on_hand,
			"short": max(0.0, need - max(0.0, on_hand)), "batches": batches, "units": batches * batch_yield,
			"batch_yield": batch_yield,
		})

	ingredients = []
	for item, need in raw.items():
		on_hand = flt(stock.get(item))
		ingredients.append({"item": item, "need": need, "in_stock": on_hand, "short": max(0.0, need - max(0.0, on_hand))})
	ingredients.sort(key=lambda r: (r["short"] <= EPS, r["item"]))

	return {
		"make": make,
		"components": [{"recipe": r, "units": q} for r, q in sorted(components.items())],
		"preps": preps,
		"pick": pick,
		"ingredients": ingredients,
	}
