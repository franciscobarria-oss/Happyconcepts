"""Read a photo of a handwritten recipe (English / Chinese): Claude first, Gemini as the backup, then a draft Recipe.

Keys: Recipe Settings `anthropic_api_key` / `anthropic_model` (Claude) and Gmail Settings `gemini_api_key` (shared with the
scanned-PDF reader). Nothing is saved by reading; a draft Recipe is only made by `create_draft`, status Draft, and lines the
reader could not match to an item or unit go into the recipe notes for a person to add."""
from __future__ import annotations

import base64
import io
import json

import frappe
from frappe import _

from happy_kitchen.hk_operations import pdf_ocr
from happy_kitchen.recipe_management import photo_recipe as pr

ROLES = ("System Manager", "Manufacturing Manager", "Manufacturing User", "Stock Manager", "Stock User")
CLAUDE_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_CLAUDE_MODEL = "claude-sonnet-5-5"
MAX_SIDE = 1800


def _check():
	if not set(frappe.get_roles()) & set(ROLES):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def _claude_settings():
	s = frappe.get_single("Recipe Settings")
	return s.get_password("anthropic_api_key", raise_exception=False), (s.get("anthropic_model") or "").strip() or DEFAULT_CLAUDE_MODEL


def prepare_image(raw: bytes) -> tuple[bytes, str]:
	"""Shrink a phone photo (EXIF turned upright, longest side 1800 px, JPEG) so it is small enough for both APIs."""
	from PIL import Image, ImageOps

	im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
	im.thumbnail((MAX_SIDE, MAX_SIDE))
	out = io.BytesIO()
	im.save(out, "JPEG", quality=85)
	return out.getvalue(), "image/jpeg"


def _post(url, headers, body, timeout=90):
	"""POST with the same patience as the PDF reader (retry when the service is busy). Returns (response or None, error)."""
	import time

	import requests

	error = ""
	for attempt in range(len(pdf_ocr.RETRY_WAIT) + 1):
		try:
			r = requests.post(url, headers=headers, json=body, timeout=timeout)
			if r.status_code == 200:
				return r, ""
			error = "HTTP %s: %s" % (r.status_code, r.text[:400])
			if r.status_code not in pdf_ocr.RETRY_STATUS and r.status_code != 529:
				return None, error
		except requests.RequestException as e:
			error = "%s: %s" % (type(e).__name__, str(e)[:300])
		if attempt < len(pdf_ocr.RETRY_WAIT):
			time.sleep(pdf_ocr.RETRY_WAIT[attempt])
	return None, error


def read_with_claude(img: bytes, mime: str):
	key, model = _claude_settings()
	if not key:
		return None, "no Claude key"
	body = {"model": model, "max_tokens": 4096, "temperature": 0,
	        "tools": [{"name": "save_recipe", "description": "Save what was read from the recipe photo.", "input_schema": pr.json_schema()}],
	        "tool_choice": {"type": "tool", "name": "save_recipe"},
	        "messages": [{"role": "user", "content": [
		        {"type": "image", "source": {"type": "base64", "media_type": mime, "data": base64.b64encode(img).decode()}},
		        {"type": "text", "text": pr.PROMPT}]}]}
	r, error = _post(CLAUDE_URL, {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}, body)
	if r is None:
		return None, error
	try:
		for block in r.json()["content"]:
			if block.get("type") == "tool_use":
				return block["input"], ""
	except Exception:
		pass
	return None, "unreadable answer: %s" % r.text[:300]


