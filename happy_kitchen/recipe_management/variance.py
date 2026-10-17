"""Inventory variance: actual ingredient usage (from approved stock takes) vs
theoretical usage (recipes applied to production logs and sales).

Pure functions only, so they are unit-tested without a site (see
tests/test_variance.py). `stock_take_variance.py` fetches the data and calls
these.

Quantities are always in the item's stock UOM (Gram / Nos), like the rest of
the app.
"""

from __future__ import annotations

from collections import OrderedDict

from happy_kitchen.recipe_management import costing

RECIPE_COMPONENT = "Recipe Component"
BATCH_PREPARATION = "Batch Preparation"
DEFAULT_TOLERANCE_PCT = 2.0


class VarianceError(Exception):
	pass


def flt(value) -> float:
	try:
		return float(value or 0)
	except (TypeError, ValueError):
		return 0.0


# ------------------------------------------------------------ count entry


def count_to_stock_qty(qty, count_uom: str, stock_uom: str, grams_per_piece=None) -> float:
	"""A counted quantity (e.g. 2.5 kg) in the item's stock UOM (2500 Gram)."""
	try:
		return costing.to_stock_qty(qty, count_uom, stock_uom, grams_per_piece)
	except costing.CostingError as e:
		raise VarianceError(str(e)) from e


MAX_PACK_SIZES = 3

# Units that are measures, not packs: they are counted in the loose box instead
MEASURE_UOMS = {"gram", "g", "kg", "kilogram", "mg", "litre", "liter", "l", "ml", "millilitre", "milliliter",
	"nos", "unit", "piece", "pcs", "pound", "lb", "ounce", "oz"}


def packs_to_stock_qty(packs, loose, count_uom: str, stock_uom: str, grams_per_piece=None) -> float:
	"""A count made of whole packs of up to three sizes plus loose units, e.g.
	1 Bag (x22700) + 2 Bag 1kg (x1000) + 350 g -> 25050 Gram.
	packs: [(counted, stock units per pack)], from the item's UOM conversions."""
	total = 0.0
	for counted, factor in packs:
		if flt(counted) and not flt(factor):
			raise VarianceError("This pack size has no conversion to the stock unit. Set it on the Item (UOM Conversion).")
		total += flt(counted) * flt(factor)
	if flt(loose):
		total += count_to_stock_qty(loose, count_uom, stock_uom, grams_per_piece)
	return total


def pack_count_to_stock_qty(
	packs, pack_factor, loose, count_uom: str, stock_uom: str, grams_per_piece=None
) -> float:
	"""One pack size plus loose units, e.g. 2 Box (x200) + 35 piece -> 435 Nos."""
	return packs_to_stock_qty([(packs, pack_factor)], loose, count_uom, stock_uom, grams_per_piece)


def compact_packs(uoms) -> list[str]:
	"""The pack sizes set on a sheet row, in order, without gaps or repeats."""
	out: list[str] = []
	for u in uoms:
		if u and u not in out:
			out.append(u)
	return out


def suggest_packs(conversions, stock_uom: str, limit: int = MAX_PACK_SIZES) -> list[str]:
	"""Pack sizes to count an item in, from its UOM conversions [(uom, factor)]:
	real packs only (not Gram/Kg/Nos...), biggest first."""
	seen: set[float] = set()
	packs = []
	for uom, factor in sorted(conversions, key=lambda c: -flt(c[1])):
		if not uom or uom == stock_uom or uom.strip().lower() in MEASURE_UOMS or flt(factor) <= 1 or flt(factor) in seen:
			continue
		seen.add(flt(factor))
		packs.append(uom)
	return packs[:limit]


def pack_caption(uom: str, factor, stock_uom: str) -> str:
	"""A pack size in words for the paper count sheet: 'Pack 22.7 kg', 'Case 360 pcs'."""
	f = flt(factor)
	if not f:
		return uom
	if (stock_uom or "").lower() in ("gram", "g"):
		size = f"{f / 1000:,.2f}".rstrip("0").rstrip(".") + " kg" if f >= 1000 else f"{f:,.0f} g"
	else:
		size = f"{f:,.0f} pcs" if (stock_uom or "").lower() in ("nos", "unit", "piece") else f"{f:,.0f} {stock_uom}"
	return f"{uom} {size}"


