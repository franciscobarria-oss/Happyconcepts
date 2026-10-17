"""Pure recipe-costing maths, kept free of Frappe so it can be unit-tested
without a site. The Recipe controller, reports and APIs all call into here.

Conventions (same as the HK-3 spreadsheet):
- Every ingredient has a base unit: grams (stock UOM "Gram") or pieces
  (stock UOM "Nos"). ml is treated as grams (density 1).
- The quantity typed on a recipe line is the NET quantity that ends up in
  the product. Yield % is the usable share of what is bought (trim, peel,
  bones, spillage). Gross = net / yield, and cost is charged on gross.
"""

from __future__ import annotations

from collections import OrderedDict

# Recipe-line unit -> (factor to base unit, base kind)
UOM_TO_BASE = {
	"g": (1.0, "weight"),
	"kg": (1000.0, "weight"),
	"oz": (28.3495, "weight"),
	"lb": (453.592, "weight"),
	"ml": (1.0, "weight"),
	"l": (1000.0, "weight"),
	"piece": (1.0, "count"),
}

# ERPNext stock UOM -> base kind
STOCK_UOM_KIND = {
	"Gram": "weight",
	"g": "weight",
	"Nos": "count",
	"Unit": "count",
	"Piece": "count",
}

OVERHEAD_BASES = (
	"Per Batch",
	"Per Unit",
	"% of Ingredient Cost",
	"% of Labour Cost",
	"Per Labour Hour",
)


class CostingError(ValueError):
	pass


def flt(value, default=0.0) -> float:
	try:
		return float(value) if value not in (None, "") else default
	except (TypeError, ValueError):
		return default


def to_base_qty(qty, uom: str) -> float:
	"""Convert a recipe-line quantity to grams or pieces."""
	if uom not in UOM_TO_BASE:
		raise CostingError(f"Unknown unit '{uom}'. Use one of: {', '.join(UOM_TO_BASE)}")
	return flt(qty) * UOM_TO_BASE[uom][0]


def check_uom_compatible(uom: str, stock_uom: str | None, grams_per_piece=None) -> None:
	"""A gram ingredient can't be measured in pieces and vice versa, unless the
	item has a weight per piece (Item > Weight Per Unit)."""
	kind = STOCK_UOM_KIND.get(stock_uom or "")
	if kind is None:
		return  # unknown stock UOM: don't block, the price lookup decides
	if UOM_TO_BASE[uom][1] != kind and not flt(grams_per_piece):
		raise CostingError(
			f"Unit '{uom}' doesn't fit an ingredient stocked in '{stock_uom}'. "
			+ ("Use 'piece'" if kind == "count" else "Use g, kg, oz, lb, ml or l")
			+ ", or set the item's Weight Per Unit (grams per piece)."
		)


def to_stock_qty(qty, uom: str, stock_uom: str | None, grams_per_piece=None) -> float:
	"""Recipe-line quantity in the ingredient's stock unit (grams or pieces),
	converting weight <-> pieces with the item's grams per piece when needed."""
	base = to_base_qty(qty, uom)
	line_kind, stock_kind = UOM_TO_BASE[uom][1], STOCK_UOM_KIND.get(stock_uom or "")
	if stock_kind is None or line_kind == stock_kind:
		return base
	check_uom_compatible(uom, stock_uom, grams_per_piece)
	gpp = flt(grams_per_piece)
	return base / gpp if stock_kind == "count" else base * gpp


def line_grams(qty, uom: str, grams_per_piece=None) -> float:
	"""Weight of a recipe line in grams (0 for pieces with no known weight)."""
	base = to_base_qty(qty, uom)
	return base if UOM_TO_BASE[uom][1] == "weight" else base * flt(grams_per_piece)


WEIGHT_UOM_TO_GRAMS = {"gram": 1.0, "g": 1.0, "kg": 1000.0, "kilogram": 1000.0, "mg": 0.001, "oz": 28.3495, "pound": 453.592, "lb": 453.592}


