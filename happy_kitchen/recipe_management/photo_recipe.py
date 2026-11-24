"""Pure rules for the handwritten-recipe photo reader (no frappe, no network): the prompt and JSON shape the
models answer in, cleaning of their answer, unit conversion into the Recipe Ingredient units, item matching
and the plain-text rendering. Tests: tests/test_photo_recipe.py."""
from __future__ import annotations

import re

PROMPT = (
	"This is a photo of a handwritten or printed kitchen recipe. The writing may be English, Traditional or Simplified "
	"Chinese, or a mix. Read it carefully and return JSON only. Copy every ingredient name exactly as written (keep Chinese "
	"characters), with its quantity as a number and its unit as written (g, kg, ml, l, oz, lb, tsp, tbsp, cup, piece, 克, 公斤, "
	"毫升, 兩, 斤, 隻, 個 ...). A fraction such as 1/2 is 0.5. If a quantity or unit is missing, leave qty 0 / unit empty: never "
	"guess a value you cannot read. steps are the method in order. yield_text is any batch size or number of portions written "
	"on the page, as written. text is a faithful plain-text transcription of the whole page, line by line. "
	"language is en, zh or mixed. Put anything you could not read, or doubted, in unclear (short phrases).")

SCHEMA = {
	"type": "OBJECT",
	"properties": {
		"title": {"type": "STRING"}, "language": {"type": "STRING"}, "yield_text": {"type": "STRING"},
		"ingredients": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
			"name": {"type": "STRING"}, "qty": {"type": "NUMBER"}, "unit": {"type": "STRING"}, "note": {"type": "STRING"}},
			"required": ["name"]}},
		"steps": {"type": "ARRAY", "items": {"type": "STRING"}},
		"text": {"type": "STRING"},
		"unclear": {"type": "ARRAY", "items": {"type": "STRING"}}},
	"required": ["ingredients", "text"],
}

# Recipe Ingredient `uom` options are g, kg, oz, lb, ml, l, piece. Other units are converted (factor, target unit).
UNITS = {
	"g": ("g", 1), "gm": ("g", 1), "gram": ("g", 1), "grams": ("g", 1), "克": ("g", 1), "公克": ("g", 1), "g.": ("g", 1),
	"kg": ("kg", 1), "kgs": ("kg", 1), "公斤": ("kg", 1), "千克": ("kg", 1),
	"oz": ("oz", 1), "ounce": ("oz", 1), "ounces": ("oz", 1), "安士": ("oz", 1), "盎司": ("oz", 1),
	"lb": ("lb", 1), "lbs": ("lb", 1), "pound": ("lb", 1), "pounds": ("lb", 1), "磅": ("lb", 1),
	"ml": ("ml", 1), "cc": ("ml", 1), "毫升": ("ml", 1), "c.c.": ("ml", 1),
	"l": ("l", 1), "litre": ("l", 1), "liter": ("l", 1), "公升": ("l", 1), "升": ("l", 1),
	"piece": ("piece", 1), "pieces": ("piece", 1), "pc": ("piece", 1), "pcs": ("piece", 1), "no": ("piece", 1), "nos": ("piece", 1),
	"隻": ("piece", 1), "只": ("piece", 1), "個": ("piece", 1), "个": ("piece", 1), "粒": ("piece", 1), "顆": ("piece", 1),
	"片": ("piece", 1), "條": ("piece", 1),
	# kitchen measures: converted, the original is kept in the line note
	"tsp": ("ml", 5), "茶匙": ("ml", 5), "teaspoon": ("ml", 5), "teaspoons": ("ml", 5),
	"tbsp": ("ml", 15), "湯匙": ("ml", 15), "tablespoon": ("ml", 15), "tablespoons": ("ml", 15), "tbs": ("ml", 15),
	"cup": ("ml", 240), "cups": ("ml", 240), "杯": ("ml", 240),
	# Hong Kong tael (37.8 g) and catty (604.8 g)
	"兩": ("g", 37.8), "两": ("g", 37.8), "斤": ("g", 604.8),
}