def default_count_uom(stock_uom: str) -> str:
	return "piece" if costing.STOCK_UOM_KIND.get(stock_uom) == "count" else "g"


# ------------------------------------------------------- expected usage


def fold_aliases(sales: dict[str, float], aliases: dict[str, tuple]) -> dict[str, float]:
	"""Sales of other SKUs for the same product (a customer's article number, a
	box of 200 dough pieces) moved onto the recipe's own item, in its units.

	aliases: {sku: (recipe_item, recipe_units_per_sku)}
	"""
	out: dict[str, float] = {}
	for item, qty in sales.items():
		target, units = aliases.get(item, (item, 1.0))
		out[target] = out.get(target, 0.0) + flt(qty) * (flt(units) or 1.0)
	return out


def runs_from_sales(sales: dict[str, float], recipe_for_item: dict[str, dict], produced_items: set[str]) -> list[dict]:
	"""Recipe runs for units sold, skipping items that were produced in the
	period ("production wins": their ingredients are counted from the
	production logs, so a produced item that is later sold counts once).

	sales: {item_code: units sold in stock UOM}
	recipe_for_item: {item_code: {"recipe": name, "recipe_type": ..., "batch_yield": n}}
	Batch preparations and bought-in items are not expanded: see sold_as_is().
	"""
	runs = []
	for item, units in sales.items():
		if item in produced_items or not flt(units):
			continue
		rec = recipe_for_item.get(item)
		if not rec or rec.get("recipe_type") == BATCH_PREPARATION:
			continue
		runs.append({"recipe": rec["recipe"], "batches": flt(units) / (flt(rec.get("batch_yield")) or 1.0)})
	return runs


def sold_as_is(sales: dict[str, float], recipe_for_item: dict[str, dict]) -> dict[str, float]:
	"""Stocked items that leave stock themselves when sold: batch preparations
	(e.g. cookie dough sold to a customer; its ingredients were counted when it
	was produced) and bought-in items with no recipe."""
	out = {}
	for item, units in sales.items():
		rec = recipe_for_item.get(item)
		if flt(units) and (not rec or rec.get("recipe_type") == BATCH_PREPARATION):
			out[item] = flt(units)
	return out


def expand_usage(
	runs: list[dict],
	recipe_lines: dict[str, list[dict]],
	sub_recipes: dict[str, dict],
	max_depth: int = 10,
) -> dict[str, float]:
	"""Expected gross usage per item for a set of recipe runs.

	runs: [{"recipe": name, "batches": n}]
	recipe_lines: {recipe: [{"item", "gross_qty" (or "base_qty")}]}, per batch, stock UOM
	sub_recipes: {item_code: {"recipe", "recipe_type", "batch_yield"}} for items made in-house

	A line whose item is a Recipe Component (made fresh as part of the parent)
	is broken down into that component recipe's own lines, recursively. A
	Batch Preparation (made ahead and stocked) stays as its own item: its raw
	ingredients are counted when the batch itself is produced, so expanding it
	here would count them twice.
	"""
	usage: OrderedDict[str, float] = OrderedDict()

	def add(recipe: str, batches: float, path: tuple):
		if recipe in path:
			raise VarianceError(f"Recipe loop: {' -> '.join(path + (recipe,))}")
		if len(path) >= max_depth:
			raise VarianceError(f"Sub-recipes nested deeper than {max_depth} levels at {recipe}")
		for line in recipe_lines.get(recipe, []):
			qty = flt(line.get("gross_qty") or line.get("base_qty")) * batches
			if not qty:
				continue
			sub = sub_recipes.get(line["item"])
			if sub and sub.get("recipe_type") == RECIPE_COMPONENT and sub.get("recipe") != recipe:
				add(sub["recipe"], qty / (flt(sub.get("batch_yield")) or 1.0), path + (recipe,))
			else:
				usage[line["item"]] = usage.get(line["item"], 0.0) + qty

	for run in runs:
		if flt(run.get("batches")):
			add(run["recipe"], flt(run["batches"]), ())
	return dict(usage)