def grams_per_piece(weight_per_unit, weight_uom: str | None) -> float:
	"""Item.weight_per_unit + weight_uom -> grams (weight_uom blank = grams)."""
	factor = WEIGHT_UOM_TO_GRAMS.get((weight_uom or "gram").strip().lower(), 1.0)
	return flt(weight_per_unit) * factor


def gross_qty(net_base_qty, yield_pct) -> float:
	"""Quantity that must be bought/issued to get net_base_qty after losses."""
	y = flt(yield_pct, 100.0)
	if y <= 0 or y > 100:
		raise CostingError(f"Yield % must be between 0 and 100, got {yield_pct}")
	return flt(net_base_qty) * 100.0 / y


def price_per_base_unit(rate, conversion_factor=1.0) -> float:
	"""Item Price rate is per price UOM (e.g. Kg); turn it into $/g or $/piece."""
	cf = flt(conversion_factor, 1.0) or 1.0
	return flt(rate) / cf


def pick_price(prices: list[dict], supplier: str | None = None) -> dict | None:
	"""Choose the price line for an ingredient.

	prices: dicts with at least 'supplier' and 'price_per_base_unit'.
	If a supplier is given, use that supplier's price (None if it has none);
	otherwise use the cheapest non-zero price, falling back to a zero price.
	"""
	if not prices:
		return None
	if supplier:
		own = [p for p in prices if p.get("supplier") == supplier]
		return min(own, key=lambda p: flt(p["price_per_base_unit"])) if own else None
	non_zero = [p for p in prices if flt(p["price_per_base_unit"]) > 0]
	return min(non_zero or prices, key=lambda p: flt(p["price_per_base_unit"]))


def cost_line(qty, uom: str, yield_pct, unit_price, stock_uom: str | None = None, grams_per_piece=None) -> dict:
	"""unit_price is per stock unit; base/gross quantities are in the stock unit."""
	net = to_stock_qty(qty, uom, stock_uom, grams_per_piece)
	gross = gross_qty(net, yield_pct)
	return {
		"base_qty": net,
		"gross_qty": gross,
		"line_cost": gross * flt(unit_price),
	}


def overhead_amount(basis: str, rate, *, batch_yield, ingredient_cost, labour_cost, labour_minutes) -> float:
	rate = flt(rate)
	if basis == "Per Batch":
		return rate
	if basis == "Per Unit":
		return rate * flt(batch_yield)
	if basis == "% of Ingredient Cost":
		return flt(ingredient_cost) * rate / 100.0
	if basis == "% of Labour Cost":
		return flt(labour_cost) * rate / 100.0
	if basis == "Per Labour Hour":
		return rate * flt(labour_minutes) / 60.0
	raise CostingError(f"Unknown overhead basis '{basis}'")


