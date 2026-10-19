"""Product label content, as pure functions (unit-tested in tests/test_labels.py).

A product's ingredient list comes from its recipe: sub-recipes (dough, bases,
fillings) are broken down into what they are made of, packaging is left out,
ingredients that print under the same name are added together, and the list is
sorted heaviest first, as Hong Kong labelling rules require.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import date, timedelta

STORAGE_TEXT = {
	"Ambient": "Store in a cool dry place",
	"Chilled": "Keep refrigerated at 0-4°C",
	"Frozen": "Keep frozen at -18°C or below",
}


def ingredient_weights(item: str, recipe_for_item: dict, lines: dict, piece_grams: dict,
                       qty: float = 1.0, _path: tuple = ()) -> tuple[dict[str, float], list[str]]:
	"""Grams of each raw ingredient in `qty` units of `item`, plus warnings.

	recipe_for_item: item -> {"recipe", "batch_yield"} for every item that has a recipe
	lines:           recipe -> [{"item", "gross_qty", "stock_uom", "component_type"}] per batch (stock UOM)
	piece_grams:     item -> grams per piece, for ingredients counted in pieces (eggs)
	"""
	info = recipe_for_item[item]
	per_unit = qty / (info.get("batch_yield") or 1.0)
	out: dict[str, float] = {}
	warnings: list[str] = []
	for l in lines.get(info["recipe"], []):
		# sub-recipe lines carry the sub-recipe's type (Batch Preparation /
		# Recipe Component); only packaging stays off the label
		if l.get("component_type") == "Packaging":
			continue
		code, amount = l["item"], (l.get("gross_qty") or 0.0) * per_unit
		if code in recipe_for_item and code != item and code not in _path:
			sub, warn = ingredient_weights(code, recipe_for_item, lines, piece_grams, amount, _path + (item,))
			# a sub-recipe made in pieces is weighed through its own ingredients
			for k, g in sub.items():
				out[k] = out.get(k, 0.0) + g
			warnings += warn
			continue
		uom = (l.get("stock_uom") or "Gram").lower()
		if uom in ("gram", "g"):
			grams = amount
		elif uom in ("kg", "kilogram"):
			grams = amount * 1000
		elif piece_grams.get(code):
			grams = amount * piece_grams[code]
		else:
			grams = 0.0
			warnings.append(f"no-weight:{code}")
		out[code] = out.get(code, 0.0) + grams
	return out, warnings


def ingredient_list(weights: dict[str, float], names: dict[str, str]) -> list[dict]:
	"""Merge ingredients that print under the same name and sort heaviest first.
	Ingredients without a known weight go last, in name order."""
	merged: dict[str, dict] = {}
	for code, grams in weights.items():
		name = (names.get(code) or code).strip()
		key = name.lower()
		row = merged.setdefault(key, {"name": name, "grams": 0.0, "items": []})
		row["grams"] += grams
		row["items"].append(code)
	return sorted(merged.values(), key=lambda r: (r["grams"] <= 0, -r["grams"], r["name"].lower()))


def allergens_for(items, item_allergens: dict[str, list[str]], order: list[str]) -> list[str]:
	"""Allergens of all ingredients, in the standard order of the Allergen list."""
	found = {a for i in items for a in item_allergens.get(i, [])}
	rank = {a: n for n, a in enumerate(order)}
	return sorted(found, key=lambda a: (rank.get(a, len(rank)), a))


def ingredients_text(rows: list[dict]) -> str:
	return ", ".join(r["name"] for r in rows)


def contains_sentence(phrases: list[str]) -> str:
	"""Allergen statement in the wording of the printed labels:
	This product contains cereals containing gluten, eggs and their products."""
	phrases = [p for p in phrases if p]
	if not phrases:
		return ""
	return "This product contains " + ", ".join(phrases) + " and their products."


def net_text(net_weight_g: float, units_per_label: int, units: int) -> str:
	net = f"{net_weight_g:g}g" if net_weight_g else ""
	if (units_per_label or 1) <= 1:
		return f"Net Weight : {net}" if net else ""
	return f"Contents : {units} x {net}" if net else f"Contents : {units} pcs"


def content_signature(content: dict) -> str:
	"""Fingerprint of what a person checks on a label (not the dates), so a
	change to the recipe or an ingredient's allergens asks for a new check."""
	keys = ("title", "ingredients", "allergens", "storage", "note", "net_weight_g", "shelf_life_days", "barcode")
	blob = json.dumps({k: content.get(k) for k in keys}, sort_keys=True, ensure_ascii=False)
	return hashlib.sha1(blob.encode("utf-8")).hexdigest()