# ------------------------------------------------------------- variance


def actual_usage(opening, received, closing, produced=0.0) -> float:
	"""What left stock in the period: opening + purchases received
	(+ batch preparations produced) - closing."""
	return flt(opening) + flt(received) + flt(produced) - flt(closing)


def variance_row(actual, expected, unit_cost, tolerance_pct=DEFAULT_TOLERANCE_PCT, wastage=0.0) -> dict:
	"""Variance figures for one ingredient. variance_pct is None when nothing
	was expected (any actual usage then counts as out of tolerance).

	Recorded wastage is part of the variance (it left stock but no recipe
	used it); what is left after it is the unexplained loss."""
	actual, expected = flt(actual), flt(expected)
	var_qty = actual - expected
	if expected:
		var_pct = var_qty / expected * 100.0
		within = abs(var_pct) <= flt(tolerance_pct) + 1e-9
	else:
		var_pct = None
		within = abs(var_qty) < 1e-9
	return {
		"actual_usage": actual,
		"expected_usage": expected,
		"variance_qty": var_qty,
		"unit_cost": flt(unit_cost),
		"variance_cost": var_qty * flt(unit_cost),
		"variance_pct": var_pct,
		"within_tolerance": within,
		"wastage_qty": flt(wastage),
		"wastage_cost": flt(wastage) * flt(unit_cost),
		"unexplained_qty": var_qty - flt(wastage),
		"unexplained_cost": (var_qty - flt(wastage)) * flt(unit_cost),
	}


def totals(rows: list[dict]) -> dict:
	"""Period totals. Overall % is cost-weighted (cost of the variance / cost of
	expected usage), because grams of salt and pieces of egg can't be added."""
	var_cost = sum(flt(r["variance_cost"]) for r in rows)
	expected_cost = sum(flt(r["expected_usage"]) * flt(r["unit_cost"]) for r in rows)
	return {
		"wastage_cost": sum(flt(r.get("wastage_cost")) for r in rows),
		"unexplained_cost": sum(flt(r.get("unexplained_cost", r["variance_cost"])) for r in rows),
		"variance_cost": var_cost,
		"expected_cost": expected_cost,
		"variance_pct": (var_cost / expected_cost * 100.0) if expected_cost else None,
		"out_of_tolerance": sum(1 for r in rows if not r["within_tolerance"]),
	}


# ------------------------------------------------------------- approval

DRAFT, SUBMITTED, APPROVED, REJECTED = "Draft", "Submitted", "Approved", "Rejected"
APPROVER_ROLE = "Stock Take Approver"


def check_transition(action: str, status: str, user: str, submitted_by: str | None, roles, comment: str | None = None) -> str:
	"""Validate a stock take state change and return the new status.

	draft -> submitted -> approved, or submitted -> rejected (comment required),
	which puts the count back to draft for correction. Raises VarianceError."""
	roles = set(roles or [])
	if action == "submit":
		if status not in (DRAFT, REJECTED):
			raise VarianceError(f"Only a draft count can be submitted (it is {status}).")
		return SUBMITTED
	if action in ("approve", "reject"):
		if status != SUBMITTED:
			raise VarianceError(f"Only a submitted count can be {action}d (it is {status}).")
		if APPROVER_ROLE not in roles:
			raise VarianceError(f"You need the {APPROVER_ROLE} role to {action} a stock take.")
		if submitted_by and user == submitted_by:
			raise VarianceError(f"You submitted this count, so someone else has to {action} it.")
		if action == "reject":
			if not (comment or "").strip():
				raise VarianceError("Add a comment explaining why the count is rejected.")
			return DRAFT
		return APPROVED
	raise VarianceError(f"Unknown action {action}")
