"""Document reader: upload a PDF or image, Gemini reads it like OCR and returns the text plus tables.

Uses the Gemini key and model already set in Gmail Settings (shared with the scanned-PDF and recipe photo readers).
Nothing is saved except the uploaded File; the screen offers the text, and each table as CSV / Excel / copy."""
from __future__ import annotations

import base64
import json

import frappe
from frappe import _

from happy_kitchen.hk_operations import pdf_ocr
from happy_kitchen.recipe_management import document_rules as rules
from happy_kitchen.recipe_management import photo_reader

ROLES = ("System Manager", "Manufacturing Manager", "Manufacturing User", "Stock Manager", "Stock User",
         "Purchase Manager", "Purchase User", "Sales Manager", "Sales User", "Accounts Manager", "Accounts User")
MAX_BYTES = 15 * 1024 * 1024


def _check():
	if not set(frappe.get_roles()) & set(ROLES):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def read_bytes(raw: bytes, filename: str = "") -> dict:
	"""Send a PDF or an image to Gemini and return the cleaned reading (throws a readable error)."""
	key, model = pdf_ocr._settings()
	if not key:
		frappe.throw(_("No Gemini key is set up: add it in Gmail Settings."))
	if not raw or len(raw) > MAX_BYTES:
		frappe.throw(_("The file is empty or larger than 15 MB."))
	if raw[:4] == b"%PDF":
		mime = "application/pdf"
	else:
		try:
			raw, mime = photo_reader.prepare_image(raw)
		except Exception:
			frappe.throw(_("Only PDF files and pictures can be read."))
	body = {"contents": [{"parts": [{"inline_data": {"mime_type": mime, "data": base64.b64encode(raw).decode()}},
	                                 {"text": rules.PROMPT}]}],
	        "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "responseSchema": rules.SCHEMA}}
	r, error = photo_reader._post(pdf_ocr.ENDPOINT.format(model=model),
	                              {"x-goog-api-key": key, "Content-Type": "application/json"}, body, timeout=180)
	if r is None:
		frappe.log_error(message="Model %s. %s" % (model, error), title="Document reader: Gemini read failed")
		frappe.throw(_("Gemini could not read the file. Try again in a minute.") + " (%s)" % error[:150])
	try:
		out = rules.clean(json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"]))
	except Exception:
		frappe.log_error(message="Model %s. Unreadable answer: %s" % (model, r.text[:500]), title="Document reader: bad answer")
		frappe.throw(_("Gemini sent an answer that could not be understood. Try again."))
	if not out["text"] and not out["tables"]:
		frappe.throw(_("Nothing readable was found in the file."))
	out["filename"] = filename
	out["engine"] = "Gemini (%s)" % model
	return out


@frappe.whitelist()
def status():
	_check()
	return {"gemini": bool(pdf_ocr._settings()[0])}


@frappe.whitelist()
def read_document(file_url: str):
	"""Read an uploaded File (one the caller can open)."""
	_check()
	f = frappe.get_doc("File", {"file_url": file_url})
	f.check_permission("read")
	return read_bytes(f.get_content(), f.file_name or "")


@frappe.whitelist()
def export_xlsx(data):
	"""The tables as one Excel workbook (one sheet per table, the text on its own sheet). Returns base64."""
	_check()
	d = rules.clean(frappe.parse_json(data) or {})
	sheets = []
	if d["text"]:
		sheets.append(("Text", [[ln] for ln in d["text"].split("\n")]))
	for i, t in enumerate(d["tables"], 1):
		sheets.append(("Table %d" % i, rules.grid(t)))
	if not sheets:
		frappe.throw(_("Nothing to export"))
	import io

	from openpyxl import Workbook

	wb = Workbook()
	wb.remove(wb.active)
	for name, rows in sheets:
		ws = wb.create_sheet(name)
		for row in rows:
			ws.append(row)
	out = io.BytesIO()
	wb.save(out)
	return base64.b64encode(out.getvalue()).decode()
