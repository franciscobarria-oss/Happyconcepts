"""Pure helpers for production logging (no frappe import, see tests/test_production.py)."""

import json
import math

BATCH_PREPARATION = "Batch Preparation"
LOGGABLE_STATUS = "Active"


def stock_qty(qty, whole_number: bool) -> float:
	"""Quantity for a stock move. Whole-number UOMs (Nos) can't hold 0.025 of an egg, so they
	round up to whole pieces; weights keep 3 decimals."""
	qty = float(qty or 0)
	if whole_number:
		return float(math.ceil(qty - 1e-9))
	return round(qty, 3)


def clean_entries(entries) -> list[dict]:
	"""[{"recipe", "batches"}] from the Production screen (list or JSON); drops empty rows and
	adds up repeated recipes. Raises ValueError when nothing is left."""
	if isinstance(entries, str):
		entries = json.loads(entries or "[]")
	totals: dict[str, float] = {}
	for e in entries or []:
		recipe = (e.get("recipe") or "").strip()
		batches = float(e.get("batches") or 0)
		if recipe and batches > 0:
			totals[recipe] = totals.get(recipe, 0.0) + batches
	if not totals:
		raise ValueError("Choose at least one recipe and a number of batches")
	return [{"recipe": r, "batches": b} for r, b in totals.items()]


def preview(rows: list[dict]) -> dict:
	"""Shape ingredient usage rows for "Check ingredients": short items first, then by name."""
	lines = [
		{
			"item": r["item"],
			"item_name": r.get("item_name") or r["item"],
			"stock_uom": r.get("stock_uom"),
			"needed": float(r.get("gross_qty") or 0),
			"in_stock": float(r.get("actual_qty") or 0),
			"short": float(r.get("shortage_qty") or 0),
			"cost": float(r.get("estimated_cost") or 0),
		}
		for r in rows
	]
	lines.sort(key=lambda l: (l["short"] <= 0, l["item_name"].lower()))
	return {
		"lines": lines,
		"total_cost": sum(l["cost"] for l in lines),
		"short_count": sum(1 for l in lines if l["short"] > 0),
	}


def split_runs(rows: list[dict], recipe_types: dict[str, str]) -> tuple[list[dict], list[dict]]:
	"""(batch preparation rows, other rows): batch preparations get their own Manufacture entry,
	the rest share one Material Issue."""
	batch, other = [], []
	for r in rows:
		(batch if recipe_types.get(r["recipe"]) == BATCH_PREPARATION else other).append(r)
	return batch, other