def summarize(
	*,
	ingredient_costs: list[float],
	labour: list[dict],
	overheads: list[dict],
	batch_yield,
	selling_price=None,
	target_food_cost_pct=None,
) -> dict:
	"""Roll up a recipe.

	labour: dicts with hourly_rate, minutes. overheads: dicts with basis, rate.
	Returns batch and per-unit totals plus per-row amounts in the same order
	as the inputs ('labour_costs', 'overhead_amounts', 'cost_shares').
	"""
	units = flt(batch_yield)
	if units <= 0:
		raise CostingError("Batch yield must be more than 0")

	ingredient_total = sum(flt(c) for c in ingredient_costs)
	labour_costs = [flt(r.get("hourly_rate")) * flt(r.get("minutes")) / 60.0 for r in labour]
	labour_total = sum(labour_costs)
	labour_minutes = sum(flt(r.get("minutes")) for r in labour)
	overhead_amounts = [
		overhead_amount(
			r.get("basis") or "Per Batch",
			r.get("rate"),
			batch_yield=units,
			ingredient_cost=ingredient_total,
			labour_cost=labour_total,
			labour_minutes=labour_minutes,
		)
		for r in overheads
	]
	overhead_total = sum(overhead_amounts)
	batch_total = ingredient_total + labour_total + overhead_total

	out = {
		"total_ingredient_cost": ingredient_total,
		"total_labour_cost": labour_total,
		"total_labour_minutes": labour_minutes,
		"total_overhead_cost": overhead_total,
		"total_batch_cost": batch_total,
		"ingredient_cost_per_unit": ingredient_total / units,
		"labour_cost_per_unit": labour_total / units,
		"overhead_cost_per_unit": overhead_total / units,
		"cost_per_unit": batch_total / units,
		"labour_costs": labour_costs,
		"overhead_amounts": overhead_amounts,
		"cost_shares": [
			(flt(c) / ingredient_total * 100.0) if ingredient_total else 0.0 for c in ingredient_costs
		],
		"food_cost_pct": 0.0,
		"total_cost_pct": 0.0,
		"gross_margin": 0.0,
		"suggested_price": 0.0,
	}

	price = flt(selling_price)
	if price > 0:
		out["food_cost_pct"] = out["ingredient_cost_per_unit"] / price * 100.0
		out["total_cost_pct"] = out["cost_per_unit"] / price * 100.0
		out["gross_margin"] = price - out["cost_per_unit"]
	target = flt(target_food_cost_pct)
	if target > 0:
		out["suggested_price"] = out["ingredient_cost_per_unit"] / (target / 100.0)
	return out


def allocate_loaded_costs(line_costs: list[float], labour_total, overhead_total) -> list[float]:
	"""Spread labour + overheads over ingredient lines by their cost share,
	giving a fully loaded cost per ingredient line."""
	total = sum(flt(c) for c in line_costs)
	extra = flt(labour_total) + flt(overhead_total)
	if not total:
		n = len(line_costs)
		return [extra / n for _ in line_costs] if n else []
	return [flt(c) + extra * flt(c) / total for c in line_costs]


def cooking_yield(total_input_weight, batch_yield, unit_weight) -> tuple[float, float]:
	"""(output weight g, cooking yield %) from finished unit weight."""
	output = flt(batch_yield) * flt(unit_weight)
	pct = output / flt(total_input_weight) * 100.0 if flt(total_input_weight) and output else 0.0
	return output, pct


def aggregate_usage(runs: list[dict], recipe_lines: dict[str, list[dict]]) -> list[dict]:
	"""Total ingredient usage for a set of production runs.

	runs: [{"recipe": name, "batches": n}, ...]
	recipe_lines: {recipe: [{"item", "item_name", "stock_uom", "base_qty",
	               "gross_qty", "price_per_base_unit", "supplier"}, ...]}
	Returns one row per ingredient, sorted by item code, with net/gross/waste
	quantities in the stock UOM, estimated cost and the recipes that use it.
	"""
	usage: OrderedDict[str, dict] = OrderedDict()
	for run in runs:
		batches = flt(run.get("batches"))
		if not batches:
			continue
		for line in recipe_lines.get(run["recipe"], []):
			row = usage.setdefault(
				line["item"],
				{
					"item": line["item"],
					"item_name": line.get("item_name"),
					"stock_uom": line.get("stock_uom"),
					"supplier": line.get("supplier"),
					"price_per_base_unit": flt(line.get("price_per_base_unit")),
					"net_qty": 0.0,
					"gross_qty": 0.0,
					"waste_qty": 0.0,
					"estimated_cost": 0.0,
					"recipes": [],
				},
			)
			net = flt(line.get("base_qty")) * batches
			gross = flt(line.get("gross_qty") or line.get("base_qty")) * batches
			row["net_qty"] += net
			row["gross_qty"] += gross
			row["waste_qty"] += gross - net
			row["estimated_cost"] += gross * flt(line.get("price_per_base_unit"))
			if run["recipe"] not in row["recipes"]:
				row["recipes"].append(run["recipe"])
	return [usage[k] for k in sorted(usage)]