def label_quantities(qty: float, units_per_label: int) -> list[int]:
	"""Units on each label: 200 pieces at 48 per carton -> [48, 48, 48, 48, 8]."""
	qty = max(0, math.ceil(qty - 1e-9))
	per = max(1, int(units_per_label or 1))
	full, rest = divmod(qty, per)
	return [per] * full + ([rest] if rest else [])


def label_dates(made_on: date, shelf_life_days: int) -> dict:
	best_before = made_on + timedelta(days=int(shelf_life_days)) if shelf_life_days else None
	return {
		"made_on": made_on,
		"best_before": best_before,
		"lot": "L" + made_on.strftime("%y%m%d"),
	}


def fmt_date(d: date | None) -> str:
	"""07/10/2026, under the label's "Best Before (dd/mm/yyyy)" heading."""
	return d.strftime("%d/%m/%Y") if d else ""


def missing_for_approval(content: dict) -> list[str]:
	"""What must be filled in before a label can be marked as checked."""
	missing = []
	if not content.get("ingredients"):
		missing.append("The product has no recipe ingredients.")
	if not content.get("shelf_life_days"):
		missing.append("Shelf life (days) is not set.")
	if not content.get("storage"):
		missing.append("Storage is not set.")
	for code in content.get("unchecked_allergens") or []:
		missing.append(f"Allergens of {code} have not been reviewed.")
	if content.get("barcode_error"):
		missing.append(f"The barcode can't be printed: {content['barcode_error']}")
	for code in content.get("no_weight") or []:
		missing.append(f"{code} is counted in pieces and has no weight per piece, so it can't be put in weight order.")
	return missing


def suggest_allergens(text: str, keywords: dict[str, list[str]]) -> list[str]:
	"""Allergens whose keywords appear in an ingredient's name (a hint for the reviewer)."""
	low = (text or "").lower()
	return [a for a, words in keywords.items() if any(w and w.lower() in low for w in words)]


def label_check_rows(items: list[dict], allergens: dict[str, list[str]], used_in: dict[str, set],
                     made_here: set[str], only_open: bool = False) -> list[dict]:
	"""The ingredient label fill-in sheet: one row per bought-in ingredient used in a
	recipe, with what prints for it and what is still to do.

	items: [{name, item_name, hk_label_name, hk_allergens_checked}]
	allergens: {item: [allergen, ...]}; used_in: {item: {recipe, ...}}
	made_here: items made from a sub-recipe (their own ingredients print instead)
	"""
	out = []
	for it in sorted(items, key=lambda i: (i.get("item_name") or i["name"]).lower()):
		code = it["name"]
		if code in made_here or code not in used_in:
			continue
		todo = []
		if not (it.get("hk_label_name") or "").strip():
			todo.append("label name")
		if not it.get("hk_allergens_checked"):
			todo.append("allergen review")
		if only_open and not todo:
			continue
		out.append({
			"item": code,
			"item_name": it.get("item_name") or code,
			"label_name": (it.get("hk_label_name") or "").strip(),
			"prints_as": (it.get("hk_label_name") or "").strip() or it.get("item_name") or code,
			"allergens": ", ".join(allergens.get(code, [])),
			"allergens_reviewed": 1 if it.get("hk_allergens_checked") else 0,
			"recipes": len(used_in[code]),
			"to_do": ", ".join(todo),
		})
	return out