def read_with_gemini(img: bytes, mime: str):
	key, model = pdf_ocr._settings()
	if not key:
		return None, "no Gemini key"
	body = {"contents": [{"parts": [{"inline_data": {"mime_type": mime, "data": base64.b64encode(img).decode()}}, {"text": pr.PROMPT}]}],
	        "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "responseSchema": pr.SCHEMA}}
	r, error = _post(pdf_ocr.ENDPOINT.format(model=model), {"x-goog-api-key": key, "Content-Type": "application/json"}, body)
	if r is None:
		return None, error
	try:
		return json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"]), ""
	except Exception:
		return None, "unreadable answer: %s" % r.text[:300]


def read_image(raw: bytes) -> dict:
	"""Claude first; Gemini when Claude has no key, fails or finds nothing. Returns the cleaned reading plus engine / errors."""
	img, mime = prepare_image(raw)
	errors, result, engine = [], None, ""
	for name, fn in (("Claude", read_with_claude), ("Gemini", read_with_gemini)):
		data, error = fn(img, mime)
		if data is not None:
			cleaned = pr.clean(data)
			if cleaned["ingredients"] or cleaned["text"]:
				result, engine = cleaned, name
				break
			error = "nothing readable"
		errors.append("%s: %s" % (name, error))
	if result is None:
		if any("no " not in e for e in errors):
			frappe.log_error(message="\n".join(errors), title="Recipe photo: could not read")
		frappe.throw(_("The photo could not be read. Try a sharper, well-lit photo, or type the recipe by hand.") + " (%s)" % "; ".join(errors))
	result["engine"] = engine
	result["fallback_errors"] = errors
	result["text"] = pr.to_text(result)
	return result


def _items():
	return frappe.db.sql("select name, item_name, hk_item_name_zh as item_name_zh from `tabItem` where disabled = 0", as_dict=True)


def match(reading: dict) -> dict:
	items = _items()
	for ing in reading["ingredients"]:
		ing["item"] = pr.pick_match(ing["name"], items)
		ing["item_name"] = next((i.item_name for i in items if i.name == ing["item"]), "") if ing["item"] else ""
	return reading


@frappe.whitelist()
def status():
	"""Which readers are set up, so the screen can say so before a photo is taken."""
	_check()
	return {"claude": bool(_claude_settings()[0]), "gemini": bool(pdf_ocr._settings()[0])}


@frappe.whitelist()
def read_photo(file_url: str):
	"""Read an uploaded photo (a File the caller can open). Returns the cleaned reading with each ingredient matched to an item."""
	_check()
	f = frappe.get_doc("File", {"file_url": file_url})
	f.check_permission("read")
	return match(read_image(f.get_content()))


@frappe.whitelist()
def create_draft(item: str, data, file_url: str | None = None):
	"""Make a Draft Recipe for `item` from the (possibly edited) reading the screen holds."""
	_check()
	d = frappe.parse_json(data) or {}
	if frappe.db.exists("Recipe", item):
		frappe.throw(_("{0} already has a recipe").format(item))
	doc = frappe.new_doc("Recipe")
	doc.update({"item": item, "recipe_name": (d.get("title") or frappe.db.get_value("Item", item, "item_name") or item),
	            "recipe_type": "Finished Product", "status": "Draft", "batch_yield": 1, "image": file_url or None})
	left = []
	for r in d.get("ingredients") or []:
		name, qty = (r.get("name") or "").strip(), pr._num(r.get("qty"))
		if r.get("item") and qty > 0 and r.get("uom") in ("g", "kg", "oz", "lb", "ml", "l", "piece") and frappe.db.exists("Item", r["item"]):
			doc.append("ingredients", {"item": r["item"], "qty": qty, "uom": r["uom"], "component_type": "Ingredient",
			                          "notes": (r.get("note") or "")[:140]})
		else:
			left.append("%s %s %s %s" % (name, ("%g" % qty) if qty else "", r.get("uom") or "", ("(" + r["note"] + ")") if r.get("note") else "").strip())
	for s in d.get("steps") or []:
		if str(s).strip():
			doc.append("steps", {"instruction": str(s).strip()})
	notes = ["Read from a photo by %s. Check every line before activating." % (d.get("engine") or "the photo reader")]
	if d.get("yield_text"):
		notes.append("Yield written on the page: %s (batch yield is set to 1: fix it)." % d["yield_text"])
	if left:
		notes.append("Not added (no matching item, quantity or unit): " + "; ".join(left))
	if d.get("unclear"):
		notes.append("Hard to read: " + "; ".join(d["unclear"]))
	if d.get("text"):
		notes.append("--- Transcription ---\n" + d["text"])
	doc.notes = "\n".join(notes)
	doc.insert()
	return {"name": doc.name, "added": len(doc.ingredients), "left_out": len(left)}
