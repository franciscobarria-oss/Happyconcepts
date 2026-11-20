"""Cake Costing screen: saved at every step, prices from the ERP buying prices, optional photo guess (Gemini)."""
from __future__ import annotations

import base64
import json

import frappe
from frappe import _

from happy_kitchen.recipe_management import cake_math as m
from happy_kitchen.recipe_management.costing import pick_price

ROLES = ("System Manager", "Stock Manager", "Stock User", "Manufacturing User", "Manufacturing Manager")
STEPS = ("Photo", "Size", "Ingredients", "Cost")
FIELDS = ("cake_name", "shape", "height_cm", "width_cm", "length_cm", "weight_g", "slices", "labour_cost", "packaging_cost", "notes")


def _check():
	if not set(frappe.get_roles()) & set(ROLES):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def gram_price(item_code: str):
	"""(cost per gram, note) from the cheapest current buying price. Pieces without a weight have no gram price."""
	from happy_kitchen.recipe_management import pricing

	p = pick_price(pricing.get_ingredient_prices(item_code))
	if not p or not p.price_per_base_unit:
		return None, "No price"
	stock_uom = p.stock_uom
	if stock_uom in ("Nos", "Unit", "Pcs"):
		w, wu = frappe.db.get_value("Item", item_code, ["weight_per_unit", "weight_uom"]) or (0, None)
		if not w:
			return None, "No pack size"
		from happy_kitchen.recipe_management.costing import grams_per_piece

		g = grams_per_piece(w, wu)
		return (p.price_per_base_unit / g if g else None), ("" if g else "No pack size")
	return p.price_per_base_unit, ""


def price_lines(doc):
	for r in doc.get("ingredients") or []:
		if not r.item:
			r.unit_cost, r.price_note = 0, "No price"
		else:
			r.item_name = r.item_name or frappe.db.get_value("Item", r.item, "item_name")
			c, note = gram_price(r.item)
			r.unit_cost, r.price_note = c or 0, note
		r.line_cost = m.line_cost(r.qty_g, r.unit_cost) if not r.price_note else 0


@frappe.whitelist()
def recent():
	_check()
	return frappe.get_all("Cake Costing", fields=["name", "cake_name", "step", "total_cost", "modified"], order_by="modified desc", limit=30)


@frappe.whitelist()
def load(name: str):
	_check()
	return frappe.get_doc("Cake Costing", name).as_dict()


@frappe.whitelist()
def save_step(data, name: str | None = None, step: str | None = None):
	"""Save the screen's current answers (every Next tap). Creates the record on the first save."""
	_check()
	d = frappe.parse_json(data) or {}
	doc = frappe.get_doc("Cake Costing", name) if name else frappe.new_doc("Cake Costing")
	for f in FIELDS:
		if f in d:
			doc.set(f, d[f])
	if not doc.cake_name:
		doc.cake_name = _("Untitled cake")
	if step in STEPS:
		doc.step = step
	if "ingredients" in d:
		doc.set("ingredients", [])
		for r in d["ingredients"]:
			doc.append("ingredients", {k: r.get(k) for k in ("item", "item_name", "qty_g", "ai_guess")})
	doc.save()
	return doc.as_dict()


@frappe.whitelist()
def set_photo(name: str, file_url: str):
	_check()
	frappe.db.set_value("Cake Costing", name, "photo", file_url)
	return file_url


def match_items(guesses: list[dict]) -> list[dict]:
	out = []
	for g in guesses:
		words = g["name"].split()[0]
		row = frappe.db.sql(
			"select name, item_name from `tabItem` where disabled = 0 and (item_name like %s or name like %s) "
			"order by item_name limit 1", (f"%{g['name']}%", f"%{words}%"), as_dict=True)
		it = row[0] if row else None
		out.append({"item": it.name if it else None, "item_name": it.item_name if it else g["name"], "qty_g": g["grams"], "ai_guess": 1})
	return out


PROMPT = ("This is a photo of a cake. Estimate the ingredients of a typical home or bakery recipe for it and the grams of each, "
          "for a cake weighing %s g. Return JSON only: {\"ingredients\":[{\"name\":\"butter\",\"grams\":250}]}. "
          "Use plain names such as butter, sugar, flour, eggs, cocoa powder, cream. These are guesses.")


@frappe.whitelist()
def guess_from_photo(name: str):
	"""Ask Gemini for ingredient guesses from the saved photo. Returns [] when there is no key, photo or answer."""
	_check()
	doc = frappe.get_doc("Cake Costing", name)
	if not doc.photo:
		return []
	from happy_kitchen.hk_operations import pdf_ocr

	key, model = pdf_ocr._settings()
	if not key:
		frappe.throw(_("No Gemini key is set in Gmail Settings"))
	import requests

	f = frappe.get_doc("File", {"file_url": doc.photo})
	raw = f.get_content()
	mime = "image/png" if doc.photo.lower().endswith(".png") else "image/jpeg"
	body = {"contents": [{"parts": [{"inline_data": {"mime_type": mime, "data": base64.b64encode(raw).decode()}},
	                                {"text": PROMPT % (int(doc.weight_g or 0) or "unknown")}]}],
	        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}}
	try:
		r = requests.post(pdf_ocr.ENDPOINT.format(model=model), headers={"x-goog-api-key": key, "Content-Type": "application/json"}, json=body, timeout=90)
		r.raise_for_status()
		data = json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
	except Exception:
		frappe.log_error(title="Cake costing: photo guess failed")
		frappe.throw(_("The photo could not be read. Add the ingredients by hand."))
	return match_items(m.parse_guess(data))