def _num(v) -> float:
	try:
		return max(float(v), 0.0)
	except (TypeError, ValueError):
		return 0.0


def convert(qty, unit) -> tuple[float, str, str]:
	"""(qty, recipe unit, note). Unknown or blank units come back as ('', note) with the unit as written in the note."""
	q = _num(qty)
	u = re.sub(r"\s+", "", str(unit or "")).lower()
	if not u:
		return q, "", ""
	hit = UNITS.get(u)
	if not hit:
		return q, "", "unit as written: %s" % str(unit).strip()
	target, factor = hit
	note = "" if factor == 1 else "written as %g %s" % (q, str(unit).strip())
	return round(q * factor, 4), target, note


def clean(data) -> dict:
	"""Tidy the model's JSON: bounded lists, no empty names, numeric quantities, converted units."""
	data = data if isinstance(data, dict) else {}
	ings = []
	for r in (data.get("ingredients") or [])[:80]:
		if not isinstance(r, dict):
			continue
		name = " ".join(str(r.get("name") or "").split())
		if not name:
			continue
		qty, unit, note = convert(r.get("qty"), r.get("unit"))
		extra = " ".join(str(r.get("note") or "").split())
		ings.append({"name": name, "qty": qty, "uom": unit, "note": "; ".join(x for x in (extra, note) if x)})
	steps = [" ".join(str(s).split()) for s in (data.get("steps") or [])[:60] if str(s).strip()]
	return {
		"title": " ".join(str(data.get("title") or "").split()),
		"language": str(data.get("language") or "")[:10],
		"yield_text": " ".join(str(data.get("yield_text") or "").split()),
		"ingredients": ings, "steps": steps,
		"text": str(data.get("text") or "").strip(),
		"unclear": [" ".join(str(u).split()) for u in (data.get("unclear") or [])[:30] if str(u).strip()],
	}


def to_text(d: dict) -> str:
	"""Plain-text version of a cleaned reading (used when the model gave no transcription of its own)."""
	if d.get("text"):
		return d["text"]
	out = [d["title"]] if d.get("title") else []
	out += ["%s %s %s" % (i["name"], ("%g" % i["qty"]) if i["qty"] else "", i["uom"]) for i in d.get("ingredients", [])]
	out += ["%d. %s" % (n, s) for n, s in enumerate(d.get("steps", []), 1)]
	return "\n".join(x.strip() for x in out)


def pick_match(name: str, items: list[dict]) -> str | None:
	"""Best item code for a written name. items: [{name, item_name, item_name_zh}]. Exact name beats starts-with beats contains;
	the shortest name wins within a rank; two equally good candidates mean no match (a person picks)."""
	n = re.sub(r"\s+", " ", (name or "").strip().lower())
	if not n:
		return None
	best, rank_best, tie = None, 0, False
	for it in items:
		labels = [str(it.get(k) or "").strip().lower() for k in ("name", "item_name", "item_name_zh")]
		labels = [x for x in labels if x]
		if not labels:
			continue
		if n in labels:
			rank = 4
		elif any(x.startswith(n) for x in labels):
			rank = 3
		elif any(n in x for x in labels):
			rank = 2
		elif any(x in n for x in labels if len(x) >= 3):
			rank = 1
		else:
			continue
		size = min(len(x) for x in labels)
		if rank > rank_best or (rank == rank_best and size < best[1]):
			best, rank_best, tie = (it["name"], size), rank, False
		elif rank == rank_best and size == best[1] and it["name"] != best[0]:
			tie = True
	return None if tie or not best else best[0]


def json_schema() -> dict:
	"""SCHEMA with lower-case JSON-Schema type names (Gemini wants upper-case, Claude's tool input wants lower-case)."""
	def low(x):
		if isinstance(x, dict):
			return {k: (v.lower() if k == "type" and isinstance(v, str) else low(v)) for k, v in x.items()}
		return [low(i) for i in x] if isinstance(x, list) else x
	return low(SCHEMA)
